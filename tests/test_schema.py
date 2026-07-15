"""Tests for required-column schema validation."""

from __future__ import annotations

from proteomics_csv_validation.models import (
    ParsedRecord,
    ParsedTable,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)
from proteomics_csv_validation.validators.schema import (
    validate_schema,
)


def test_all_required_columns_produce_no_schema_finding(
    default_profile: ProfileDefinition,
) -> None:
    """Column order does not control validity."""

    header = tuple(
        reversed(
            tuple(
                field.name
                for field
                in default_profile.required_fields
            )
        )
    )

    table = ParsedTable(
        input_name="reordered.csv",
        header=header,
        records=(
            ParsedRecord(
                row_number=2,
                values={
                    name: "synthetic"
                    for name in header
                },
            ),
        ),
    )

    assert validate_schema(
        table,
        default_profile,
    ) == ()


def test_each_missing_required_column_receives_one_finding(
    default_profile: ProfileDefinition,
) -> None:
    """Several missing fields follow deterministic profile order."""

    table = ParsedTable(
        input_name="missing.csv",
        header=(
            "sample_id",
        ),
        records=(
            ParsedRecord(
                row_number=2,
                values={
                    "sample_id": "S001",
                },
            ),
        ),
    )

    findings = validate_schema(
        table,
        default_profile,
    )

    assert tuple(
        finding.location.field_name
        for finding in findings
        if finding.location is not None
    ) == (
        "study_id",
        "experimental_condition",
        "sample_preparation_batch",
        "quantified_protein_group_count",
        "protein_group_intensity_sum",
    )
