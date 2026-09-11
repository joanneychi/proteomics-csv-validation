"""HTTP workflow tests for the loopback-only Review vertical slice."""

from __future__ import annotations

from html.parser import HTMLParser
import ast
import json
from pathlib import Path
import re
import sqlite3
import tomllib

from fastapi.testclient import (
    TestClient,
)

from proteomics_csv_validation.web.composition import (
    create_app,
)
from proteomics_csv_validation.web.security import (
    SecurityHeadersMiddleware,
)

_ROOT = Path(
    __file__
).resolve().parents[
    1
]

_BASELINE = (
    _ROOT
    / "data"
    / "synthetic"
    / "baseline_valid.csv"
)

_SEEDED = (
    _ROOT
    / "data"
    / "synthetic"
    / "seeded_errors.csv"
)

_SECRET = (
    b"d3-test-secret-material-32-bytes!!"
)

_ORIGIN = (
    "http://127.0.0.1:8000"
)


class _VisibleTextParser(
    HTMLParser
):
    def __init__(
        self,
    ) -> None:
        super().__init__(
            convert_charrefs=True
        )

        self.parts: list[
            str
        ] = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        self.parts.append(
            data
        )


def _visible_text(
    document: str,
) -> str:
    parser = _VisibleTextParser()

    parser.feed(
        document
    )

    return " ".join(
        " ".join(
            parser.parts
        ).split()
    )


def _application(
    tmp_path: Path,
):
    return create_app(
        data_root=(
            tmp_path
            / "app-data"
        ).resolve(),
        csrf_secret=_SECRET,
    )


def _csrf(
    client: TestClient,
) -> str:
    response = client.get(
        "/review"
    )

    assert response.status_code == 200

    match = re.search(
        (
            r'name="csrf_token"\s+'
            r'value="([0-9a-f]+\.[0-9a-f]+)"'
        ),
        response.text,
    )

    assert match is not None

    return match.group(
        1
    )


def _submit(
    client: TestClient,
    source: Path,
    *,
    profile_version: str = "0.2.0",
    mapping_mode: str = "strict",
    filename: str | None = None,
    token: str | None = None,
    headers: dict[
        str,
        str,
    ] | None = None,
):
    csrf = (
        _csrf(
            client
        )
        if token is None
        else token
    )

    request_headers = {
        "Origin": _ORIGIN,
        "Sec-Fetch-Site": (
            "same-origin"
        ),
    }

    if headers is not None:
        request_headers.update(
            headers
        )

    return client.post(
        "/reviews",
        data={
            "csrf_token": csrf,
            "profile_version": (
                profile_version
            ),
            "mapping_mode": (
                mapping_mode
            ),
        },
        files={
            "input_file": (
                filename
                or source.name,
                source.read_bytes(),
                "text/csv",
            ),
        },
        headers=request_headers,
        follow_redirects=False,
    )


