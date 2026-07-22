"""Tests for profile-driven required-value missingness validation."""

from __future__ import annotations

import pytest

from proteomics_csv_validation.models import (
    FindingCategory,
    ParsedRecord,
    ParsedTable,
    Scope,
    Severity,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)
from proteomics_csv_validation.validators.missingness import (
    REQUIRED_VALUE_RULE,
    validate_missingness,
)


_VALID_VALUES = {
    "study_id": "STUDY_SYNTH_001",
    "sample_id": "S001",
    "experimental_condition": "control",
    "sample_preparation_batch": "PREP01",
    "quantified_protein_group_count": "5120",
    "protein_group_intensity_sum": "128450000.25",
}


def _table(
    *rows: dict[str, str],
    header: tuple[str, ...] | None = None,
) -> ParsedTable:
    resolved_header = (
        tuple(
            _VALID_VALUES
        )
        if header is None
        else header
    )

    return ParsedTable(
        input_name="missingness.csv",
        header=resolved_header,
        records=tuple(
            ParsedRecord(
                row_number=row_number,
                values=row,
            )
            for row_number, row
            in enumerate(
                rows,
                start=2,
            )
        ),
    )


def test_complete_required_values_produce_no_missingness_finding(
    default_profile: ProfileDefinition,
) -> None:
    """Complete required values produce no row-scope evidence."""

    findings = validate_missingness(
        _table(
            dict(
                _VALID_VALUES
            )
        ),
        default_profile,
    )

    assert findings == ()


def test_blank_and_whitespace_values_follow_row_and_profile_order(
    default_profile: ProfileDefinition,
) -> None:
    """Missing values preserve raw text and deterministic locations."""

    first = dict(
        _VALID_VALUES
    )
    first[
        "experimental_condition"
    ] = ""

    second = dict(
        _VALID_VALUES
    )
    second[
        "sample_id"
    ] = "S002"
    second[
        "sample_preparation_batch"
    ] = "   "
    second[
        "protein_group_intensity_sum"
    ] = ""

    findings = validate_missingness(
        _table(
            first,
            second,
        ),
        default_profile,
    )

    assert tuple(
        (
            finding.location.row_number,
            finding.location.field_name,
            finding.observed_value,
        )
        for finding in findings
        if finding.location is not None
    ) == (
        (
            2,
            "experimental_condition",
            "",
        ),
        (
            3,
            "sample_preparation_batch",
            "   ",
        ),
        (
            3,
            "protein_group_intensity_sum",
            "",
        ),
    )


def test_required_value_finding_has_exact_contract(
    default_profile: ProfileDefinition,
) -> None:
    """One missing value returns complete structured evidence."""

    row = dict(
        _VALID_VALUES
    )
    row[
        "quantified_protein_group_count"
    ] = ""

    finding = validate_missingness(
        _table(
            row
        ),
        default_profile,
    )[0]

    assert finding.code == (
        "MISSINGNESS_REQUIRED_VALUE"
    )
    assert finding.category is (
        FindingCategory.MISSINGNESS
    )
    assert finding.severity is (
        Severity.ERROR
    )
    assert finding.scope is (
        Scope.ROW
    )
    assert finding.rule == (
        REQUIRED_VALUE_RULE
    )
    assert finding.location is not None
    assert finding.location.row_number == 2
    assert finding.location.field_name == (
        "quantified_protein_group_count"
    )
    assert finding.entity is not None
    assert finding.entity.entity_type == (
        "processed_sample_summary"
    )
    assert tuple(
        (
            part.field_name,
            part.value,
        )
        for part in finding.entity.key_parts
    ) == (
        (
            "sample_id",
            "S001",
        ),
    )
    assert finding.observed_value == ""
    assert finding.expected_value == (
        "nonmissing"
    )
    assert finding.message == (
        "A required profile value is missing "
        "for this record."
    )


def test_schema_and_identifier_owned_defects_are_not_double_reported(
    default_profile: ProfileDefinition,
) -> None:
    """Absent columns and sample IDs remain owned by other validators."""

    header = tuple(
        name
        for name in _VALID_VALUES
        if name != "study_id"
    )

    row = {
        name: value
        for name, value
        in _VALID_VALUES.items()
        if name != "study_id"
    }
    row[
        "sample_id"
    ] = ""

    findings = validate_missingness(
        _table(
            row,
            header=header,
        ),
        default_profile,
    )

    assert findings == ()


def test_missing_sample_identifier_prevents_entity_reference(
    default_profile: ProfileDefinition,
) -> None:
    """A second missing field remains reportable without an entity key."""

    row = dict(
        _VALID_VALUES
    )
    row[
        "sample_id"
    ] = ""
    row[
        "experimental_condition"
    ] = ""

    finding = validate_missingness(
        _table(
            row
        ),
        default_profile,
    )[0]

    assert finding.location is not None
    assert finding.location.field_name == (
        "experimental_condition"
    )
    assert finding.entity is None


def test_missingness_rejects_invalid_argument_types(
    default_profile: ProfileDefinition,
) -> None:
    """The public validator rejects unsupported argument types."""

    table = _table(
        dict(
            _VALID_VALUES
        )
    )

    with pytest.raises(
        TypeError,
        match=(
            "table must be a ParsedTable"
        ),
    ):
        validate_missingness(
            object(),
            default_profile,
        )

    with pytest.raises(
        TypeError,
        match=(
            "profile must be a ProfileDefinition"
        ),
    ):
        validate_missingness(
            table,
            object(),
        )
