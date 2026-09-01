"""Foundation tests for the optional local browser application."""

from __future__ import annotations

import argparse
import ast
import asyncio
from pathlib import Path
import tomllib

from proteomics_csv_validation.web import (
    cli as web_cli,
)
from proteomics_csv_validation.web.app import (
    create_http_app,
)
from proteomics_csv_validation.web.composition import (
    create_app,
)
from proteomics_csv_validation.web.security import (
    SecurityHeadersMiddleware,
)


_ROOT = Path(
    __file__
).resolve().parents[1]

_PACKAGE = (
    _ROOT
    / "src"
    / "proteomics_csv_validation"
)

_WEB = (
    _PACKAGE
    / "web"
)


def _imports(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )

    modules: set[str] = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(
                node.module
            )

    return modules


def _request(
    path: str,
    *,
    host: str = "localhost",
) -> tuple[
    int,
    dict[str, str],
    bytes,
]:
    app = create_app()

    messages: list[
        dict
    ] = []

    async def run() -> None:
        sent_request = False

        async def receive() -> dict:
            nonlocal sent_request

            if not sent_request:
                sent_request = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }

            return {
                "type": "http.disconnect",
            }

        async def send(
            message: dict,
        ) -> None:
            messages.append(
                message
            )

        await app(
            {
                "type": "http",
                "asgi": {
                    "version": "3.0",
                },
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(
                    "ascii"
                ),
                "query_string": b"",
                "headers": [
                    (
                        b"host",
                        host.encode(
                            "ascii"
                        ),
                    ),
                ],
                "client": (
                    "127.0.0.1",
                    40000,
                ),
                "server": (
                    "127.0.0.1",
                    8000,
                ),
                "root_path": "",
            },
            receive,
            send,
        )

    asyncio.run(
        run()
    )

    start = next(
        message
        for message in messages
        if message["type"]
        == "http.response.start"
    )

    body = b"".join(
        message.get(
            "body",
            b"",
        )
        for message in messages
        if message["type"]
        == "http.response.body"
    )

    headers = {
        name.decode(
            "latin-1"
        ).lower():
        value.decode(
            "latin-1"
        )
        for name, value in start[
            "headers"
        ]
    }

    return (
        start["status"],
        headers,
        body,
    )


def test_app_disables_public_api_documentation() -> None:
    app = create_http_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_global_security_envelope_wraps_http_middleware() -> None:
    http_app = create_http_app()

    middleware = {
        item.cls.__name__
        for item in http_app.user_middleware
    }

    assert "TrustedHostMiddleware" in middleware
    assert "SecurityHeadersMiddleware" not in middleware
    assert "CORSMiddleware" not in middleware

    app = create_app()

    assert isinstance(
        app,
        SecurityHeadersMiddleware,
    )


def test_health_response_has_security_headers() -> None:
    status, headers, body = _request(
        "/health"
    )

    assert status == 200
    assert body == b"ok"

    assert headers[
        "content-security-policy"
    ].startswith(
        "default-src 'self';"
    )

    assert headers[
        "referrer-policy"
    ] == "same-origin"

    assert headers[
        "x-content-type-options"
    ] == "nosniff"

    assert headers[
        "x-frame-options"
    ] == "DENY"

    assert headers[
        "cross-origin-opener-policy"
    ] == "same-origin"

    assert headers[
        "cross-origin-resource-policy"
    ] == "same-origin"

    assert "camera=()" in headers[
        "permissions-policy"
    ]