def test_root_redirects_to_review_and_review_is_semantic(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        root = client.get(
            "/",
            follow_redirects=False,
        )

        assert root.status_code == 303
        assert root.headers[
            "location"
        ] == "/review"

        response = client.get(
            "/review"
        )

        assert response.status_code == 200
        assert response.text.count(
            "<h1"
        ) == 1

        assert (
            'action="/reviews"'
            in response.text
        )

        assert (
            'method="post"'
            in response.text
        )

        assert (
            'enctype="multipart/form-data"'
            in response.text
        )

        assert (
            'for="input-file"'
            in response.text
        )

        assert (
            'for="profile-version"'
            in response.text
        )

        assert (
            "0.1.0 · Processed Sample Summary · historical"
            in response.text
        )

        assert (
            'for="mapping-mode"'
            in response.text
        )

        assert (
            'for="mapping-file"'
            in response.text
        )

        assert (
            "<script"
            not in response.text.casefold()
        )


def test_review_post_requires_browser_origin_before_form_processing(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        token = _csrf(
            client
        )

        response = client.post(
            "/reviews",
            data={
                "csrf_token": token,
                "profile_version": (
                    "0.2.0"
                ),
                "mapping_mode": (
                    "strict"
                ),
            },
            files={
                "input_file": (
                    _BASELINE.name,
                    _BASELINE.read_bytes(),
                    "text/csv",
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 403


def test_review_post_rejects_cross_site_fetch_metadata(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        token = _csrf(
            client
        )

        response = _submit(
            client,
            _BASELINE,
            token=token,
            headers={
                "Sec-Fetch-Site": (
                    "cross-site"
                ),
            },
        )

        assert response.status_code == 403


def test_review_post_rejects_wrong_origin(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        token = _csrf(
            client
        )

        response = _submit(
            client,
            _BASELINE,
            token=token,
            headers={
                "Origin": (
                    "http://example.invalid"
                ),
            },
        )

        assert response.status_code == 403


def test_review_post_accepts_same_origin_referer_without_origin(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.post(
            "/reviews",
            data={
                "csrf_token": _csrf(
                    client
                ),
                "profile_version": "0.2.0",
                "mapping_mode": "strict",
            },
            files={
                "input_file": (
                    _BASELINE.name,
                    _BASELINE.read_bytes(),
                    "text/csv",
                ),
            },
            headers={
                "Referer": (
                    _ORIGIN
                    + "/review"
                ),
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303

        assert re.fullmatch(
            r"/results/[0-9a-f]{32}",
            response.headers[
                "location"
            ],
        )


def test_review_post_rejects_opaque_null_origin(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.post(
            "/reviews",
            data={
                "csrf_token": _csrf(
                    client
                ),
                "profile_version": "0.2.0",
                "mapping_mode": "strict",
            },
            files={
                "input_file": (
                    _BASELINE.name,
                    _BASELINE.read_bytes(),
                    "text/csv",
                ),
            },
            headers={
                "Origin": "null",
                "Referer": (
                    _ORIGIN
                    + "/review"
                ),
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 403



def test_review_post_rejects_invalid_csrf_token(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
            token=(
                "0"
                * 64
                + "."
                + "0"
                * 64
            ),
        )

        assert response.status_code == 403


def test_raw_request_body_limit_is_enforced(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.post(
            "/reviews",
            content=(
                b"x"
                * 12_000_001
            ),
            headers={
                "Origin": _ORIGIN,
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
                "Content-Type": (
                    "application/octet-stream"
                ),
            },
        )

        assert response.status_code == 413

        assert response.headers[
            "x-content-type-options"
        ] == "nosniff"


def test_invalid_profile_is_accessible_422_form_error(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
            profile_version=(
                "999.0.0"
            ),
        )

        assert response.status_code == 422

        assert (
            'role="alert"'
            in response.text
        )

        assert (
            'href="#profile-version"'
            in response.text
        )

        assert (
            "Select a supported review profile."
            in response.text
        )


def test_explicit_mapping_requires_json_mapping_file(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
            mapping_mode="explicit",
        )

        assert response.status_code == 422

        assert (
            'href="#mapping-file"'
            in response.text
        )


def test_non_csv_browser_filename_is_rejected(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
            filename="input.txt",
        )

        assert response.status_code == 422

        assert (
            'href="#input-file"'
            in response.text
        )


def test_baseline_review_prg_persists_verified_result_and_cleans_staging(
    tmp_path: Path,
) -> None:
    data_root = (
        tmp_path
        / "app-data"
    ).resolve()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=_SECRET,
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
        )

        assert response.status_code == 303

        location = response.headers[
            "location"
        ]

        assert re.fullmatch(
            r"/results/[0-9a-f]{32}",
            location,
        )

        result = client.get(
            location
        )

        assert result.status_code == 200

        assert (
            result.headers[
                "cache-control"
            ]
            == "no-store"
        )

        assert (
            "Structural review completed"
            in result.text
        )

        assert (
            "0 structural findings"
            in _visible_text(
                result.text
            )
        )

        assert (
            "does not establish scientific validity"
            in result.text
        )

    staging = (
        data_root
        / "staging"
    )

    assert staging.is_dir()
    assert list(
        staging.iterdir()
    ) == []

    assert not tuple(
        data_root.rglob(
            "input.csv"
        )
    )


def test_seeded_review_reports_four_structural_findings(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _SEEDED,
        )

        assert response.status_code == 303

        result = client.get(
            response.headers[
                "location"
            ]
        )

        assert result.status_code == 200

        assert (
            "4 structural findings"
            in _visible_text(
                result.text
            )
        )


def test_configuration_persists_byte_evidence_not_temporary_path(
    tmp_path: Path,
) -> None:
    data_root = (
        tmp_path
        / "app-data"
    ).resolve()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=_SECRET,
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
            filename=(
                "../../submitted.csv"
            ),
        )

        assert response.status_code == 303

        run_id = (
            response.headers[
                "location"
            ]
            .rsplit(
                "/",
                1,
            )[-1]
        )

    with sqlite3.connect(
        data_root
        / "ledger.sqlite3"
    ) as connection:
        row = connection.execute(
            """
            SELECT c.canonical_json
            FROM run_configuration AS c
            JOIN analysis_run AS r
              ON r.configuration_id = c.configuration_id
            WHERE r.run_id = ?
            """,
            (
                run_id,
            ),
        ).fetchone()

    assert row is not None

    document = json.loads(
        row[
            0
        ]
    )

    assert document[
        "source"
    ][
        "display_name"
    ] == "submitted.csv"

    assert document[
        "source"
    ][
        "byte_count"
    ] == len(
        _BASELINE.read_bytes()
    )

    assert re.fullmatch(
        r"[0-9a-f]{64}",
        document[
            "source"
        ][
            "sha256"
        ],
    )

    assert str(
        tmp_path
    ) not in row[
        0
    ]

    assert (
        "input.csv"
        not in row[
            0
        ]
    )


def test_unknown_result_is_404(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.get(
            "/results/"
            + "0"
            * 32
        )

        assert response.status_code == 404


def test_d3_middleware_and_dependency_boundaries_are_exact(
    tmp_path: Path,
) -> None:
    outer = _application(
        tmp_path
    )

    assert isinstance(
        outer,
        SecurityHeadersMiddleware,
    )

    http_app = outer._app

    assert [
        item.cls.__name__
        for item
        in http_app.user_middleware
    ] == [
        "TrustedHostMiddleware",
        "RequestBodyLimitMiddleware",
    ]

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



def _imported_modules(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(
            path
        ),
    )

    modules: set[
        str
    ] = set()

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


def test_d3_composition_boundary_is_explicit() -> None:
    source = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
    )

    review_imports = _imported_modules(
        source
        / "web"
        / "review.py"
    )

    application_imports = {
        module
        for module in review_imports
        if module.startswith(
            "proteomics_csv_validation.application"
        )
    }

    assert application_imports == {
        "proteomics_csv_validation.application.browser_review",
    }

    assert not any(
        module.startswith(
            (
                "proteomics_csv_validation.adapters",
                "proteomics_csv_validation.domain",
                "proteomics_csv_validation.infrastructure",
            )
        )
        for module in review_imports
    )

    web_composition_imports = _imported_modules(
        source
        / "web"
        / "composition.py"
    )

    assert (
        "proteomics_csv_validation.review_composition"
        in web_composition_imports
    )

    assert not any(
        module.startswith(
            (
                "proteomics_csv_validation.adapters",
                "proteomics_csv_validation.application",
                "proteomics_csv_validation.domain",
                "proteomics_csv_validation.infrastructure",
            )
        )
        for module in web_composition_imports
    )

    facade_imports = _imported_modules(
        source
        / "application"
        / "browser_review.py"
    )

    assert not any(
        module.startswith(
            (
                "proteomics_csv_validation.adapters",
                "proteomics_csv_validation.infrastructure",
                "proteomics_csv_validation.web",
            )
        )
        for module in facade_imports
    )

    outer_imports = _imported_modules(
        source
        / "review_composition.py"
    )

    assert (
        "proteomics_csv_validation.adapters.core_validation"
        in outer_imports
    )

    assert (
        "proteomics_csv_validation.infrastructure.sqlite.run_repository"
        in outer_imports
    )

    assert not any(
        module.startswith(
            "proteomics_csv_validation.web"
        )
        for module in outer_imports
    )



def _f1_csrf_token(
    client,
) -> str:
    import re

    response = client.get(
        "/review"
    )

    assert response.status_code == 200

    match = re.search(
        (
            r'name="csrf_token"\s+'
            r'value="([0-9a-f]+\.[0-9a-f]+)"'
        ),
        response.text,
    )

    assert match is not None

    return match.group(
        1
    )


def test_duplicate_input_file_parts_are_rejected(
    tmp_path,
) -> None:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from proteomics_csv_validation.web.composition import (
        create_app,
    )

    origin = (
        "http://127.0.0.1:8000"
    )

    data_root = (
        tmp_path
        / "data"
    ).resolve()

    source = (
        Path(
            __file__
        )
        .resolve()
        .parents[
            1
        ]
        / "data"
        / "synthetic"
        / "baseline_valid.csv"
    ).read_bytes()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=(
                b"f1-multipart-shape-test-secret-0001"
            ),
        ),
        base_url=origin,
    ) as client:
        response = client.post(
            "/reviews",
            data={
                "csrf_token": (
                    _f1_csrf_token(
                        client
                    )
                ),
                "profile_version": (
                    "0.2.0"
                ),
                "mapping_mode": (
                    "strict"
                ),
            },
            files=[
                (
                    "input_file",
                    (
                        "first.csv",
                        source,
                        "text/csv",
                    ),
                ),
                (
                    "input_file",
                    (
                        "second.csv",
                        source,
                        "text/csv",
                    ),
                ),
            ],
            headers={
                "Origin": origin,
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
            },
            follow_redirects=False,
        )

    assert response.status_code == 400

    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )

    assert (
        "location"
        not in response.headers
    )


def test_unknown_second_file_part_is_rejected(
    tmp_path,
) -> None:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from proteomics_csv_validation.web.composition import (
        create_app,
    )

    origin = (
        "http://127.0.0.1:8000"
    )

    data_root = (
        tmp_path
        / "data"
    ).resolve()

    source = (
        Path(
            __file__
        )
        .resolve()
        .parents[
            1
        ]
        / "data"
        / "synthetic"
        / "baseline_valid.csv"
    ).read_bytes()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=(
                b"f1-multipart-shape-test-secret-0002"
            ),
        ),
        base_url=origin,
    ) as client:
        response = client.post(
            "/reviews",
            data={
                "csrf_token": (
                    _f1_csrf_token(
                        client
                    )
                ),
                "profile_version": (
                    "0.2.0"
                ),
                "mapping_mode": (
                    "strict"
                ),
            },
            files=[
                (
                    "input_file",
                    (
                        "baseline_valid.csv",
                        source,
                        "text/csv",
                    ),
                ),
                (
                    "unexpected_file",
                    (
                        "extra.bin",
                        b"untrusted-extra",
                        "application/octet-stream",
                    ),
                ),
            ],
            headers={
                "Origin": origin,
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
            },
            follow_redirects=False,
        )

    assert response.status_code == 400

    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )

    assert (
        "location"
        not in response.headers
    )


def test_ingestion_stop_status_is_visible_and_distinct_from_execution_success(
    tmp_path,
) -> None:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from proteomics_csv_validation.web.composition import (
        create_app,
    )

    stopped_cases = (
        (
            "invalid-utf8",
            b"study_id\n\xff\n",
        ),
        (
            "nul-byte",
            b"study_id\nSTUDY\x00" b"001\n",
        ),
        (
            "empty",
            b"",
        ),
    )

    secret = (
        b"d4-f1a1-validation-status-test-secret-0001"
    )

    for label, content in stopped_cases:
        data_root = (
            tmp_path
            / label
            / "data"
        ).resolve()

        outer = create_app(
            data_root=data_root,
            csrf_secret=secret,
        )

        with TestClient(
            outer,
            base_url=_ORIGIN,
        ) as client:
            response = client.post(
                "/reviews",
                data={
                    "csrf_token": (
                        _f1_csrf_token(
                            client
                        )
                    ),
                    "profile_version": (
                        "0.2.0"
                    ),
                    "mapping_mode": (
                        "strict"
                    ),
                },
                files={
                    "input_file": (
                        label
                        + ".csv",
                        content,
                        "text/csv",
                    ),
                },
                headers={
                    "Origin": _ORIGIN,
                    "Sec-Fetch-Site": (
                        "same-origin"
                    ),
                },
                follow_redirects=False,
            )

            assert (
                response.status_code
                == 303
            )

            location = (
                response.headers[
                    "location"
                ]
            )

            run_id = location.rsplit(
                "/",
                1,
            )[-1]

            view = (
                outer
                ._app
                .state
                .review_workflow
                .result(
                    run_id
                )
            )

            assert (
                view.status
                == "SUCCEEDED"
            )

            assert (
                view.validation_status
                == "stopped_after_ingestion_finding"
            )

            assert (
                view.total_findings
                == 1
            )

            assert (
                view.evidence_available
                is True
            )

            result = client.get(
                location
            )

            assert (
                result.status_code
                == 200
            )

            visible = (
                _visible_text(
                    result.text
                )
                .lower()
            )

            assert (
                "execution status succeeded"
                in visible
            )

            assert (
                "validation status: "
                "stopped after ingestion finding"
                in visible
            )

            assert (
                "validation stopped after ingestion finding"
                in visible
            )

            assert (
                "later structural checks were not completed"
                in visible
            )

            assert (
                "1 structural finding"
                in visible
            )

            assert (
                "structural review completed"
                not in visible
            )

            assert (
                str(
                    data_root
                )
                not in result.text
            )

        restarted = create_app(
            data_root=data_root,
            csrf_secret=secret,
        )

        with TestClient(
            restarted,
            base_url=_ORIGIN,
        ) as client:
            result = client.get(
                location
            )

            assert (
                result.status_code
                == 200
            )

            visible = (
                _visible_text(
                    result.text
                )
                .lower()
            )

            assert (
                "execution status succeeded"
                in visible
            )

            assert (
                "validation status: "
                "stopped after ingestion finding"
                in visible
            )

            assert (
                "validation stopped after ingestion finding"
                in visible
            )

            assert (
                "structural review completed"
                not in visible
            )

    baseline = (
        Path(
            __file__
        )
        .resolve()
        .parents[
            1
        ]
        / "data"
        / "synthetic"
        / "baseline_valid.csv"
    ).read_bytes()

    data_root = (
        tmp_path
        / "completed"
        / "data"
    ).resolve()

    outer = create_app(
        data_root=data_root,
        csrf_secret=secret,
    )

    with TestClient(
        outer,
        base_url=_ORIGIN,
    ) as client:
        response = client.post(
            "/reviews",
            data={
                "csrf_token": (
                    _f1_csrf_token(
                        client
                    )
                ),
                "profile_version": (
                    "0.2.0"
                ),
                "mapping_mode": (
                    "strict"
                ),
            },
            files={
                "input_file": (
                    "baseline_valid.csv",
                    baseline,
                    "text/csv",
                ),
            },
            headers={
                "Origin": _ORIGIN,
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
            },
            follow_redirects=False,
        )

        assert (
            response.status_code
            == 303
        )

        location = (
            response.headers[
                "location"
            ]
        )

        run_id = location.rsplit(
            "/",
            1,
        )[-1]

        view = (
            outer
            ._app
            .state
            .review_workflow
            .result(
                run_id
            )
        )

        assert (
            view.status
            == "SUCCEEDED"
        )

        assert (
            view.validation_status
            == "completed"
        )

        assert (
            view.total_findings
            == 0
        )

        result = client.get(
            location
        )

        assert (
            result.status_code
            == 200
        )

        visible = (
            _visible_text(
                result.text
            )
            .lower()
        )

        assert (
            "execution status succeeded"
            in visible
        )

        assert (
            "validation status: completed"
            in visible
        )

        assert (
            "structural review completed"
            in visible
        )

        assert (
            "validation stopped after ingestion finding"
            not in visible
        )


def test_detailed_baseline_result_exposes_verified_source_configuration_and_restart(
    tmp_path: Path,
) -> None:
    from hashlib import sha256

    data_root = (
        tmp_path
        / "detailed-baseline"
    ).resolve()

    source_bytes = (
        _BASELINE.read_bytes()
    )

    expected_sha = sha256(
        source_bytes
    ).hexdigest()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=_SECRET,
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
        )

        assert response.status_code == 303

        location = response.headers[
            "location"
        ]

        result = client.get(
            location
        )

        assert result.status_code == 200

        visible = _visible_text(
            result.text
        )

        for required in (
            "Source evidence",
            "baseline_valid.csv",
            expected_sha,
            str(
                len(
                    source_bytes
                )
            ),
            "Review configuration",
            "Profile version",
            "0.2.0",
            "Mapping mode",
            "strict",
            "Validation identity",
            "Summary counts",
            "Configured rules",
            "Column mapping",
            "Individual findings",
            "No individual findings were emitted",
            "Result artifact evidence",
        ):
            assert required in visible

        assert str(
            data_root
        ) not in result.text

        assert str(
            tmp_path
        ) not in result.text

    restarted = create_app(
        data_root=data_root,
        csrf_secret=_SECRET,
    )

    with TestClient(
        restarted,
        base_url=_ORIGIN,
    ) as client:
        result = client.get(
            location
        )

        assert result.status_code == 200

        visible = _visible_text(
            result.text
        )

        assert (
            "baseline_valid.csv"
            in visible
        )

        assert (
            expected_sha
            in visible
        )

        assert (
            "0 structural findings"
            in visible
        )


def test_detailed_seeded_result_exposes_four_reconciled_findings(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _SEEDED,
        )

        assert response.status_code == 303

        result = client.get(
            response.headers[
                "location"
            ]
        )

        assert result.status_code == 200

        visible = _visible_text(
            result.text
        )

        assert (
            "4 structural findings"
            in visible
        )

        assert (
            visible.count(
                "SCHEMA_MISSING_REQUIRED_COLUMN"
            )
            >= 1
        )

        assert (
            visible.count(
                "IDENTIFIER_DUPLICATE_SAMPLE_ID"
            )
            >= 2
        )

        assert (
            visible.count(
                "IDENTIFIER_MISSING_SAMPLE_ID"
            )
            >= 1
        )

        for rule_id in (
            "ingestion.input_limits",
            "ingestion.csv_parse",
            "schema.required_column",
            "identifier.sample_id_required",
            "identifier.sample_id_unique",
            "missingness.required_value",
        ):
            assert rule_id in visible

        for heading in (
            "Summary counts",
            "By category",
            "By code",
            "By severity",
            "By scope",
            "Individual findings",
        ):
            assert heading in visible


def test_detailed_required_value_result_exposes_missingness_findings(
    tmp_path: Path,
) -> None:
    source = (
        _ROOT
        / "data"
        / "synthetic"
        / "required_value_missing_values.csv"
    )

    assert source.is_file()

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            source,
        )

        assert response.status_code == 303

        result = client.get(
            response.headers[
                "location"
            ]
        )

        assert result.status_code == 200

        visible = _visible_text(
            result.text
        )

        assert (
            "3 structural findings"
            in visible
        )

        assert (
            visible.count(
                "MISSINGNESS_REQUIRED_VALUE"
            )
            >= 3
        )

        assert (
            "missingness.required_value"
            in visible
        )

        assert (
            "experimental_condition"
            in visible
        )

        assert (
            "sample_preparation_batch"
            in visible
        )

        assert (
            "protein_group_intensity_sum"
            in visible
        )


def test_detailed_explicit_mapping_result_exposes_mapping_evidence(
    tmp_path: Path,
) -> None:
    baseline_lines = (
        _BASELINE
        .read_text(
            encoding="utf-8"
        )
        .splitlines()
    )

    assert baseline_lines

    baseline_lines[
        0
    ] = (
        "study_id,"
        "Sample Name,"
        "Condition,"
        "sample_preparation_batch,"
        "quantified_protein_group_count,"
        "protein_group_intensity_sum"
    )

    source_bytes = (
        (
            "\n".join(
                baseline_lines
            )
            + "\n"
        )
        .encode(
            "utf-8"
        )
    )

    mapping_document = {
        "mapping_specification_version": (
            "1.0.0"
        ),
        "columns": {
            "sample_id": (
                "Sample Name"
            ),
            "experimental_condition": (
                "Condition"
            ),
        },
    }

    mapping_bytes = (
        json.dumps(
            mapping_document,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )
        .encode(
            "utf-8"
        )
    )

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        token = _csrf(
            client
        )

        response = client.post(
            "/reviews",
            data={
                "csrf_token": token,
                "profile_version": (
                    "0.2.0"
                ),
                "mapping_mode": (
                    "explicit"
                ),
            },
            files={
                "input_file": (
                    "explicit_alias.csv",
                    source_bytes,
                    "text/csv",
                ),
                "mapping_file": (
                    "mapping.json",
                    mapping_bytes,
                    "application/json",
                ),
            },
            headers={
                "Origin": _ORIGIN,
                "Sec-Fetch-Site": (
                    "same-origin"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303

        result = client.get(
            response.headers[
                "location"
            ]
        )

        assert result.status_code == 200

        visible = _visible_text(
            result.text
        )

        for required in (
            "explicit_alias.csv",
            "Mapping source evidence",
            "mapping.json",
            "Mapping mode explicit",
            "Sample Name",
            "sample_id",
            "Condition",
            "experimental_condition",
            "1.0.0",
        ):
            assert required in visible

        assert (
            "0 structural findings"
            in visible
        )


def test_detailed_result_escapes_source_name_and_does_not_leak_private_path(
    tmp_path: Path,
) -> None:
    data_root = (
        tmp_path
        / "escape-result"
    ).resolve()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=_SECRET,
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _BASELINE,
            filename=(
                "<source&name>.csv"
            ),
        )

        assert response.status_code == 303

        result = client.get(
            response.headers[
                "location"
            ]
        )

        assert result.status_code == 200

        assert (
            "&lt;source&amp;name&gt;.csv"
            in result.text
        )

        assert (
            "<source&name>.csv"
            not in result.text
        )

        assert (
            str(
                tmp_path
            )
            not in result.text
        )

        assert (
            str(
                data_root
            )
            not in result.text
        )


def test_detailed_result_fails_closed_when_verified_artifact_is_corrupted(
    tmp_path: Path,
) -> None:
    data_root = (
        tmp_path
        / "corrupt-evidence"
    ).resolve()

    with TestClient(
        create_app(
            data_root=data_root,
            csrf_secret=_SECRET,
        ),
        base_url=_ORIGIN,
    ) as client:
        response = _submit(
            client,
            _SEEDED,
        )

        assert response.status_code == 303

        location = response.headers[
            "location"
        ]

        run_id = location.rsplit(
            "/",
            1,
        )[-1]

    with sqlite3.connect(
        data_root
        / "ledger.sqlite3"
    ) as connection:
        row = connection.execute(
            """
            SELECT relative_path
            FROM run_artifact
            WHERE run_id = ?
              AND kind = 'RESULT_BUNDLE'
            """,
            (
                run_id,
            ),
        ).fetchone()

    assert row is not None

    artifact_path = (
        data_root
        / "artifacts"
        / row[
            0
        ]
    )

    assert artifact_path.is_file()

    artifact_path.write_bytes(
        b"{}\n"
    )

    restarted = create_app(
        data_root=data_root,
        csrf_secret=_SECRET,
    )

    with TestClient(
        restarted,
        base_url=_ORIGIN,
    ) as client:
        result = client.get(
            location
        )

        assert result.status_code == 503

        visible = _visible_text(
            result.text
        )

        assert (
            "Review evidence unavailable"
            in visible
        )

        assert (
            "Detailed review evidence is withheld"
            in visible
        )

        assert (
            "SCHEMA_MISSING_REQUIRED_COLUMN"
            not in visible
        )

        assert (
            "seeded_errors.csv"
            not in visible
        )

    assert (
        "No scientific conclusion should be inferred from this state."
        in visible
    )



def test_detailed_mapping_evidence_rejects_impossible_domain_states() -> None:
    from copy import deepcopy

    from proteomics_csv_validation.application.browser_review import (
        _mapping_view,
    )

    valid = {
        "specification_version": "1.0.0",
        "mode": "explicit",
        "resolution_completed": True,
        "entries": [
            {
                "source_field": "Sample Name",
                "target_field": "sample_id",
            },
            {
                "source_field": "Condition",
                "target_field": "experimental_condition",
            },
        ],
    }

    accepted = _mapping_view(
        deepcopy(
            valid
        )
    )

    assert len(
        accepted.entries
    ) == 2

    duplicate_target = deepcopy(
        valid
    )

    duplicate_target[
        "entries"
    ][
        1
    ][
        "target_field"
    ] = "sample_id"

    duplicate_source = deepcopy(
        valid
    )

    duplicate_source[
        "entries"
    ][
        1
    ][
        "source_field"
    ] = "Sample Name"

    identity_mapping = deepcopy(
        valid
    )

    identity_mapping[
        "entries"
    ][
        0
    ] = {
        "source_field": "sample_id",
        "target_field": "sample_id",
    }

    incomplete_with_entries = deepcopy(
        valid
    )

    incomplete_with_entries[
        "resolution_completed"
    ] = False

    attacks = {
        "duplicate_target": duplicate_target,
        "duplicate_source": duplicate_source,
        "identity_mapping": identity_mapping,
        "incomplete_with_entries": incomplete_with_entries,
    }

    for label, document in attacks.items():
        try:
            _mapping_view(
                document
            )

        except ValueError:
            continue

        raise AssertionError(
            "Impossible mapping evidence was accepted: "
            + label
        )


def _history_direct_service(
    *,
    runs,
    configurations,
):
    from types import SimpleNamespace

    from proteomics_csv_validation.application.browser_review import (
        ReviewWorkflowService,
    )
    from proteomics_csv_validation.domain.run_lifecycle import (
        LedgerRecordNotFoundError,
    )

    class Lifecycle:
        def __init__(self):
            self.last_list_request = None

        def list_runs(
            self,
            workspace_id,
            *,
            limit,
        ):
            self.last_list_request = (
                workspace_id,
                limit,
            )

            return tuple(
                runs
            )

        def get_configuration(
            self,
            configuration_id,
        ):
            value = configurations.get(
                configuration_id
            )

            if value is None:
                raise LedgerRecordNotFoundError(
                    "Run configuration does not exist."
                )

            return value

    lifecycle = Lifecycle()

    service = ReviewWorkflowService(
        lifecycle=lifecycle,
        execution=SimpleNamespace(),
        publication=SimpleNamespace(),
        result_reader=SimpleNamespace(),
    )

    return lifecycle, service


def _history_direct_run(
    *,
    run_id="1" * 32,
    configuration_id="a" * 32,
    workspace_id="local-default",
):
    from types import SimpleNamespace

    from proteomics_csv_validation.domain.run_lifecycle import (
        RunState,
    )

    return SimpleNamespace(
        run_id=run_id,
        workspace_id=workspace_id,
        configuration_id=configuration_id,
        status=RunState.SUCCEEDED,
        created_at="2026-01-01T00:00:00Z",
        queued_at="2026-01-01T00:00:00Z",
        started_at="2026-01-01T00:01:00Z",
        finished_at="2026-01-01T00:02:00Z",
        cancel_requested_at=None,
    )


def _history_direct_configuration(
    document,
    *,
    configuration_id="a" * 32,
    workspace_id="local-default",
    sha256_override=None,
):
    from hashlib import sha256
    import json
    from types import SimpleNamespace

    canonical = (
        document
        if isinstance(
            document,
            str,
        )
        else json.dumps(
            document,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )
    )

    digest = sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest()

    return SimpleNamespace(
        configuration_id=configuration_id,
        workspace_id=workspace_id,
        source_draft_id=None,
        source_draft_revision=None,
        canonical_json=canonical,
        sha256=(
            digest
            if sha256_override is None
            else sha256_override
        ),
        created_at="2026-01-01T00:00:00Z",
    )


def _history_valid_document(
    *,
    display_name="history.csv",
    mapping_mode="strict",
):
    from hashlib import sha256

    document = {
        "mapping_mode": mapping_mode,
        "profile_version": "0.2.0",
        "source": {
            "byte_count": 10,
            "display_name": display_name,
            "sha256": sha256(
                b"history"
            ).hexdigest(),
        },
    }

    if mapping_mode == "explicit":
        document[
            "column_mapping_source"
        ] = {
            "byte_count": 5,
            "display_name": "mapping.json",
            "sha256": sha256(
                b"map"
            ).hexdigest(),
        }

    return document


def test_history_empty_is_accessible_no_store_and_discoverable(
    tmp_path: Path,
) -> None:
    outer = _application(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=_ORIGIN,
    ) as client:
        review = client.get(
            "/review"
        )

        assert review.status_code == 200
        assert 'href="/history"' in review.text

        response = client.get(
            "/history"
        )

        assert response.status_code == 200

        assert (
            "no-store"
            in response.headers[
                "cache-control"
            ]
        )

        assert (
            "No review runs are available yet"
            in response.text
        )

        assert (
            "Open run record"
            not in response.text
        )


def test_history_lists_durable_identity_newest_first_with_reopen_links(
    tmp_path: Path,
) -> None:
    from hashlib import sha256
    import sqlite3

    outer = _application(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=_ORIGIN,
    ) as client:
        first = _submit(
            client,
            _BASELINE,
            filename="older-history.csv",
        )

        second = _submit(
            client,
            _BASELINE,
            filename="newer-history.csv",
        )

        assert first.status_code == 303
        assert second.status_code == 303

        first_run = (
            first.headers[
                "location"
            ].rsplit(
                "/",
                1,
            )[-1]
        )

        second_run = (
            second.headers[
                "location"
            ].rsplit(
                "/",
                1,
            )[-1]
        )

        response = client.get(
            "/history"
        )

        assert response.status_code == 200

        assert (
            response.text.index(
                "newer-history.csv"
            )
            < response.text.index(
                "older-history.csv"
            )
        )

        assert "SUCCEEDED" in response.text
        assert "0.2.0" in response.text
        assert "strict" in response.text

        source_sha = sha256(
            _BASELINE.read_bytes()
        ).hexdigest()

        assert source_sha in response.text

        assert (
            f'href="/results/{first_run}"'
            in response.text
        )

        assert (
            f'href="/results/{second_run}"'
            in response.text
        )

        database = (
            tmp_path
            / "app-data"
            / "ledger.sqlite3"
        )

        with sqlite3.connect(
            database
        ) as connection:
            row = connection.execute(
                """
                SELECT
                    run_configuration.sha256
                FROM analysis_run
                JOIN run_configuration
                  ON run_configuration.configuration_id
                   = analysis_run.configuration_id
                WHERE analysis_run.run_id = ?
                """,
                (
                    second_run,
                ),
            ).fetchone()

        assert row is not None
        assert row[0] in response.text


def test_history_persists_across_restart_and_excludes_other_workspace(
    tmp_path: Path,
) -> None:
    from hashlib import sha256
    import json

    outer = _application(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=_ORIGIN,
    ) as client:
        submitted = _submit(
            client,
            _BASELINE,
            filename="persistent-history.csv",
        )

        assert submitted.status_code == 303

        service = (
            outer
            ._app
            .state
            .review_workflow
            ._get_service()
        )

        lifecycle = service._lifecycle

        lifecycle.ensure_workspace(
            "other-workspace"
        )

        document = {
            "mapping_mode": "strict",
            "profile_version": "0.2.0",
            "source": {
                "byte_count": 1,
                "display_name": "other-workspace.csv",
                "sha256": sha256(
                    b"x"
                ).hexdigest(),
            },
        }

        lifecycle.snapshot_configuration(
            "e" * 32,
            "other-workspace",
            json.dumps(
                document,
                sort_keys=True,
                separators=(
                    ",",
                    ":",
                ),
            ),
        )

        lifecycle.queue_run(
            "f" * 32,
            "other-workspace",
            "e" * 32,
        )

    restarted = _application(
        tmp_path
    )

    with TestClient(
        restarted,
        base_url=_ORIGIN,
    ) as client:
        response = client.get(
            "/history"
        )

        assert response.status_code == 200
        assert "persistent-history.csv" in response.text
        assert "other-workspace.csv" not in response.text


def test_history_escapes_source_display_and_does_not_leak_private_path(
    tmp_path: Path,
) -> None:
    outer = _application(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=_ORIGIN,
    ) as client:
        submitted = _submit(
            client,
            _BASELINE,
            filename="<b onclick=alert(1)>.csv",
        )

        assert submitted.status_code == 303

        response = client.get(
            "/history"
        )

        assert response.status_code == 200

        assert (
            "&lt;b onclick=alert(1)&gt;.csv"
            in response.text
        )

        assert (
            "<b onclick=alert(1)>.csv"
            not in response.text
        )

        assert (
            str(
                tmp_path
            )
            not in response.text
        )


def test_history_application_uses_fixed_workspace_and_limit(
) -> None:
    lifecycle, service = (
        _history_direct_service(
            runs=(),
            configurations={},
        )
    )

    assert service.history() == ()

    assert (
        lifecycle.last_list_request
        == (
            "local-default",
            50,
        )
    )


def test_history_application_accepts_explicit_configuration_without_bundle_read(
) -> None:
    run = _history_direct_run()

    configuration = (
        _history_direct_configuration(
            _history_valid_document(
                mapping_mode="explicit"
            )
        )
    )

    _, service = (
        _history_direct_service(
            runs=(
                run,
            ),
            configurations={
                run.configuration_id: configuration,
            },
        )
    )

    entries = service.history()

    assert len(entries) == 1

    assert (
        entries[
            0
        ].mapping_mode
        == "explicit"
    )

    assert (
        entries[
            0
        ].source_display_name
        == "history.csv"
    )


def test_history_application_fails_closed_for_invalid_configuration_evidence(
) -> None:
    from copy import deepcopy

    import pytest

    from proteomics_csv_validation.application.browser_review import (
        ReviewHistoryUnavailable,
    )

    run = _history_direct_run()
    valid = _history_valid_document()

    cases = [
        _history_direct_configuration(
            valid,
            sha256_override="0" * 64,
        ),
        _history_direct_configuration(
            "{",
        ),
    ]

    missing_source = deepcopy(
        valid
    )
    del missing_source["source"]

    cases.append(
        _history_direct_configuration(
            missing_source
        )
    )

    path_source = deepcopy(
        valid
    )
    path_source[
        "source"
    ][
        "display_name"
    ] = "private/path.csv"

    cases.append(
        _history_direct_configuration(
            path_source
        )
    )

    bad_source_sha = deepcopy(
        valid
    )
    bad_source_sha[
        "source"
    ][
        "sha256"
    ] = "x" * 64

    cases.append(
        _history_direct_configuration(
            bad_source_sha
        )
    )

    bad_byte_count = deepcopy(
        valid
    )
    bad_byte_count[
        "source"
    ][
        "byte_count"
    ] = -1

    cases.append(
        _history_direct_configuration(
            bad_byte_count
        )
    )

    bad_profile = deepcopy(
        valid
    )
    bad_profile[
        "profile_version"
    ] = ""

    cases.append(
        _history_direct_configuration(
            bad_profile
        )
    )

    bad_mapping = deepcopy(
        valid
    )
    bad_mapping[
        "mapping_mode"
    ] = "unsupported"

    cases.append(
        _history_direct_configuration(
            bad_mapping
        )
    )

    explicit_missing_mapping = deepcopy(
        valid
    )
    explicit_missing_mapping[
        "mapping_mode"
    ] = "explicit"

    cases.append(
        _history_direct_configuration(
            explicit_missing_mapping
        )
    )

    nonexplicit_extra_mapping = deepcopy(
        valid
    )
    nonexplicit_extra_mapping[
        "column_mapping_source"
    ] = {
        "byte_count": 1,
        "display_name": "mapping.json",
        "sha256": "1" * 64,
    }

    cases.append(
        _history_direct_configuration(
            nonexplicit_extra_mapping
        )
    )

    cases.append(
        _history_direct_configuration(
            valid,
            workspace_id="other-workspace",
        )
    )

    for configuration in cases:
        _, service = (
            _history_direct_service(
                runs=(
                    run,
                ),
                configurations={
                    run.configuration_id: configuration,
                },
            )
        )

        with pytest.raises(
            ReviewHistoryUnavailable
        ):
            service.history()

    wrong_workspace_run = (
        _history_direct_run(
            workspace_id="other-workspace"
        )
    )

    _, wrong_workspace_service = (
        _history_direct_service(
            runs=(
                wrong_workspace_run,
            ),
            configurations={
                wrong_workspace_run.configuration_id: (
                    _history_direct_configuration(
                        valid,
                        configuration_id=(
                            wrong_workspace_run.configuration_id
                        ),
                        workspace_id="other-workspace",
                    )
                ),
            },
        )
    )

    with pytest.raises(
        ReviewHistoryUnavailable
    ):
        wrong_workspace_service.history()

    _, missing_service = (
        _history_direct_service(
            runs=(
                run,
            ),
            configurations={},
        )
    )

    with pytest.raises(
        ReviewHistoryUnavailable
    ):
        missing_service.history()


def test_history_http_503_withholds_partial_rows_on_integrity_failure(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from proteomics_csv_validation.domain.run_lifecycle import (
        RunState,
    )

    outer = _application(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=_ORIGIN,
    ) as client:
        service = (
            outer
            ._app
            .state
            .review_workflow
            ._get_service()
        )

        good_run = SimpleNamespace(
            run_id="1" * 32,
            workspace_id="local-default",
            configuration_id="a" * 32,
            status=RunState.SUCCEEDED,
            created_at="2026-01-01T00:01:00Z",
            queued_at="2026-01-01T00:01:00Z",
            started_at=None,
            finished_at=None,
            cancel_requested_at=None,
        )

        bad_run = SimpleNamespace(
            run_id="2" * 32,
            workspace_id="local-default",
            configuration_id="b" * 32,
            status=RunState.FAILED,
            created_at="2026-01-01T00:02:00Z",
            queued_at="2026-01-01T00:02:00Z",
            started_at=None,
            finished_at=None,
            cancel_requested_at=None,
        )

        good_configuration = (
            _history_direct_configuration(
                _history_valid_document(
                    display_name=(
                        "visible-if-partial.csv"
                    )
                ),
                configuration_id=(
                    good_run.configuration_id
                ),
            )
        )

        bad_configuration = (
            _history_direct_configuration(
                _history_valid_document(
                    display_name=(
                        "bad-history.csv"
                    )
                ),
                configuration_id=(
                    bad_run.configuration_id
                ),
                sha256_override="0" * 64,
            )
        )

        class CorruptLifecycle:
            def list_runs(
                self,
                workspace_id,
                *,
                limit,
            ):
                assert (
                    workspace_id
                    == "local-default"
                )

                assert limit == 50

                return (
                    bad_run,
                    good_run,
                )

            def get_configuration(
                self,
                configuration_id,
            ):
                return {
                    good_run.configuration_id: (
                        good_configuration
                    ),
                    bad_run.configuration_id: (
                        bad_configuration
                    ),
                }[
                    configuration_id
                ]

        service._lifecycle = (
            CorruptLifecycle()
        )

        response = client.get(
            "/history"
        )

        assert response.status_code == 503

        assert (
            "Review history unavailable"
            in response.text
        )

        assert (
            "visible-if-partial.csv"
            not in response.text
        )

        assert (
            "bad-history.csv"
            not in response.text
        )

        assert (
            "no-store"
            in response.headers[
                "cache-control"
            ]
        )


class _CeCsrfParser:
    def __init__(self) -> None:
        from html.parser import HTMLParser

        class _Parser(HTMLParser):
            def __init__(
                inner_self,
            ) -> None:
                super().__init__()
                inner_self.values: list[
                    str
                ] = []

            def handle_starttag(
                inner_self,
                tag: str,
                attrs,
            ) -> None:
                if tag.casefold() != "input":
                    return

                values = dict(
                    attrs
                )

                if (
                    values.get(
                        "name"
                    )
                    == "csrf_token"
                    and values.get(
                        "value"
                    )
                ):
                    inner_self.values.append(
                        values[
                            "value"
                        ]
                    )

        self.parser = _Parser()

    def feed(
        self,
        text: str,
    ) -> tuple[str, ...]:
        self.parser.feed(
            text
        )

        return tuple(
            self.parser.values
        )


def _ce_outer(
    tmp_path,
):
    from proteomics_csv_validation.web.composition import (
        create_app,
    )

    return create_app(
        data_root=(
            tmp_path
            / "state"
        ),
        csrf_secret=(
            b"0123456789abcdef"
            b"0123456789abcdef"
        ),
    )


def _ce_fixture(
    name: str,
):
    from pathlib import Path

    return (
        Path(__file__)
        .resolve()
        .parents[1]
        / "data"
        / "synthetic"
        / name
    )


def _ce_token(
    client,
) -> str:
    response = client.get(
        "/review"
    )

    assert response.status_code == 200

    values = _CeCsrfParser().feed(
        response.text
    )

    assert len(
        values
    ) == 1

    return values[
        0
    ]


def _ce_submit(
    client,
    path,
    filename: str,
) -> str:
    response = client.post(
        "/reviews",
        data={
            "csrf_token": (
                _ce_token(
                    client
                )
            ),
            "profile_version": "0.2.0",
            "mapping_mode": "strict",
        },
        files={
            "input_file": (
                filename,
                path.read_bytes(),
                "text/csv",
            ),
        },
        headers={
            "Origin": (
                "http://127.0.0.1:8000"
            ),
            "Sec-Fetch-Site": (
                "same-origin"
            ),
        },
    )

    assert response.status_code == 303

    location = response.headers[
        "location"
    ]

    assert location.startswith(
        "/results/"
    )

    return location.rsplit(
        "/",
        1,
    )[-1]


def _ce_service(
    outer,
):
    return (
        outer
        ._app
        .state
        .review_workflow
        ._get_service()
    )


def _ce_queue_run(
    service,
    *,
    run_id: str = "d" * 32,
    configuration_id: str = "e" * 32,
) -> str:
    import json

    lifecycle = (
        service._lifecycle
    )

    lifecycle.ensure_workspace(
        "local-default"
    )

    document = {
        "mapping_mode": "strict",
        "profile_version": "0.2.0",
        "source": {
            "byte_count": 0,
            "display_name": (
                "queued.csv"
            ),
            "sha256": "0" * 64,
        },
    }

    lifecycle.snapshot_configuration(
        configuration_id,
        "local-default",
        json.dumps(
            document,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )

    lifecycle.queue_run(
        run_id,
        "local-default",
        configuration_id,
    )

    return run_id


class _CeBrokenResultReader:
    def read_verified(
        self,
        relative_path,
        *,
        expected_sha256,
        expected_byte_count,
    ):
        raise ValueError(
            "verified evidence unavailable"
        )


def test_compare_exact_multiset_preserves_multiplicity(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    from proteomics_csv_validation.application.browser_review import (
        _exact_finding_multiset,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        run_id = _ce_submit(
            client,
            _ce_fixture(
                "seeded_errors.csv"
            ),
            "multiplicity.csv",
        )

        result = (
            _ce_service(
                outer
            ).result(
                run_id
            )
        )

        assert result.validation is not None

        finding = (
            result
            .validation
            .findings[
                0
            ]
        )

        common, left_only, right_only = (
            _exact_finding_multiset(
                (
                    finding,
                    finding,
                ),
                (
                    finding,
                ),
            )
        )

        assert common == (
            finding,
        )

        assert left_only == (
            finding,
        )

        assert right_only == ()


def test_compare_preserves_display_identity_and_source_byte_identity(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        fixture = _ce_fixture(
            "seeded_errors.csv"
        )

        left_id = _ce_submit(
            client,
            fixture,
            "left-display.csv",
        )

        right_id = _ce_submit(
            client,
            fixture,
            "right-display.csv",
        )

        comparison = (
            _ce_service(
                outer
            ).compare(
                left_id,
                right_id,
            )
        )

        assert (
            comparison.same_source_bytes
            is True
        )

        assert (
            comparison
            .left
            .configuration
            is not None
        )

        assert (
            comparison
            .right
            .configuration
            is not None
        )

        assert (
            comparison
            .left
            .configuration
            .source
            .display_name
            == "left-display.csv"
        )

        assert (
            comparison
            .right
            .configuration
            .source
            .display_name
            == "right-display.csv"
        )


def test_compare_summary_delta_is_right_minus_left_and_labels_are_sorted(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        left_id = _ce_submit(
            client,
            _ce_fixture(
                "baseline_valid.csv"
            ),
            "baseline.csv",
        )

        right_id = _ce_submit(
            client,
            _ce_fixture(
                "seeded_errors.csv"
            ),
            "seeded.csv",
        )

        comparison = (
            _ce_service(
                outer
            ).compare(
                left_id,
                right_id,
            )
        )

        assert (
            comparison
            .total_findings
            .delta
            ==
            (
                comparison
                .total_findings
                .right_count
                -
                comparison
                .total_findings
                .left_count
            )
        )

        for values in (
            comparison.category_counts,
            comparison.code_counts,
            comparison.severity_counts,
            comparison.scope_counts,
        ):
            labels = [
                value.label
                for value in values
            ]

            assert labels == sorted(
                labels
            )

            for value in values:
                assert (
                    value.delta
                    ==
                    value.right_count
                    - value.left_count
                )


def test_compare_rejects_same_run(
    tmp_path,
):
    import pytest

    from starlette.testclient import (
        TestClient,
    )

    from proteomics_csv_validation.application.browser_review import (
        ReviewComparisonInvalid,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        run_id = _ce_submit(
            client,
            _ce_fixture(
                "baseline_valid.csv"
            ),
            "same.csv",
        )

        with pytest.raises(
            ReviewComparisonInvalid
        ):
            _ce_service(
                outer
            ).compare(
                run_id,
                run_id,
            )


def test_compare_rejects_non_successful_run(
    tmp_path,
):
    import pytest

    from starlette.testclient import (
        TestClient,
    )

    from proteomics_csv_validation.application.browser_review import (
        ReviewComparisonIneligible,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        success_id = _ce_submit(
            client,
            _ce_fixture(
                "baseline_valid.csv"
            ),
            "success.csv",
        )

        service = _ce_service(
            outer
        )

        queued_id = _ce_queue_run(
            service
        )

        with pytest.raises(
            ReviewComparisonIneligible
        ):
            service.compare(
                queued_id,
                success_id,
            )


def test_compare_fails_closed_when_verified_evidence_is_unavailable(
    tmp_path,
):
    import pytest

    from starlette.testclient import (
        TestClient,
    )

    from proteomics_csv_validation.application.browser_review import (
        ReviewComparisonUnavailable,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        fixture = _ce_fixture(
            "baseline_valid.csv"
        )

        left_id = _ce_submit(
            client,
            fixture,
            "left.csv",
        )

        right_id = _ce_submit(
            client,
            fixture,
            "right.csv",
        )

        service = _ce_service(
            outer
        )

        service._result_reader = (
            _CeBrokenResultReader()
        )

        with pytest.raises(
            ReviewComparisonUnavailable
        ):
            service.compare(
                left_id,
                right_id,
            )


def test_export_result_returns_exact_bytes_without_new_publication_state(
    tmp_path,
):
    import sqlite3

    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        run_id = _ce_submit(
            client,
            _ce_fixture(
                "seeded_errors.csv"
            ),
            "export.csv",
        )

        service = _ce_service(
            outer
        )

        artifacts_before = (
            service
            ._publication
            .list_artifacts(
                run_id
            )
        )

        assert len(
            artifacts_before
        ) == 1

        artifact = (
            artifacts_before[
                0
            ]
        )

        expected = (
            service
            ._result_reader
            .read_verified(
                artifact.relative_path,
                expected_sha256=(
                    artifact.sha256
                ),
                expected_byte_count=(
                    artifact.byte_count
                ),
            )
        )

        database = (
            service
            ._lifecycle
            .repository
            .database_path
        )

        with sqlite3.connect(
            database
        ) as connection:
            attempts_before = (
                connection.execute(
                    "SELECT COUNT(*) FROM export_attempt"
                ).fetchone()[0]
            )

        exported = (
            service.export_result(
                run_id
            )
        )

        assert (
            exported.payload
            == expected
        )

        assert (
            exported.sha256
            == artifact.sha256
        )

        assert (
            exported.byte_count
            == artifact.byte_count
        )

        assert (
            exported.media_type
            == "application/json"
        )

        assert (
            exported.filename
            ==
            "result-bundle-"
            + run_id
            + ".json"
        )

        artifacts_after = (
            service
            ._publication
            .list_artifacts(
                run_id
            )
        )

        with sqlite3.connect(
            database
        ) as connection:
            attempts_after = (
                connection.execute(
                    "SELECT COUNT(*) FROM export_attempt"
                ).fetchone()[0]
            )

        assert (
            attempts_before
            == attempts_after
            == 0
        )

        assert (
            artifacts_after
            == artifacts_before
        )


def test_export_result_rejects_non_successful_run(
    tmp_path,
):
    import pytest

    from starlette.testclient import (
        TestClient,
    )

    from proteomics_csv_validation.application.browser_review import (
        ReviewExportIneligible,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ):
        service = _ce_service(
            outer
        )

        run_id = _ce_queue_run(
            service
        )

        with pytest.raises(
            ReviewExportIneligible
        ):
            service.export_result(
                run_id
            )


def test_compare_page_empty_is_accessible_and_no_store(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        response = client.get(
            "/compare"
        )

        assert response.status_code == 200

        assert (
            'for="left-run"'
            in response.text
        )

        assert (
            'for="right-run"'
            in response.text
        )

        assert (
            'name="left"'
            in response.text
        )

        assert (
            'name="right"'
            in response.text
        )

        assert (
            "no-store"
            in response.headers[
                "cache-control"
            ]
        )


def test_compare_http_rejects_malformed_and_same_ids(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        malformed = client.get(
            "/compare",
            params={
                "left": "bad",
                "right": "f" * 32,
            },
        )

        assert malformed.status_code == 400

        same = client.get(
            "/compare",
            params={
                "left": "a" * 32,
                "right": "a" * 32,
            },
        )

        assert same.status_code == 400


def test_compare_http_missing_run_is_404(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        response = client.get(
            "/compare",
            params={
                "left": "a" * 32,
                "right": "b" * 32,
            },
        )

        assert response.status_code == 404


def test_compare_http_success_escapes_source_identity_and_renders_evidence(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        fixture = _ce_fixture(
            "seeded_errors.csv"
        )

        left_id = _ce_submit(
            client,
            fixture,
            "<svg onload=alert(1)>.csv",
        )

        right_id = _ce_submit(
            client,
            fixture,
            "right.csv",
        )

        response = client.get(
            "/compare",
            params={
                "left": left_id,
                "right": right_id,
            },
        )

        assert response.status_code == 200

        assert "<svg" not in response.text

        assert (
            "&lt;svg"
            in response.text
        )

        assert left_id in response.text
        assert right_id in response.text

        assert (
            "Same source bytes:"
            in response.text
        )

        assert (
            "right minus left"
            in response.text
        )

        assert (
            "quality, improvement, regression, or biological meaning"
            in response.text
        )


def test_export_http_returns_exact_bytes_and_download_headers(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        run_id = _ce_submit(
            client,
            _ce_fixture(
                "seeded_errors.csv"
            ),
            "download.csv",
        )

        expected = (
            _ce_service(
                outer
            ).export_result(
                run_id
            )
        )

        response = client.get(
            "/results/"
            + run_id
            + "/export"
        )

        assert response.status_code == 200

        assert (
            response.content
            == expected.payload
        )

        assert (
            response.headers[
                "content-type"
            ].startswith(
                "application/json"
            )
        )

        assert (
            response.headers[
                "content-disposition"
            ]
            ==
            (
                'attachment; filename="'
                + expected.filename
                + '"'
            )
        )

        assert (
            "no-store"
            in response.headers[
                "cache-control"
            ]
        )


def test_export_http_malformed_and_missing_run_are_404(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        malformed = client.get(
            "/results/bad/export"
        )

        assert malformed.status_code == 404

        missing = client.get(
            "/results/"
            + "a" * 32
            + "/export"
        )

        assert missing.status_code == 404


def test_compare_http_non_successful_run_is_409(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        success_id = _ce_submit(
            client,
            _ce_fixture(
                "baseline_valid.csv"
            ),
            "success.csv",
        )

        service = _ce_service(
            outer
        )

        queued_id = _ce_queue_run(
            service
        )

        response = client.get(
            "/compare",
            params={
                "left": queued_id,
                "right": success_id,
            },
        )

        assert response.status_code == 409


def test_export_http_non_successful_run_is_409(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        service = _ce_service(
            outer
        )

        queued_id = _ce_queue_run(
            service
        )

        response = client.get(
            "/results/"
            + queued_id
            + "/export"
        )

        assert response.status_code == 409


def test_compare_http_unavailable_evidence_is_503(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        fixture = _ce_fixture(
            "baseline_valid.csv"
        )

        left_id = _ce_submit(
            client,
            fixture,
            "left.csv",
        )

        right_id = _ce_submit(
            client,
            fixture,
            "right.csv",
        )

        service = _ce_service(
            outer
        )

        service._result_reader = (
            _CeBrokenResultReader()
        )

        response = client.get(
            "/compare",
            params={
                "left": left_id,
                "right": right_id,
            },
        )

        assert response.status_code == 503


def test_export_http_unavailable_evidence_is_503(
    tmp_path,
):
    from starlette.testclient import (
        TestClient,
    )

    outer = _ce_outer(
        tmp_path
    )

    with TestClient(
        outer,
        base_url=(
            "http://127.0.0.1:8000"
        ),
        follow_redirects=False,
    ) as client:
        run_id = _ce_submit(
            client,
            _ce_fixture(
                "baseline_valid.csv"
            ),
            "unavailable.csv",
        )

        service = _ce_service(
            outer
        )

        service._result_reader = (
            _CeBrokenResultReader()
        )

        response = client.get(
            "/results/"
            + run_id
            + "/export"
        )

        assert response.status_code == 503


def test_compare_export_web_architecture_and_template_guards():
    from pathlib import Path

    root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    web = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "review.py"
    ).read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "sqlite3",
        "SQLiteRunRepository",
        "json.loads",
        "FilesystemResultStore",
        "read_verified",
    ):
        assert forbidden not in web

    compare = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "compare.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "<script" not in (
        compare.casefold()
    )

    assert "|safe" not in compare

    assert (
        "quality, improvement, regression, or biological meaning"
        in compare
    )

    history = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "history.html"
    ).read_text(
        encoding="utf-8"
    )

    result = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "result.html"
    ).read_text(
        encoding="utf-8"
    )

    assert 'href="/compare"' in history

    assert (
        "/results/{{ result.run_id }}/export"
        in result
    )

    assert (
        "/compare?left={{ result.run_id }}"
        in result
    )


def test_result_missing_get_uses_application_shell_error(
    tmp_path,
) -> None:
    from fastapi.testclient import TestClient

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.get(
            "/results/not-a-run"
        )

    assert response.status_code == 404
    assert "<nav" in response.text
    assert (
        "Review result not found"
        in response.text
    )
    assert (
        response.headers[
            "cache-control"
        ]
        == "no-store"
    )


def test_compare_get_error_retains_selections_in_application_shell(
    tmp_path,
) -> None:
    from fastapi.testclient import TestClient

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.get(
            "/compare",
            params={
                "left": "not-a-run",
                "right": "also-not-a-run",
            },
        )

    assert response.status_code == 400
    assert "<nav" in response.text
    assert (
        "Comparison could not be completed"
        in response.text
    )
    assert (
        'value="not-a-run"'
        in response.text
    )
    assert (
        'value="also-not-a-run"'
        in response.text
    )
    assert (
        response.headers[
            "cache-control"
        ]
        == "no-store"
    )


def test_export_missing_get_uses_application_shell_error(
    tmp_path,
) -> None:
    from fastapi.testclient import TestClient

    unknown = (
        "a"
        * 32
    )

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.get(
            (
                "/results/"
                + unknown
                + "/export"
            )
        )

    assert response.status_code == 404
    assert "<nav" in response.text
    assert (
        "Result Bundle export unavailable"
        in response.text
    )
    assert (
        "content-disposition"
        not in response.headers
    )
    assert (
        response.headers[
            "cache-control"
        ]
        == "no-store"
    )


def test_hardened_post_rejection_remains_plain_text(
    tmp_path,
) -> None:
    from fastapi.testclient import TestClient

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        response = client.post(
            "/reviews",
            content=(
                b"not-a-multipart-form"
            ),
            headers={
                "Content-Type": (
                    "application/octet-stream"
                ),
            },
        )

    assert response.status_code == 403
    assert response.text == "Forbidden"
    assert "<html" not in (
        response.text.casefold()
    )


def test_user_facing_get_error_architecture_stays_presentation_only() -> None:
    from pathlib import Path

    root = (
        Path(
            __file__
        )
        .resolve()
        .parents[
            1
        ]
    )

    web = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "review.py"
    ).read_text(
        encoding="utf-8"
    )

    compare = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "compare.html"
    ).read_text(
        encoding="utf-8"
    )

    error = (
        root
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "error.html"
    ).read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "sqlite3",
        "SQLiteRunRepository",
        "json.loads",
        "FilesystemResultStore",
        "read_verified",
    ):
        assert forbidden not in web

    for retired_plain_get_message in (
        '"Not found"',
        '"Comparison run ID was not accepted."',
        '"Comparison requires two distinct runs."',
        '"Comparison request was not accepted."',
        '"Comparison run not found."',
        '"Comparison requires completed successful reviews."',
        '"Comparison evidence is unavailable."',
        '"Result not found."',
        '"Result is not eligible for export."',
        '"Result export evidence is unavailable."',
    ):
        assert retired_plain_get_message not in web

    assert '"Forbidden"' in web
    assert (
        '"Invalid multipart request."'
        in web
    )

    assert 'name="error.html"' in web
    assert 'name="compare.html"' in web

    assert "{{ error_message }}" in compare
    assert "compare-error-title" in compare

    assert "{% extends \"base.html\" %}" in error

    assert "<script" not in (
        compare.casefold()
    )
    assert "<script" not in (
        error.casefold()
    )

    assert "|safe" not in compare
    assert "|safe" not in error


def test_input_browser_filename_length_boundary_is_explicit(
    tmp_path: Path,
) -> None:
    def filename_of_length(
        length: int,
    ) -> str:
        suffix = ".csv"

        return (
            "x"
            * (
                length
                - len(suffix)
            )
            + suffix
        )

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        accepted = _submit(
            client,
            _BASELINE,
            filename=filename_of_length(
                255
            ),
        )

        assert accepted.status_code == 303

        rejected = _submit(
            client,
            _BASELINE,
            filename=filename_of_length(
                256
            ),
        )

        assert rejected.status_code == 422

        visible = _visible_text(
            rejected.text
        )

        assert (
            "The selected filename must be 255 characters or fewer."
            in visible
        )

        assert (
            "The review input must use a .csv filename."
            not in visible
        )


def test_mapping_browser_filename_length_boundary_is_explicit(
    tmp_path: Path,
) -> None:
    def filename_of_length(
        length: int,
    ) -> str:
        suffix = ".json"

        return (
            "x"
            * (
                length
                - len(suffix)
            )
            + suffix
        )

    source_bytes = (
        _BASELINE
        .read_bytes()
        .replace(
            b"sample_id",
            b"Sample Name",
            1,
        )
    )

    mapping_bytes = json.dumps(
        {
            "mapping_specification_version":
                "1.0.0",
            "columns": {
                "sample_id":
                    "Sample Name",
            },
        },
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    def submit_mapping(
        client: TestClient,
        filename: str,
    ):
        return client.post(
            "/reviews",
            data={
                "csrf_token":
                    _csrf(
                        client
                    ),
                "profile_version":
                    "0.2.0",
                "mapping_mode":
                    "explicit",
            },
            files={
                "input_file": (
                    "mapped.csv",
                    source_bytes,
                    "text/csv",
                ),
                "mapping_file": (
                    filename,
                    mapping_bytes,
                    "application/json",
                ),
            },
            headers={
                "Origin":
                    _ORIGIN,
                "Sec-Fetch-Site":
                    "same-origin",
            },
            follow_redirects=False,
        )

    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        accepted = submit_mapping(
            client,
            filename_of_length(
                255
            ),
        )

        assert accepted.status_code == 303

        rejected = submit_mapping(
            client,
            filename_of_length(
                256
            ),
        )

        assert rejected.status_code == 422

        visible = _visible_text(
            rejected.text
        )

        assert (
            "The selected filename must be 255 characters or fewer."
            in visible
        )

        assert (
            "The mapping input must use a .json filename."
            not in visible
        )


def test_compare_renders_entity_key_display_values_without_object_repr(
    tmp_path: Path,
) -> None:
    with TestClient(
        _application(
            tmp_path
        ),
        base_url=_ORIGIN,
    ) as client:
        left_response = _submit(
            client,
            _BASELINE,
        )

        right_response = _submit(
            client,
            _SEEDED,
        )

        assert left_response.status_code == 303
        assert right_response.status_code == 303

        left = (
            left_response
            .headers["location"]
            .rsplit(
                "/",
                1,
            )[-1]
        )

        right = (
            right_response
            .headers["location"]
            .rsplit(
                "/",
                1,
            )[-1]
        )

        response = client.get(
            (
                "/compare?left="
                + left
                + "&right="
                + right
            )
        )

        assert response.status_code == 200

        visible = _visible_text(
            response.text
        )

        assert (
            "ResultTaggedValueView"
            not in visible
        )

        assert (
            "sample_id=S003"
            in visible
        )


def test_compare_technical_tokens_have_targeted_wrap_contract(
) -> None:
    template = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "compare.html"
    ).read_text(
        encoding="utf-8"
    )

    css = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "static"
        / "app.css"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        (
            '<div class="compare-technical-token">'
            '<strong>Code:</strong> '
            '{{ finding.code }}</div>'
        )
        in template
    )

    assert (
        (
            '<span class="compare-technical-token">'
            '{{ key.field_name }}='
            '{{ key.value.display_value }}'
            '</span>'
        )
        in template
    )

    assert re.search(
        (
            r"\.compare-technical-token\s*"
            r"\{[^}]*"
            r"overflow-wrap\s*:\s*anywhere"
        ),
        css,
        re.S,
    )


def test_compare_page_has_scoped_inherited_wrap_contract(
) -> None:
    template = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "templates"
        / "compare.html"
    ).read_text(
        encoding="utf-8"
    )

    css = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "web"
        / "static"
        / "app.css"
    ).read_text(
        encoding="utf-8"
    )

    wrapper_count = template.count(
        '<div class="compare-page">'
    )

    scoped_rule = (
        re.search(
            (
                r"\.compare-page\s*"
                r"\{[^}]*"
                r"overflow-wrap\s*:\s*anywhere"
            ),
            css,
            re.S,
        )
        is not None
    )

    broad_wrap_absent = all(
        re.search(
            pattern,
            css,
            re.S,
        )
        is None
        for pattern in (
            (
                r"\.result-panel\s+div\s*"
                r"\{[^}]*overflow-wrap"
            ),
            (
                r"\.result-panel\s+strong\s*"
                r"\{[^}]*overflow-wrap"
            ),
            (
                r"\.evidence-grid\s+div\s*"
                r"\{[^}]*overflow-wrap"
            ),
        )
    )

    assert (
        wrapper_count,
        scoped_rule,
        broad_wrap_absent,
    ) == (
        1,
        True,
        True,
    )

def test_compare_malformed_side_error_identifies_actual_side(
    tmp_path,
) -> None:
    """Malformed comparison input identifies the actual side in error."""

    from starlette.testclient import TestClient

    from proteomics_csv_validation.web.composition import (
        create_app,
    )

    app = create_app(
        data_root=tmp_path / "state",
        csrf_secret=(
            b"compare-side-error-regression-"
            b"0123456789abcdef0123456789abcdef"
        ),
    )

    valid_left = "a" * 32
    valid_right = "b" * 32

    with TestClient(
        app,
        base_url="http://localhost",
        follow_redirects=False,
    ) as client:

        left_invalid = client.get(
            "/compare",
            params={
                "left": "malformed-left",
                "right": valid_right,
            },
        )

        assert left_invalid.status_code == 400

        assert (
            "Left run ID is not a valid review run ID. "
            "Enter a valid review run ID for the left comparison side."
            in left_invalid.text
        )


        right_invalid = client.get(
            "/compare",
            params={
                "left": valid_left,
                "right": "malformed-right",
            },
        )

        assert right_invalid.status_code == 400

        assert (
            "Right run ID is not a valid review run ID. "
            "Enter a valid review run ID for the right comparison side."
            in right_invalid.text
        )


        both_invalid = client.get(
            "/compare",
            params={
                "left": "malformed-left",
                "right": "malformed-right",
            },
        )

        assert both_invalid.status_code == 400

        assert (
            "Left run ID and Right run ID are not valid review run IDs. "
            "Enter a valid review run ID for each comparison side."
            in both_invalid.text
        )


        only_left = client.get(
            "/compare",
            params={
                "left": valid_left,
            },
        )

        assert only_left.status_code == 200
        assert valid_left in only_left.text


        only_right = client.get(
            "/compare",
            params={
                "right": valid_right,
            },
        )

        assert only_right.status_code == 200
        assert valid_right in only_right.text
