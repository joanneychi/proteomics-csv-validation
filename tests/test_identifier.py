"""Tests for exact missing and duplicate sample identifiers."""

from __future__ import annotations

from proteomics_csv_validation.models import (
    ParsedRecord,
    ParsedTable,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)
from proteomics_csv_validation.validators.identifier import (
    validate_identifiers,
)


def _table(
    values: tuple[str, ...],
) -> ParsedTable:
    return ParsedTable(
        input_name="identifiers.csv",
        header=(
            "sample_id",
        ),
        records=tuple(
            ParsedRecord(
                row_number=index,
                values={
                    "sample_id": value,
                },
            )
            for index, value
            in enumerate(
                values,
                start=2,
            )
        ),
    )


def test_duplicate_group_flags_every_affected_row(
    default_profile: ProfileDefinition,
) -> None:
    """Both occurrences of an exact duplicate receive evidence."""

    findings = validate_identifiers(
        _table(
            (
                "S003",
                "S003",
            )
        ),
        default_profile,
    )

    assert tuple(
        finding.location.row_number
        for finding in findings
        if finding.location is not None
    ) == (
        2,
        3,
    )


def test_missing_and_whitespace_only_identifiers_are_missing(
    default_profile: ProfileDefinition,
) -> None:
    """Blank interpretation is field-specific and preserves raw text."""

    findings = validate_identifiers(
        _table(
            (
                "",
                "   ",
            )
        ),
        default_profile,
    )

    assert tuple(
        finding.observed_value
        for finding in findings
    ) == (
        "",
        "   ",
    )


def test_identifier_comparison_is_exact_and_case_sensitive(
    default_profile: ProfileDefinition,
) -> None:
    """Whitespace and case are not silently normalized."""

    findings = validate_identifiers(
        _table(
            (
                "S001",
                "s001",
                " S001",
            )
        ),
        default_profile,
    )

    assert findings == ()
