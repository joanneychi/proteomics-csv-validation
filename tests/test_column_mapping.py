"""Tests for deterministic source-column resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proteomics_csv_validation.column_mapping import (
    COLUMN_MAPPING_SPECIFICATION_VERSION,
    pending_column_mapping_evidence,
    resolve_column_mapping,
)
from proteomics_csv_validation.errors import (
    ColumnMappingError,
)
from proteomics_csv_validation.models import (
    ColumnMappingMode,
    ParsedRecord,
    ParsedTable,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


def _table(
    header: tuple[str, ...],
) -> ParsedTable:
    return ParsedTable(
        input_name="mapped.csv",
        header=header,
        records=(
            ParsedRecord(
                row_number=2,
                values={
                    name: f"value-{index}"
                    for index, name
                    in enumerate(
                        header,
                        start=1,
                    )
                },
            ),
        ),
    )


def _write_map(
    path: Path,
    columns: dict[str, str],
    *,
    version: str = COLUMN_MAPPING_SPECIFICATION_VERSION,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "mapping_specification_version": version,
                "columns": columns,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def test_strict_mode_preserves_table_exactly(
    default_profile: ProfileDefinition,
) -> None:
    """Strict resolution performs no implicit header renaming."""

    table = _table(
        (
            "study_id",
            "sample_id",
        )
    )

    resolved, evidence = resolve_column_mapping(
        table,
        default_profile,
    )

    assert resolved == table
    assert evidence.mode is ColumnMappingMode.STRICT
    assert evidence.resolution_completed is True
    assert evidence.entries == ()


def test_automatic_mode_resolves_lexical_variants_and_profile_titles(
    default_profile: ProfileDefinition,
) -> None:
    """Automatic mapping is limited to canonical lexical forms and titles."""

    table = _table(
        (
            "STUDY ID",
            "Sample identifier",
            "Experimental-Condition",
            "Sample Preparation Batch",
            "Quantified Protein Group Count",
            "Protein-Group Intensity Sum",
        )
    )

    resolved, evidence = resolve_column_mapping(
        table,
        default_profile,
        auto_map=True,
    )

    assert resolved.header == tuple(
        field.name
        for field in default_profile.fields
    )

    assert tuple(
        (
            entry.source_field,
            entry.target_field,
        )
        for entry in evidence.entries
    ) == (
        (
            "STUDY ID",
            "study_id",
        ),
        (
            "Sample identifier",
            "sample_id",
        ),
        (
            "Experimental-Condition",
            "experimental_condition",
        ),
        (
            "Sample Preparation Batch",
            "sample_preparation_batch",
        ),
        (
            "Quantified Protein Group Count",
            "quantified_protein_group_count",
        ),
        (
            "Protein-Group Intensity Sum",
            "protein_group_intensity_sum",
        ),
    )

    assert evidence.mode is ColumnMappingMode.AUTOMATIC
    assert evidence.resolution_completed is True

    assert tuple(
        resolved.records[0].values.values()
    ) == tuple(
        table.records[0].values.values()
    )

    assert (
        resolved.records[0].row_number
        == table.records[0].row_number
    )


def test_automatic_mode_rejects_multiple_sources_for_one_target(
    default_profile: ProfileDefinition,
) -> None:
    """Two lexical variants for one canonical field are ambiguous."""

    table = _table(
        (
            "Sample ID",
            "Sample-ID",
        )
    )

    with pytest.raises(
        ColumnMappingError,
        match="multiple source columns",
    ):
        resolve_column_mapping(
            table,
            default_profile,
            auto_map=True,
        )


def test_automatic_mode_rejects_collision_with_canonical_field(
    default_profile: ProfileDefinition,
) -> None:
    """Automatic mapping never shadows an already canonical field."""

    table = _table(
        (
            "sample_id",
            "Sample ID",
        )
    )

    with pytest.raises(
        ColumnMappingError,
        match="collide",
    ):
        resolve_column_mapping(
            table,
            default_profile,
            auto_map=True,
        )


def test_explicit_partial_mapping_preserves_unmapped_columns(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Explicit mapping may resolve a subset while retaining other headers."""

    table = _table(
        (
            "Study",
            "Sample Name",
            "unrelated",
        )
    )

    mapping_path = _write_map(
        tmp_path / "mapping.json",
        {
            "study_id": "Study",
            "sample_id": "Sample Name",
        },
    )

    resolved, evidence = resolve_column_mapping(
        table,
        default_profile,
        column_map=mapping_path,
    )

    assert resolved.header == (
        "study_id",
        "sample_id",
        "unrelated",
    )

    assert evidence.mode is ColumnMappingMode.EXPLICIT

    assert tuple(
        entry.target_field
        for entry in evidence.entries
    ) == (
        "study_id",
        "sample_id",
    )


@pytest.mark.parametrize(
    (
        "columns",
        "message",
    ),
    (
        (
            {
                "unknown_field": "Study",
            },
            "unknown profile field",
        ),
        (
            {
                "study_id": "Missing",
            },
            "absent",
        ),
        (
            {
                "study_id": "sample_id",
            },
            "repurpose",
        ),
    ),
)
def test_explicit_mapping_rejects_invalid_contracts(
    tmp_path: Path,
    default_profile: ProfileDefinition,
    columns: dict[str, str],
    message: str,
) -> None:
    """Explicit mappings reject unknown, absent, and canonical-repurposing input."""

    table = _table(
        (
            "Study",
            "sample_id",
        )
    )

    mapping_path = _write_map(
        tmp_path / "mapping.json",
        columns,
    )

    with pytest.raises(
        ColumnMappingError,
        match=message,
    ):
        resolve_column_mapping(
            table,
            default_profile,
            column_map=mapping_path,
        )


def test_explicit_mapping_rejects_duplicate_json_keys(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Strict JSON parsing rejects duplicate mapping keys."""

    table = _table(
        (
            "Study",
        )
    )

    path = tmp_path / "mapping.json"

    path.write_text(
        (
            "{"
            '"mapping_specification_version":"1.0.0",'
            '"columns":{"study_id":"Study","study_id":"Study"}'
            "}"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ColumnMappingError,
        match="strict JSON",
    ):
        resolve_column_mapping(
            table,
            default_profile,
            column_map=path,
        )


def test_explicit_mapping_rejects_unsupported_version(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Mapping files identify their supported specification version."""

    table = _table(
        (
            "Study",
        )
    )

    mapping_path = _write_map(
        tmp_path / "mapping.json",
        {
            "study_id": "Study",
        },
        version="9.9.9",
    )

    with pytest.raises(
        ColumnMappingError,
        match="Unsupported",
    ):
        resolve_column_mapping(
            table,
            default_profile,
            column_map=mapping_path,
        )


def test_pending_evidence_rejects_both_mapping_modes(
    tmp_path: Path,
) -> None:
    """API callers cannot request automatic and explicit mapping together."""

    with pytest.raises(
        ColumnMappingError,
        match="cannot be requested together",
    ):
        pending_column_mapping_evidence(
            auto_map=True,
            column_map=tmp_path / "mapping.json",
        )
