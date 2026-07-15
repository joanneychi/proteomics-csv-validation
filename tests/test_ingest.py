"""Tests for CSV access, parsing, and source preservation."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteomics_csv_validation.errors import (
    InputAccessError,
)
from proteomics_csv_validation.ingest import (
    ingest_csv,
)
from proteomics_csv_validation.models import (
    IngestionFailure,
    ParsedTable,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


def test_baseline_ingestion_preserves_rows_and_source(
    baseline_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Eight records load without changing source bytes."""

    before = baseline_input_path.read_bytes()

    result = ingest_csv(
        baseline_input_path,
        default_profile,
    )

    assert isinstance(
        result,
        ParsedTable,
    )

    assert len(
        result.records
    ) == 8

    assert result.records[0].row_number == 2
    assert result.records[-1].row_number == 9
    assert baseline_input_path.read_bytes() == before


def test_empty_accessible_file_becomes_reportable_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Empty content is not confused with inaccessible input."""

    path = tmp_path / "empty.csv"
    path.write_bytes(b"")

    result = ingest_csv(
        path,
        default_profile,
    )

    assert isinstance(
        result,
        IngestionFailure,
    )

    assert (
        result.finding.code
        == "INGESTION_CSV_PARSE_ERROR"
    )


def test_missing_file_raises_input_access_error(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """An unavailable file remains an operational failure."""

    with pytest.raises(
        InputAccessError
    ):
        ingest_csv(
            tmp_path / "missing.csv",
            default_profile,
        )

def test_single_line_quoted_field_is_accepted(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Ordinary CSV quoting does not resemble an embedded line break."""

    path = (
        tmp_path
        / "quoted.csv"
    )

    path.write_text(
        (
            "study_id,sample_id,"
            "experimental_condition,"
            "sample_preparation_batch,"
            "quantified_protein_group_count,"
            "protein_group_intensity_sum\n"
            "\"STUDY,001\",S001,"
            "control,PREP01,1452,"
            "125000000.0\n"
        ),
        encoding="utf-8",
        newline="",
    )

    result = ingest_csv(
        path,
        default_profile,
    )

    assert isinstance(
        result,
        ParsedTable,
    )

    assert (
        result
        .records[
            0
        ]
        .values[
            "study_id"
        ]
        == "STUDY,001"
    )


def test_embedded_quoted_line_break_is_rejected(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Profile 0.1.0 permits one logical record per physical line."""

    path = (
        tmp_path
        / "embedded-newline.csv"
    )

    path.write_text(
        (
            "study_id,sample_id,"
            "experimental_condition,"
            "sample_preparation_batch,"
            "quantified_protein_group_count,"
            "protein_group_intensity_sum\n"
            "STUDY001,S001,\"control\n"
            "continued\",PREP01,1452,"
            "125000000.0\n"
        ),
        encoding="utf-8",
        newline="",
    )

    result = ingest_csv(
        path,
        default_profile,
    )

    assert isinstance(
        result,
        IngestionFailure,
    )

    assert (
        result.finding.code
        == "INGESTION_CSV_PARSE_ERROR"
    )

    assert (
        "Embedded quoted line breaks"
        in result.finding.message
    )
