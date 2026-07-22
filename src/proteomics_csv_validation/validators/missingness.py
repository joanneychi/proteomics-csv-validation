"""Required-value missingness validation against the active profile."""

from __future__ import annotations

from proteomics_csv_validation.models import (
    EntityKeyPart,
    EntityReference,
    Finding,
    FindingCategory,
    ParsedRecord,
    ParsedTable,
    RuleReference,
    Scope,
    Severity,
    SourceLocation,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


REQUIRED_VALUE_RULE = RuleReference(
    rule_id="missingness.required_value",
    rule_version="1.0.0",
)

MISSINGNESS_RULES = (
    REQUIRED_VALUE_RULE,
)


def _entity_reference(
    record: ParsedRecord,
    table: ParsedTable,
    profile: ProfileDefinition,
) -> EntityReference | None:
    """Return a complete nonmissing profile key for one record."""

    key_parts: list[
        EntityKeyPart
    ] = []

    for field_name in profile.key_fields:
        if field_name not in table.header:
            return None

        value = record.values[
            field_name
        ]

        policy = (
            profile
            .field(
                field_name
            )
            .missing_value_policy
        )

        if policy.is_missing(
            value
        ):
            return None

        key_parts.append(
            EntityKeyPart(
                field_name=field_name,
                value=value,
            )
        )

    if not key_parts:
        return None

    return EntityReference(
        entity_type=profile.entity_type,
        key_parts=tuple(
            key_parts
        ),
    )


def validate_missingness(
    table: ParsedTable,
    profile: ProfileDefinition,
) -> tuple[Finding, ...]:
    """Return row findings for missing required non-key values."""

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

    observed_fields = set(
        table.header
    )

    key_fields = set(
        profile.key_fields
    )

    applicable_fields = tuple(
        field
        for field
        in profile.required_fields
        if (
            field.name
            in observed_fields
            and field.name
            not in key_fields
        )
    )

    findings: list[
        Finding
    ] = []

    for record in table.records:
        entity = _entity_reference(
            record,
            table,
            profile,
        )

        for field in applicable_fields:
            value = record.values[
                field.name
            ]

            if not field.missing_value_policy.is_missing(
                value
            ):
                continue

            findings.append(
                Finding(
                    code=(
                        "MISSINGNESS_REQUIRED_VALUE"
                    ),
                    category=(
                        FindingCategory.MISSINGNESS
                    ),
                    severity=Severity.ERROR,
                    scope=Scope.ROW,
                    rule=REQUIRED_VALUE_RULE,
                    location=SourceLocation(
                        row_number=record.row_number,
                        field_name=field.name,
                    ),
                    entity=entity,
                    observed_value=value,
                    expected_value="nonmissing",
                    message=(
                        "A required profile value is "
                        "missing for this record."
                    ),
                )
            )

    return tuple(
        findings
    )