def test_unhandled_500_response_has_global_security_headers() -> None:
    inner = create_http_app()

    @inner.get(
        "/__test_unhandled_error__",
        include_in_schema=False,
    )
    async def raise_unhandled_error() -> None:
        raise RuntimeError(
            "test unhandled error"
        )

    app = SecurityHeadersMiddleware(
        inner
    )

    messages: list[
        dict
    ] = []

    async def run() -> None:
        sent_request = False

        async def receive() -> dict:
            nonlocal sent_request

            if not sent_request:
                sent_request = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }

            return {
                "type": "http.disconnect",
            }

        async def send(
            message: dict,
        ) -> None:
            messages.append(
                message
            )

        try:
            await app(
                {
                    "type": "http",
                    "asgi": {
                        "version": "3.0",
                    },
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": "/__test_unhandled_error__",
                    "raw_path": b"/__test_unhandled_error__",
                    "query_string": b"",
                    "headers": [
                        (
                            b"host",
                            b"localhost",
                        ),
                    ],
                    "client": (
                        "127.0.0.1",
                        40000,
                    ),
                    "server": (
                        "127.0.0.1",
                        8000,
                    ),
                    "root_path": "",
                },
                receive,
                send,
            )
        except RuntimeError as exc:
            assert str(
                exc
            ) == "test unhandled error"
        else:
            raise AssertionError(
                "Expected the unhandled exception "
                "to be re-raised."
            )

    asyncio.run(
        run()
    )

    start = next(
        message
        for message in messages
        if message["type"]
        == "http.response.start"
    )

    headers = {
        name.decode(
            "latin-1"
        ).lower():
        value.decode(
            "latin-1"
        )
        for name, value in start[
            "headers"
        ]
    }

    assert start[
        "status"
    ] == 500

    assert headers[
        "content-security-policy"
    ].startswith(
        "default-src 'self';"
    )

    assert headers[
        "referrer-policy"
    ] == "same-origin"

    assert headers[
        "x-content-type-options"
    ] == "nosniff"

    assert headers[
        "x-frame-options"
    ] == "DENY"

    assert headers[
        "cross-origin-opener-policy"
    ] == "same-origin"

    assert headers[
        "cross-origin-resource-policy"
    ] == "same-origin"

    assert "camera=()" in headers[
        "permissions-policy"
    ]


def test_invalid_host_is_rejected_with_security_headers() -> None:
    status, headers, _ = _request(
        "/health",
        host="example.invalid",
    )

    assert status == 400

    assert headers[
        "x-content-type-options"
    ] == "nosniff"

    assert headers[
        "x-frame-options"
    ] == "DENY"


def test_web_foundation_does_not_import_certified_inner_layers() -> None:
    forbidden = (
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.domain",
        "proteomics_csv_validation.infrastructure",
        "proteomics_csv_validation.models",
        "proteomics_csv_validation.pipeline",
        "proteomics_csv_validation.profiles",
        "proteomics_csv_validation.validators",
    )

    allowed_application = (
        "proteomics_csv_validation.application.browser_review"
    )

    composition_bridge = (
        "proteomics_csv_validation.review_composition"
    )

    for path in _WEB.glob(
        "*.py"
    ):
        for module in _imports(
            path
        ):
            if module.startswith(
                "proteomics_csv_validation.application"
            ):
                assert (
                    path.name == "review.py"
                    and module == allowed_application
                ), (
                    path,
                    module,
                )

                continue

            if module == composition_bridge:
                assert path.name == "composition.py", (
                    path,
                    module,
                )

                continue

            assert not module.startswith(
                forbidden
            ), (
                path,
                module,
            )


def test_existing_inner_layers_do_not_import_web() -> None:
    for path in _PACKAGE.rglob(
        "*.py"
    ):
        if "web" in path.parts:
            continue

        for module in _imports(
            path
        ):
            assert not module.startswith(
                "proteomics_csv_validation.web"
            ), (
                path,
                module,
            )


def test_base_template_has_semantic_accessibility_shell() -> None:
    text = (
        _WEB
        / "templates"
        / "base.html"
    ).read_text(
        encoding="utf-8"
    )

    lowered = text.lower()

    assert "<!doctype html>" in lowered
    assert '<html lang="en">' in lowered
    assert 'name="viewport"' in lowered
    assert 'href="#main-content"' in lowered
    assert 'id="main-content"' in lowered
    assert "/static/app.css" in text

    assert "<script" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered


def test_foundation_css_has_focus_and_reduced_motion_contract() -> None:
    text = (
        _WEB
        / "static"
        / "app.css"
    ).read_text(
        encoding="utf-8"
    )

    lowered = text.lower()

    assert ":focus-visible" in text
    assert (
        "prefers-reduced-motion: reduce"
        in text
    )

    assert "@import" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered


