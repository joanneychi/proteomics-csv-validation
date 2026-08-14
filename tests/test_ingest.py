"""Tests for CSV access, parsing, and source preservation."""

from __future__ import annotations

from pathlib import Path

import pytest

import proteomics_csv_validation.ingest as ingest_module
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
    """The default profile permits one logical record per physical line."""

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



def _assert_parse_failure(
    result: ParsedTable | IngestionFailure,
    *,
    message_fragment: str,
) -> None:
    """Check the stable file-scope CSV parse-failure contract."""

    assert isinstance(result, IngestionFailure)
    finding = result.finding
    assert finding.code == "INGESTION_CSV_PARSE_ERROR"
    assert finding.rule.rule_id == "ingestion.csv_parse"
    assert finding.rule.rule_version == "1.0.0"
    assert finding.observed_value is None
    assert finding.expected_value == "parseable_csv"
    assert message_fragment in finding.message


def _assert_limit_failure(
    result: ParsedTable | IngestionFailure,
    *,
    observed_value: int,
    expected_value: str,
    message_fragment: str,
) -> None:
    """Check the stable file-scope ingestion-limit contract."""

    assert isinstance(result, IngestionFailure)
    finding = result.finding
    assert finding.code == "INGESTION_INPUT_LIMIT_EXCEEDED"
    assert finding.rule.rule_id == "ingestion.input_limits"
    assert finding.rule.rule_version == "1.0.0"
    assert finding.observed_value == observed_value
    assert finding.expected_value == expected_value
    assert message_fragment in finding.message


def test_ingestion_rejects_invalid_argument_types(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Public ingestion arguments reject objects outside their contracts."""

    with pytest.raises(
        TypeError,
        match="input_path must be a pathlib.Path",
    ):
        ingest_csv(
            "input.csv",  # type: ignore[arg-type]
            default_profile,
        )

    with pytest.raises(
        TypeError,
        match="profile must be a ProfileDefinition",
    ):
        ingest_csv(
            tmp_path / "input.csv",
            object(),  # type: ignore[arg-type]
        )


def test_wrong_extension_raises_input_access_error(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Accessible non-CSV paths are rejected before parsing."""

    path = tmp_path / "input.txt"
    path.write_text("study_id\nSTUDY001\n", encoding="utf-8", newline="")

    with pytest.raises(
        InputAccessError,
        match=r"Input must use the \.csv extension",
    ):
        ingest_csv(path, default_profile)


def test_read_failure_is_translated_to_input_access_error(
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem read failures use the public input-access exception."""

    path = tmp_path / "unreadable.csv"
    path.write_text("study_id\nSTUDY001\n", encoding="utf-8", newline="")

    def fail_read(_path: Path) -> bytes:
        raise OSError("simulated read failure")

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    with pytest.raises(
        InputAccessError,
        match="Input could not be read",
    ) as error:
        ingest_csv(path, default_profile)

    assert isinstance(error.value.__cause__, OSError)


def test_utf8_bom_is_removed_before_header_parsing(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """The current profile accepts a UTF-8 BOM without changing field names."""

    path = tmp_path / "bom.csv"
    path.write_bytes(
        b"\xef\xbb\xbfstudy_id,sample_id\n"
        b"STUDY001,S001\n"
    )

    result = ingest_csv(path, default_profile)

    assert isinstance(result, ParsedTable)
    assert result.header == ("study_id", "sample_id")
    assert result.records[0].values["study_id"] == "STUDY001"


def test_invalid_utf8_becomes_reportable_parse_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Invalid UTF-8 bytes stop ingestion with a parse finding."""

    path = tmp_path / "invalid-utf8.csv"
    path.write_bytes(b"study_id\n\xff\n")

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="not valid UTF-8 text",
    )


def test_nul_character_becomes_reportable_parse_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """NUL characters are rejected before CSV record construction."""

    path = tmp_path / "nul.csv"
    path.write_bytes(b"study_id\nSTUDY\x00" b"001\n")

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="contains a NUL character",
    )


def test_malformed_csv_parser_error_becomes_reportable_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Strict CSV parser errors become stable ingestion findings."""

    path = tmp_path / "malformed.csv"
    path.write_text(
        "study_id,sample_id\n\"unterminated,S001\n",
        encoding="utf-8",
        newline="",
    )

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="CSV parser rejected malformed content",
    )


def test_bom_only_input_reports_missing_header(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """A BOM without CSV records does not satisfy the header contract."""

    path = tmp_path / "bom-only.csv"
    path.write_bytes(b"\xef\xbb\xbf")

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="does not contain a header",
    )


def test_all_empty_header_reports_missing_header(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """A parsed header containing only empty names is rejected."""

    path = tmp_path / "empty-header.csv"
    path.write_text(",,\n", encoding="utf-8", newline="")

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="CSV header is missing",
    )


def test_duplicate_header_names_become_reportable_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Duplicate physical column names are rejected before record mapping."""

    path = tmp_path / "duplicate-header.csv"
    path.write_text(
        "study_id,study_id\nSTUDY001,STUDY001\n",
        encoding="utf-8",
        newline="",
    )

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="header contains duplicate names",
    )


def test_byte_limit_accepts_boundary_and_rejects_excess(
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Byte-limit comparison accepts the maximum and rejects one byte more."""

    monkeypatch.setattr(ingest_module, "_MAX_INPUT_BYTES", 4)
    path = tmp_path / "bytes.csv"
    path.write_bytes(b"a\n1\n")

    assert isinstance(ingest_csv(path, default_profile), ParsedTable)

    path.write_bytes(b"a\n12\n")
    _assert_limit_failure(
        ingest_csv(path, default_profile),
        observed_value=5,
        expected_value="at_most_4_bytes",
        message_fragment="byte limit",
    )


def test_column_limit_accepts_boundary_and_rejects_excess(
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Column-limit comparison accepts the maximum and rejects one more."""

    monkeypatch.setattr(ingest_module, "_MAX_COLUMNS", 2)
    path = tmp_path / "columns.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8", newline="")

    assert isinstance(ingest_csv(path, default_profile), ParsedTable)

    path.write_text("a,b,c\n1,2,3\n", encoding="utf-8", newline="")
    _assert_limit_failure(
        ingest_csv(path, default_profile),
        observed_value=3,
        expected_value="at_most_2_columns",
        message_fragment="column limit",
    )


def test_row_limit_accepts_boundary_and_rejects_excess(
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row-limit comparison accepts the maximum and rejects one more."""

    monkeypatch.setattr(ingest_module, "_MAX_ROWS", 1)
    path = tmp_path / "rows.csv"
    path.write_text("a\n1\n", encoding="utf-8", newline="")

    assert isinstance(ingest_csv(path, default_profile), ParsedTable)

    path.write_text("a\n1\n2\n", encoding="utf-8", newline="")
    _assert_limit_failure(
        ingest_csv(path, default_profile),
        observed_value=2,
        expected_value="at_most_1_records",
        message_fragment="row limit",
    )


def test_blank_physical_record_becomes_reportable_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """The current profile rejects a blank physical record."""

    path = tmp_path / "blank-record.csv"
    path.write_text("a,b\n1,2\n\n3,4\n", encoding="utf-8", newline="")

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="Blank physical CSV records are unsupported",
    )


def test_record_width_mismatch_becomes_reportable_failure(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Every data record must contain the same field count as the header."""

    path = tmp_path / "width.csv"
    path.write_text("a,b\n1\n", encoding="utf-8", newline="")

    _assert_parse_failure(
        ingest_csv(path, default_profile),
        message_fragment="different field count than the header",
    )
