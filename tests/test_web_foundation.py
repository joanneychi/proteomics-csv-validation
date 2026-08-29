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
    ] == "no-referrer"

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
    ] == "no-referrer"

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