def test_pyproject_preserves_base_runtime_and_adds_exact_web_extra() -> None:
    data = tomllib.loads(
        (
            _ROOT
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    project = data[
        "project"
    ]

    assert project[
        "dependencies"
    ] == []

    assert project[
        "optional-dependencies"
    ][
        "dev"
    ] == [
        "pytest>=8.0,<9",
        "httpx2==2.12.0",
    ]

    assert project[
        "optional-dependencies"
    ][
        "web"
    ] == [
        "fastapi==0.141.1",
        "uvicorn==0.52.4",
        "Jinja2==3.1.6",
        "python-multipart==0.0.32",
    ]


def test_pyproject_preserves_cli_and_adds_web_launcher() -> None:
    data = tomllib.loads(
        (
            _ROOT
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    scripts = data[
        "project"
    ][
        "scripts"
    ]

    assert scripts[
        "proteomics-csv-validate"
    ] == (
        "proteomics_csv_validation."
        "cli:main"
    )

    assert scripts[
        "proteomics-csv-app"
    ] == (
        "proteomics_csv_validation."
        "web.cli:main"
    )


def test_web_package_data_contract_is_explicit() -> None:
    data = tomllib.loads(
        (
            _ROOT
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    package_data = (
        data[
            "tool"
        ][
            "setuptools"
        ][
            "package-data"
        ]
    )

    assert package_data[
        "proteomics_csv_validation.web"
    ] == [
        "templates/*.html",
        "static/*.css",
    ]


def test_workflow_installs_web_extra_for_test_matrix() -> None:
    text = (
        _ROOT
        / ".github"
        / "workflows"
        / "cross-platform.yml"
    ).read_text(
        encoding="utf-8"
    )

    assert text.count(
        'python -m pip install -e ".[dev,web]"'
    ) == 1

    assert (
        'python -m pip install -e ".[dev]"'
        not in text
    )


def test_web_launcher_has_no_external_bind_option() -> None:
    parser = (
        web_cli._parser()
    )

    actions = {
        action.dest:
        action
        for action in parser._actions
    }

    assert "host" not in actions
    assert web_cli._LOOPBACK_HOST == "127.0.0.1"
    assert web_cli._DEFAULT_PORT == 8000

    assert isinstance(
        actions[
            "port"
        ],
        argparse.Action,
    )

    assert parser.parse_args(
        []
    ).port == 8000


def _theme_contract_sources() -> tuple[str, str]:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    css = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "static"
        / "app.css"
    ).read_text(
        encoding="utf-8"
    )

    base = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "base.html"
    ).read_text(
        encoding="utf-8"
    )

    return css, base


def _theme_contract_declarations(
    block: str,
) -> dict[str, str]:
    import re

    return {
        name: " ".join(value.split())
        for name, value in re.findall(
            (
                r"(--[A-Za-z0-9_-]+)"
                r"\s*:\s*"
                r"([^;]+);"
            ),
            block,
        )
    }


def _theme_contract_root_block(
    css: str,
) -> str:
    import re

    match = re.search(
        r":root\s*\{([^{}]*)\}",
        css,
        re.S,
    )

    assert match is not None

    return match.group(1)


def _theme_contract_dark_block(
    css: str,
) -> str | None:
    import re

    match = re.search(
        (
            r"@media\s*"
            r"\(\s*prefers-color-scheme"
            r"\s*:\s*dark\s*\)"
            r"\s*\{\s*"
            r":root\s*\{([^{}]*)\}"
            r"\s*\}"
        ),
        css,
        re.S | re.I,
    )

    return (
        match.group(1)
        if match is not None
        else None
    )


def test_foundation_declares_system_light_dark_color_scheme_without_script_toggle(
) -> None:
    import re

    css, base = _theme_contract_sources()

    metadata = (
        re.search(
            (
                r'<meta\b'
                r'[^>]*\bname=["\']'
                r'color-scheme["\']'
                r'[^>]*\bcontent=["\']'
                r'light\s+dark["\']'
                r'[^>]*>'
            ),
            base,
            re.I,
        )
        is not None
    )

    root_contract = (
        re.search(
            (
                r"(?m)^\s*"
                r"color-scheme"
                r"\s*:\s*"
                r"light\s+dark"
                r"\s*;\s*$"
            ),
            _theme_contract_root_block(
                css
            ),
            re.I,
        )
        is not None
    )

    system_dark = (
        _theme_contract_dark_block(css)
        is not None
    )

    no_script_state = all(
        token not in (
            base + "\n" + css
        ).lower()
        for token in (
            "<script",
            "localstorage",
            "sessionstorage",
            "data-theme",
            "theme-toggle",
        )
    )

    assert (
        metadata,
        root_contract,
        system_dark,
        no_script_state,
    ) == (
        True,
        True,
        True,
        True,
    )


def test_foundation_css_has_semantic_theme_role_contract(
) -> None:
    import re

    css, _ = _theme_contract_sources()

    root_match = re.search(
        r":root\s*\{([^{}]*)\}",
        css,
        re.S,
    )

    assert root_match is not None

    light = _theme_contract_declarations(
        root_match.group(1)
    )

    dark_block = _theme_contract_dark_block(
        css
    )

    dark = (
        _theme_contract_declarations(
            dark_block
        )
        if dark_block is not None
        else {}
    )

    expected_light = {
        "--ui-text-primary":
            "var(--ink)",
        "--ui-text-muted":
            "var(--muted)",
        "--ui-link":
            "var(--navy)",

        "--ui-canvas":
            "var(--paper)",
        "--ui-surface":
            "var(--white)",
        "--ui-field-subtle":
            "var(--paper)",
        "--ui-field":
            "var(--white)",

        "--ui-border-subtle":
            "var(--neutral)",
        "--ui-border-control":
            "var(--muted)",

        "--ui-accent":
            "var(--gold)",
        "--ui-attention-border":
            "var(--gold)",
        "--ui-attention-bg":
            "var(--apricot)",

        "--ui-action-bg":
            "var(--navy)",
        "--ui-action-hover":
            "var(--ink)",
        "--ui-action-text":
            "var(--white)",

        "--ui-focus-inner":
            "var(--white)",
        "--ui-focus-outer":
            "var(--navy)",

        "--ui-inverse-bg":
            "var(--ink)",
        "--ui-inverse-text":
            "var(--white)",
    }

    expected_dark = {
        "--ui-text-primary":
            "#E8EEF5",
        "--ui-text-muted":
            "#AEBBC9",
        "--ui-link":
            "#8FC5F4",

        "--ui-canvas":
            "#0D1420",
        "--ui-surface":
            "#131E2B",
        "--ui-field-subtle":
            "#0D1420",
        "--ui-field":
            "#172434",

        "--ui-border-subtle":
            "#34495E",
        "--ui-border-control":
            "#647D95",

        "--ui-accent":
            "#D9A441",
        "--ui-attention-border":
            "#D9A441",
        "--ui-attention-bg":
            "#2A2114",

        "--ui-action-bg":
            "#2B6692",
        "--ui-action-hover":
            "#3B76A0",
        "--ui-action-text":
            "#FFFFFF",

        "--ui-focus-inner":
            "#FFFFFF",
        "--ui-focus-outer":
            "#6FB8E8",

        "--ui-inverse-bg":
            "#E8EEF5",
        "--ui-inverse-text":
            "#0D1420",
    }

    assert len(
        expected_light
    ) == 19

    assert set(
        expected_light
    ) == set(
        expected_dark
    )

    actual_light = {
        role:
            light.get(role)
        for role in expected_light
    }

    actual_dark = {
        role:
            dark.get(role)
        for role in expected_dark
    }

    dark_normalized = {
        role:
            (
                value.upper()
                if value is not None
                else None
            )
        for role, value
        in actual_dark.items()
    }

    expected_dark_normalized = {
        role:
            value.upper()
        for role, value
        in expected_dark.items()
    }

    palette_tokens = (
        "--ink",
        "--navy",
        "--gold",
        "--paper",
        "--mist",
        "--neutral",
        "--apricot",
        "--muted",
        "--white",
    )

    outside_light_root = (
        css[:root_match.start()]
        + css[root_match.end():]
    )

    palette_component_refs = [
        token
        for token in palette_tokens
        if (
            "var("
            + token
            + ")"
        )
        in outside_light_root
    ]

    assert (
        actual_light,
        dark_normalized,
        palette_component_refs,
    ) == (
        expected_light,
        expected_dark_normalized,
        [],
    )


def test_foundation_theme_color_pairs_meet_static_contrast_contract(
) -> None:
    import re

    css, _ = _theme_contract_sources()

    light = _theme_contract_declarations(
        _theme_contract_root_block(
            css
        )
    )

    dark_block = _theme_contract_dark_block(
        css
    )

    assert dark_block is not None

    dark = _theme_contract_declarations(
        dark_block
    )

    roles = (
        "--ui-text-primary",
        "--ui-text-muted",
        "--ui-link",
        "--ui-canvas",
        "--ui-surface",
        "--ui-field-subtle",
        "--ui-field",
        "--ui-border-subtle",
        "--ui-border-control",
        "--ui-accent",
        "--ui-attention-border",
        "--ui-attention-bg",
        "--ui-action-bg",
        "--ui-action-hover",
        "--ui-action-text",
        "--ui-focus-inner",
        "--ui-focus-outer",
        "--ui-inverse-bg",
        "--ui-inverse-text",
    )

    assert all(
        role in light
        and role in dark
        for role in roles
    )

    def resolve(
        name: str,
        mapping: dict[str, str],
    ) -> str:
        value = mapping[name]

        seen = {
            name
        }

        while True:
            match = re.fullmatch(
                (
                    r"var\(\s*"
                    r"(--[A-Za-z0-9_-]+)"
                    r"\s*\)"
                ),
                value,
            )

            if match is None:
                return value

            target = match.group(1)

            assert target not in seen

            seen.add(target)

            assert target in mapping

            value = mapping[target]

    def linear(
        value: int,
    ) -> float:
        channel = value / 255.0

        if channel <= 0.04045:
            return channel / 12.92

        return (
            (
                channel + 0.055
            )
            / 1.055
        ) ** 2.4

    def luminance(
        value: str,
    ) -> float:
        value = value.lstrip("#")

        assert len(value) == 6

        red = int(
            value[0:2],
            16,
        )

        green = int(
            value[2:4],
            16,
        )

        blue = int(
            value[4:6],
            16,
        )

        return (
            0.2126 * linear(red)
            + 0.7152 * linear(green)
            + 0.0722 * linear(blue)
        )

    def contrast(
        first: str,
        second: str,
    ) -> float:
        a = luminance(first)
        b = luminance(second)

        high = max(a, b)
        low = min(a, b)

        return (
            high + 0.05
        ) / (
            low + 0.05
        )

    checks = (
        (
            "TEXT_CANVAS",
            "--ui-text-primary",
            "--ui-canvas",
            4.5,
        ),
        (
            "TEXT_SURFACE",
            "--ui-text-primary",
            "--ui-surface",
            4.5,
        ),
        (
            "MUTED_CANVAS",
            "--ui-text-muted",
            "--ui-canvas",
            4.5,
        ),
        (
            "MUTED_SURFACE",
            "--ui-text-muted",
            "--ui-surface",
            4.5,
        ),
        (
            "LINK_CANVAS",
            "--ui-link",
            "--ui-canvas",
            4.5,
        ),
        (
            "LINK_SURFACE",
            "--ui-link",
            "--ui-surface",
            4.5,
        ),
        (
            "ACCENT_CANVAS",
            "--ui-accent",
            "--ui-canvas",
            4.5,
        ),
        (
            "ACCENT_SURFACE",
            "--ui-accent",
            "--ui-surface",
            4.5,
        ),
        (
            "ACTION",
            "--ui-action-text",
            "--ui-action-bg",
            4.5,
        ),
        (
            "ACTION_HOVER",
            "--ui-action-text",
            "--ui-action-hover",
            4.5,
        ),
        (
            "INVERSE",
            "--ui-inverse-text",
            "--ui-inverse-bg",
            4.5,
        ),
        (
            "CONTROL_BORDER_CANVAS",
            "--ui-border-control",
            "--ui-canvas",
            3.0,
        ),
        (
            "CONTROL_BORDER_SURFACE",
            "--ui-border-control",
            "--ui-surface",
            3.0,
        ),
        (
            "CONTROL_BORDER_FIELD",
            "--ui-border-control",
            "--ui-field",
            3.0,
        ),
        (
            "FOCUS_OUTER_CANVAS",
            "--ui-focus-outer",
            "--ui-canvas",
            3.0,
        ),
        (
            "FOCUS_OUTER_SURFACE",
            "--ui-focus-outer",
            "--ui-surface",
            3.0,
        ),
        (
            "FOCUS_OUTER_FIELD",
            "--ui-focus-outer",
            "--ui-field",
            3.0,
        ),
        (
            "ATTENTION_BORDER_BG",
            "--ui-attention-border",
            "--ui-attention-bg",
            3.0,
        ),
        (
            "TEXT_ATTENTION_BG",
            "--ui-text-primary",
            "--ui-attention-bg",
            4.5,
        ),
    )

    for theme_name, mapping in (
        (
            "LIGHT",
            light,
        ),
        (
            "DARK",
            dark,
        ),
    ):
        for (
            name,
            foreground,
            background,
            minimum,
        ) in checks:

            required = minimum

            if (
                theme_name
                == "DARK"
                and name.startswith(
                    "CONTROL_BORDER_"
                )
            ):
                required = 3.5

            result = contrast(
                resolve(
                    foreground,
                    mapping,
                ),
                resolve(
                    background,
                    mapping,
                ),
            )

            assert result >= required, (
                theme_name,
                name,
                result,
                required,
            )
