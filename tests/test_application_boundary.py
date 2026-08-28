"""Regression tests for the first application-service boundary."""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

import pytest

from proteomics_csv_validation.adapters import (
    LegacyCoreValidationAdapter,
)
from proteomics_csv_validation.application import (
    StructuralReviewRequest,
    StructuralReviewService,
)
from proteomics_csv_validation.errors import (
    ProfileNotFoundError,
)
from proteomics_csv_validation.pipeline import (
    validate_input,
)
from proteomics_csv_validation.profiles.loader import (
    load_default_profile,
    load_profile,
)


_ROOT = Path(__file__).resolve().parents[1]

_PACKAGE = (
    _ROOT
    / "src"
    / "proteomics_csv_validation"
)

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

_MISSINGNESS = (
    _ROOT
    / "data"
    / "synthetic"
    / "required_value_missing_values.csv"
)

_PROFILE_ID = (
    "proteomics_processed_sample_summary"
)


def _service() -> StructuralReviewService:
    return StructuralReviewService(
        engine=LegacyCoreValidationAdapter()
    )


def _profile(
    version: str | None,
):
    if version is None:
        return load_default_profile()

    return load_profile(
        _PROFILE_ID,
        version,
    )


def _direct(
    request: StructuralReviewRequest,
):
    return validate_input(
        request.input_path,
        _profile(
            request.profile_version
        ),
        auto_map=request.auto_map,
        column_map=request.column_map,
    )


def _write_reheadered_csv(
    source: Path,
    target: Path,
    header: list[str],
) -> None:
    with source.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.reader(handle)
        )

    if not rows:
        raise AssertionError(
            "source fixture unexpectedly empty"
        )

    if len(header) != len(rows[0]):
        raise AssertionError(
            "replacement header width mismatch"
        )

    with target.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            lineterminator="\n",
        )

        writer.writerow(header)
        writer.writerows(rows[1:])


def _imported_modules(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )

    modules: set[str] = set()

    for node in ast.walk(tree):
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


def test_default_strict_review_equals_existing_core():
    request = StructuralReviewRequest(
        input_path=_BASELINE
    )

    actual = _service().review(
        request
    )

    expected = _direct(
        request
    )

    assert actual == expected
    assert actual.profile_version == "0.2.0"
    assert actual.rows == 8
    assert actual.summary.total_findings == 0
    assert (
        actual.column_mapping.mode.value
        == "strict"
    )


def test_seeded_review_equals_existing_core():
    request = StructuralReviewRequest(
        input_path=_SEEDED
    )

    actual = _service().review(
        request
    )

    expected = _direct(
        request
    )

    assert actual == expected
    assert actual.summary.total_findings == 4
    assert {
        finding.code
        for finding in actual.findings
    } == {
        "SCHEMA_MISSING_REQUIRED_COLUMN",
        "IDENTIFIER_DUPLICATE_SAMPLE_ID",
        "IDENTIFIER_MISSING_SAMPLE_ID",
    }


def test_missingness_review_equals_existing_core():
    request = StructuralReviewRequest(
        input_path=_MISSINGNESS
    )

    actual = _service().review(
        request
    )

    expected = _direct(
        request
    )

    assert actual == expected
    assert actual.summary.total_findings == 3
    assert {
        finding.code
        for finding in actual.findings
    } == {
        "MISSINGNESS_REQUIRED_VALUE"
    }


def test_explicit_profile_selection_equals_existing_core():
    request = StructuralReviewRequest(
        input_path=_BASELINE,
        profile_version="0.3.0",
    )

    actual = _service().review(
        request
    )

    expected = _direct(
        request
    )

    assert actual == expected
    assert actual.profile_version == "0.3.0"
    assert actual.summary.total_findings == 0


def test_automatic_mapping_equals_existing_core(
    tmp_path: Path,
):
    profile = load_default_profile()

    automatic_input = (
        tmp_path
        / "automatic.csv"
    )

    _write_reheadered_csv(
        _BASELINE,
        automatic_input,
        [
            field.title
            for field in profile.fields
        ],
    )

    request = StructuralReviewRequest(
        input_path=automatic_input,
        auto_map=True,
    )

    actual = _service().review(
        request
    )

    expected = _direct(
        request
    )

    assert actual == expected
    assert (
        actual.column_mapping.mode.value
        == "automatic"
    )
    assert len(
        actual.column_mapping.entries
    ) == len(
        profile.fields
    )


def test_explicit_mapping_equals_existing_core(
    tmp_path: Path,
):
    profile = load_default_profile()

    explicit_input = (
        tmp_path
        / "explicit.csv"
    )

    source_names = [
        f"Source column {index}"
        for index, _field
        in enumerate(
            profile.fields,
            start=1,
        )
    ]

    _write_reheadered_csv(
        _BASELINE,
        explicit_input,
        source_names,
    )

    mapping = (
        tmp_path
        / "mapping.json"
    )

    mapping.write_text(
        json.dumps(
            {
                "mapping_specification_version":
                    "1.0.0",

                "columns": {
                    field.name:
                        source_name

                    for field, source_name
                    in zip(
                        profile.fields,
                        source_names,
                        strict=True,
                    )
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    request = StructuralReviewRequest(
        input_path=explicit_input,
        column_map=mapping,
    )

    actual = _service().review(
        request
    )

    expected = _direct(
        request
    )

    assert actual == expected
    assert (
        actual.column_mapping.mode.value
        == "explicit"
    )
    assert len(
        actual.column_mapping.entries
    ) == len(
        profile.fields
    )


def test_unknown_profile_version_preserves_existing_error():
    request = StructuralReviewRequest(
        input_path=_BASELINE,
        profile_version="99.0.0",
    )

    with pytest.raises(
        ProfileNotFoundError
    ):
        _service().review(
            request
        )


def test_application_layer_does_not_import_core_or_adapters():
    application = (
        _PACKAGE
        / "application"
    )

    forbidden = (
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.aggregate",
        "proteomics_csv_validation.cli",
        "proteomics_csv_validation.column_mapping",
        "proteomics_csv_validation.errors",
        "proteomics_csv_validation.ingest",
        "proteomics_csv_validation.models",
        "proteomics_csv_validation.pipeline",
        "proteomics_csv_validation.profiles",
        "proteomics_csv_validation.report",
        "proteomics_csv_validation.validators",
    )

    for path in application.rglob(
        "*.py"
    ):
        modules = _imported_modules(
            path
        )

        for module in modules:
            assert not module.startswith(
                forbidden
            ), (
                f"{path.name} imports "
                f"forbidden dependency "
                f"{module}"
            )


def test_existing_core_does_not_import_new_outer_layers():
    forbidden = (
        "proteomics_csv_validation.application",
        "proteomics_csv_validation.adapters",
    )

    for path in _PACKAGE.rglob(
        "*.py"
    ):
        if (
            "application"
            in path.parts
            or "adapters"
            in path.parts
        ):
            continue

        modules = _imported_modules(
            path
        )

        for module in modules:
            assert not module.startswith(
                forbidden
            ), (
                f"{path.name} imports "
                f"new outer layer "
                f"{module}"
            )
