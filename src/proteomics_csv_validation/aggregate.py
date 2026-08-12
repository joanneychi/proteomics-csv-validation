"""Deterministic finding aggregation and result construction."""

from __future__ import annotations

from collections import Counter

from proteomics_csv_validation.models import (
    CategoryCount,
    ColumnMappingEvidence,
    CodeCount,
    Finding,
    FindingCategory,
    FindingSummary,
    RuleReference,
    Scope,
    ScopeCount,
    Severity,
    SeverityCount,
    ValidationResult,
    ValidationStatus,
)


_CATEGORY_ORDER = tuple(
    FindingCategory
)

_SEVERITY_ORDER = tuple(
    Severity
)

_SCOPE_ORDER = tuple(
    Scope
)


def _finding_sort_key(
    finding: Finding,
    rule_rank: dict[
        RuleReference,
        int,
    ],
) -> tuple[
    int,
    int,
    int,
]:
    scope_rank = {
        Scope.FILE: 0,
        Scope.ROW: 1,
    }[
        finding.scope
    ]

    row_number = (
        finding.location.row_number
        if (
            finding.location is not None
            and finding.location.row_number
            is not None
        )
        else 0
    )

    return (
        scope_rank,
        row_number,
        rule_rank[
            finding.rule
        ],
    )


def aggregate_findings(
    findings: tuple[
        Finding,
        ...,
    ],
    configured_rules: tuple[
        RuleReference,
        ...,
    ],
) -> tuple[
    tuple[Finding, ...],
    FindingSummary,
]:
    """Validate provenance, order findings, and build complete counts."""

    if not isinstance(
        findings,
        tuple,
    ):
        raise TypeError(
            "findings must be a tuple."
        )

    if not isinstance(
        configured_rules,
        tuple,
    ):
        raise TypeError(
            "configured_rules must be a tuple."
        )

    if len(
        set(
            configured_rules
        )
    ) != len(
        configured_rules
    ):
        raise ValueError(
            "Configured rules must be unique."
        )

    configured = set(
        configured_rules
    )

    for finding in findings:
        if finding.rule not in configured:
            raise ValueError(
                "Finding rule is not present in "
                "configured_rules."
            )

    if len(
        set(
            findings
        )
    ) != len(
        findings
    ):
        raise ValueError(
            "Exact duplicate findings are not permitted."
        )

    rule_rank = {
        rule: index
        for index, rule
        in enumerate(
            configured_rules
        )
    }

    ordered = tuple(
        sorted(
            findings,
            key=lambda finding: (
                _finding_sort_key(
                    finding,
                    rule_rank,
                )
            ),
        )
    )

    category_counter = Counter(
        finding.category
        for finding
        in ordered
    )

    code_counter = Counter(
        finding.code
        for finding
        in ordered
    )

    severity_counter = Counter(
        finding.severity
        for finding
        in ordered
    )

    scope_counter = Counter(
        finding.scope
        for finding
        in ordered
    )

    observed_codes: list[
        str
    ] = []

    for finding in ordered:
        if (
            finding.code
            not in observed_codes
        ):
            observed_codes.append(
                finding.code
            )

    summary = FindingSummary(
        total_findings=len(
            ordered
        ),
        category_counts=tuple(
            CategoryCount(
                category=category,
                count=category_counter[
                    category
                ],
            )
            for category
            in _CATEGORY_ORDER
        ),
        code_counts=tuple(
            CodeCount(
                code=code,
                count=code_counter[
                    code
                ],
            )
            for code
            in observed_codes
        ),
        severity_counts=tuple(
            SeverityCount(
                severity=severity,
                count=severity_counter[
                    severity
                ],
            )
            for severity
            in _SEVERITY_ORDER
        ),
        scope_counts=tuple(
            ScopeCount(
                scope=scope,
                count=scope_counter[
                    scope
                ],
            )
            for scope
            in _SCOPE_ORDER
        ),
    )

    return (
        ordered,
        summary,
    )


def build_validation_result(
    *,
    application_version: str,
    descriptor_schema_version: str,
    profile_id: str,
    profile_version: str,
    input_name: str,
    status: ValidationStatus,
    rows: int,
    configured_rules: tuple[
        RuleReference,
        ...,
    ],
    findings: tuple[
        Finding,
        ...,
    ],
    column_mapping: ColumnMappingEvidence,
) -> ValidationResult:
    """Construct one immutable result from validated aggregate evidence."""

    ordered, summary = aggregate_findings(
        findings,
        configured_rules,
    )

    return ValidationResult(
        application_version=(
            application_version
        ),
        descriptor_schema_version=(
            descriptor_schema_version
        ),
        profile_id=profile_id,
        profile_version=profile_version,
        input_name=input_name,
        status=status,
        rows=rows,
        configured_rules=(
            configured_rules
        ),
        findings=ordered,
        summary=summary,
        column_mapping=column_mapping,
    )
