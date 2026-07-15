"""Tests for deterministic aggregation and zero-inclusive summaries."""

from __future__ import annotations

from proteomics_csv_validation.aggregate import (
    aggregate_findings,
)
from proteomics_csv_validation.models import (
    Finding,
    FindingCategory,
    RuleReference,
    Scope,
    Severity,
    SourceLocation,
)


_RULE = RuleReference(
    rule_id="test.rule",
    rule_version="1.0.0",
)


def test_empty_summary_contains_every_dimension() -> None:
    """Zero-finding results retain all configured summary dimensions."""

    findings, summary = aggregate_findings(
        (),
        (
            _RULE,
        ),
    )

    assert findings == ()
    assert summary.total_findings == 0

    assert tuple(
        item.category.value
        for item in summary.category_counts
    ) == (
        "ingestion",
        "schema",
        "identifier",
    )

    assert all(
        item.count == 0
        for item in summary.category_counts
    )


def test_row_findings_are_sorted_by_physical_row() -> None:
    """Aggregation produces stable row ordering."""

    later = Finding(
        code="B",
        category=FindingCategory.IDENTIFIER,
        severity=Severity.ERROR,
        scope=Scope.ROW,
        rule=_RULE,
        location=SourceLocation(
            row_number=5,
            field_name="sample_id",
        ),
        entity=None,
        observed_value="S",
        expected_value="unique",
        message="Later.",
    )

    earlier = Finding(
        code="A",
        category=FindingCategory.IDENTIFIER,
        severity=Severity.ERROR,
        scope=Scope.ROW,
        rule=_RULE,
        location=SourceLocation(
            row_number=4,
            field_name="sample_id",
        ),
        entity=None,
        observed_value="S",
        expected_value="unique",
        message="Earlier.",
    )

    findings, _ = aggregate_findings(
        (
            later,
            earlier,
        ),
        (
            _RULE,
        ),
    )

    assert tuple(
        item.location.row_number
        for item in findings
        if item.location is not None
    ) == (
        4,
        5,
    )

def test_equal_location_findings_follow_configured_rule_order() -> None:
    """Configured rule priority resolves findings at the same location."""

    earlier_rule = RuleReference(
        rule_id="test.earlier",
        rule_version="1.0.0",
    )

    later_rule = RuleReference(
        rule_id="test.later",
        rule_version="1.0.0",
    )

    location = SourceLocation(
        row_number=4,
        field_name="sample_id",
    )

    later = Finding(
        code="LATER",
        category=FindingCategory.IDENTIFIER,
        severity=Severity.ERROR,
        scope=Scope.ROW,
        rule=later_rule,
        location=location,
        entity=None,
        observed_value="S003",
        expected_value="later",
        message="Later rule.",
    )

    earlier = Finding(
        code="EARLIER",
        category=FindingCategory.IDENTIFIER,
        severity=Severity.ERROR,
        scope=Scope.ROW,
        rule=earlier_rule,
        location=location,
        entity=None,
        observed_value="S003",
        expected_value="earlier",
        message="Earlier rule.",
    )

    findings, _ = aggregate_findings(
        (
            later,
            earlier,
        ),
        (
            earlier_rule,
            later_rule,
        ),
    )

    assert tuple(
        finding.code
        for finding in findings
    ) == (
        "EARLIER",
        "LATER",
    )
