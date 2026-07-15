"""Missing and duplicate sample-identifier validation."""

from __future__ import annotations

from collections import Counter

from proteomics_csv_validation.models import (
    EntityKeyPart,
    EntityReference,
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


SAMPLE_ID_REQUIRED_RULE = RuleReference(
    rule_id="identifier.sample_id_required",
    rule_version="1.0.0",
)

SAMPLE_ID_UNIQUE_RULE = RuleReference(
    rule_id="identifier.sample_id_unique",
    rule_version="1.0.0",
)

IDENTIFIER_RULES = (
    SAMPLE_ID_REQUIRED_RULE,
    SAMPLE_ID_UNIQUE_RULE,
)


def validate_identifiers(
    table: ParsedTable,
    profile: ProfileDefinition,
) -> tuple[Finding, ...]:
    """Validate exact case-sensitive sample identifiers by physical row."""

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

    identifier_field = "sample_id"

    if identifier_field not in (
        table.header
    ):
        return ()

    policy = (
        profile
        .field(
            identifier_field
        )
        .missing_value_policy
    )

    nonmissing_values = tuple(
        record.values[
            identifier_field
        ]
        for record
        in table.records
        if not policy.is_missing(
            record.values[
                identifier_field
            ]
        )
    )

    counts = Counter(
        nonmissing_values
    )

    findings: list[
        Finding
    ] = []

    for record in table.records:
        value = record.values[
            identifier_field
        ]

        location = SourceLocation(
            row_number=record.row_number,
            field_name=identifier_field,
        )

        if policy.is_missing(
            value
        ):
            findings.append(
                Finding(
                    code="IDENTIFIER_MISSING_SAMPLE_ID",
                    category=FindingCategory.IDENTIFIER,
                    severity=Severity.ERROR,
                    scope=Scope.ROW,
                    rule=SAMPLE_ID_REQUIRED_RULE,
                    location=location,
                    entity=None,
                    observed_value=value,
                    expected_value="nonmissing",
                    message=(
                        "The sample identifier is "
                        "missing for this record."
                    ),
                )
            )
            continue

        if counts[
            value
        ] > 1:
            findings.append(
                Finding(
                    code="IDENTIFIER_DUPLICATE_SAMPLE_ID",
                    category=FindingCategory.IDENTIFIER,
                    severity=Severity.ERROR,
                    scope=Scope.ROW,
                    rule=SAMPLE_ID_UNIQUE_RULE,
                    location=location,
                    entity=EntityReference(
                        entity_type=(
                            profile.entity_type
                        ),
                        key_parts=(
                            EntityKeyPart(
                                field_name=(
                                    identifier_field
                                ),
                                value=value,
                            ),
                        ),
                    ),
                    observed_value=value,
                    expected_value=(
                        "unique_within_input_file"
                    ),
                    message=(
                        "The sample identifier occurs "
                        "in more than one input record."
                    ),
                )
            )

    return tuple(
        findings
    )
