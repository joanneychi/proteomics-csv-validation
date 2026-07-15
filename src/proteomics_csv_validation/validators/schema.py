"""Required-column validation against the active profile."""

from __future__ import annotations

from proteomics_csv_validation.models import (
    Finding,
    FindingCategory,
    ParsedTable,
    RuleReference,
    Scope,
    Severity,
    SourceLocation,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


REQUIRED_COLUMN_RULE = RuleReference(
    rule_id="schema.required_column",
    rule_version="1.0.0",
)

SCHEMA_RULES = (
    REQUIRED_COLUMN_RULE,
)


def validate_schema(
    table: ParsedTable,
    profile: ProfileDefinition,
) -> tuple[Finding, ...]:
    """Return one file-scope finding per missing required field."""

    if not isinstance(
        table,
        ParsedTable,
    ):
        raise TypeError(
            "table must be a ParsedTable."
        )

    if not isinstance(
        profile,
        ProfileDefinition,
    ):
        raise TypeError(
            "profile must be a ProfileDefinition."
        )

    observed = set(
        table.header
    )

    findings = tuple(
        Finding(
            code="SCHEMA_MISSING_REQUIRED_COLUMN",
            category=FindingCategory.SCHEMA,
            severity=Severity.ERROR,
            scope=Scope.FILE,
            rule=REQUIRED_COLUMN_RULE,
            location=SourceLocation(
                row_number=None,
                field_name=field.name,
            ),
            entity=None,
            observed_value=None,
            expected_value=field.name,
            message=(
                "A required profile column is "
                "absent from the input header."
            ),
        )
        for field
        in profile.required_fields
        if field.name not in observed
    )

    return findings
