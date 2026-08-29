"""HTTP workflow tests for the secure local Review vertical slice."""

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
            "nul",
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
