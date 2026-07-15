"""Tests for immutable profile-definition contracts."""

from __future__ import annotations

import pytest

from proteomics_csv_validation.profiles.models import (
    CsvDialectDefinition,
    FieldDefinition,
    LogicalType,
    MissingValuePolicy,
    ProfileDefinition,
)


def test_missing_value_policy_preserves_literal_na() -> None:
    """Generic text tokens are not silently converted to missing values."""

    policy = MissingValuePolicy(
        blank_is_missing=True,
        whitespace_only_is_missing=True,
    )

    assert policy.is_missing("")
    assert policy.is_missing("   ")
    assert not policy.is_missing("NA")
    assert not policy.is_missing("NULL")


def test_profile_rejects_duplicate_field_names() -> None:
    """Physical field names remain unique within a profile."""

    policy = MissingValuePolicy(
        blank_is_missing=True,
        whitespace_only_is_missing=True,
    )

    field = FieldDefinition(
        name="sample_id",
        title="Sample identifier",
        description="Synthetic sample identifier.",
        logical_type=LogicalType.STRING,
        required=True,
        missing_value_policy=policy,
    )

    dialect = CsvDialectDefinition(
        encoding="utf-8",
        delimiter=",",
        quote_character='"',
        header_required=True,
        allow_utf8_bom=True,
        allow_blank_records=False,
        allow_embedded_newlines=False,
        decimal_separator=".",
    )

    with pytest.raises(
        ValueError
    ):
        ProfileDefinition(
            descriptor_schema_version="1.0.0",
            profile_id="test",
            profile_version="1.0.0",
            entity_type="record",
            title="Test",
            description="Test profile.",
            record_grain="one row",
            file_grain="one file",
            fields=(
                field,
                field,
            ),
            key_fields=(
                "sample_id",
            ),
            factor_fields=(),
            batch_fields=(),
            metrics=(),
            csv_dialect=dialect,
        )
