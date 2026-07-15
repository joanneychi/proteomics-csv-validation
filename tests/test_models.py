"""Tests for immutable validation evidence models."""

from __future__ import annotations

import pytest

from proteomics_csv_validation.models import (
    Finding,
    FindingCategory,
    RuleReference,
    Scope,
    Severity,
    SourceLocation,
)


def test_row_scope_finding_requires_row_number() -> None:
    """Row evidence cannot omit its physical row."""

    with pytest.raises(
        ValueError
    ):
        Finding(
            code="TEST",
            category=FindingCategory.IDENTIFIER,
            severity=Severity.ERROR,
            scope=Scope.ROW,
            rule=RuleReference(
                rule_id="test.rule",
                rule_version="1.0.0",
            ),
            location=SourceLocation(
                row_number=None,
                field_name="sample_id",
            ),
            entity=None,
            observed_value=None,
            expected_value=None,
            message="Test message.",
        )
