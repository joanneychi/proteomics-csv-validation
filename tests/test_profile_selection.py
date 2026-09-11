"""Regression tests for versioned processed-sample profile selection."""

from __future__ import annotations

import csv
import json
from importlib import resources
from pathlib import Path

from proteomics_csv_validation import cli as cli_module
from proteomics_csv_validation.pipeline import validate_input
from proteomics_csv_validation.profiles.loader import (
    load_default_profile,
    load_profile,
)

PROFILE_ID = "proteomics_processed_sample_summary"

SIX_CANONICAL = (
    "study_id",
    "sample_id",
    "experimental_condition",
    "sample_preparation_batch",
    "quantified_protein_group_count",
    "protein_group_intensity_sum",
)
FOUR_CANONICAL = (
    "study_id",
    "sample_id",
    "quantified_protein_group_count",
    "protein_group_intensity_sum",
)
FOUR_TITLES = (
    "Study identifier",
    "Sample identifier",
    "Quantified protein-group count",
    "Protein-group intensity sum",
)


def _write(
    path: Path,
    header: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _reduced_profile():
    return load_profile(PROFILE_ID, "0.3.0")


def test_profile_0_3_0_resource_is_installed() -> None:
    resource = (
        resources.files("proteomics_csv_validation.profiles")
        .joinpath("data")
        .joinpath("proteomics_processed_sample_summary-0.3.0.json")
    )
    assert resource.is_file()


def test_default_profile_remains_six_field_0_2_0() -> None:
    profile = load_default_profile()
    assert profile.profile_version == "0.2.0"
    assert tuple(field.name for field in profile.required_fields) == SIX_CANONICAL


def test_profile_0_3_0_changes_only_metadata_requiredness() -> None:
    profile = _reduced_profile()
    assert tuple(field.name for field in profile.required_fields) == FOUR_CANONICAL
    assert profile.field("experimental_condition").required is False
    assert profile.field("sample_preparation_batch").required is False
    assert profile.factor_fields == ("experimental_condition",)
    assert profile.batch_fields == ("sample_preparation_batch",)


def test_four_column_canonical_record_is_valid_under_profile_0_3_0(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "four.csv",
        FOUR_CANONICAL,
        (("PXDTEST", "Experiment_A", "100", "12345.0"),),
    )
    result = validate_input(path, _reduced_profile())
    assert result.profile_version == "0.3.0"
    assert result.summary.total_findings == 0


def test_four_column_profile_titles_auto_map_under_profile_0_3_0(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "titles.csv",
        FOUR_TITLES,
        (("PXDTEST", "Experiment_A", "100", "12345.0"),),
    )
    result = validate_input(path, _reduced_profile(), auto_map=True)
    assert result.summary.total_findings == 0
    assert result.column_mapping.mode.value == "automatic"
    assert len(result.column_mapping.entries) == 4


def test_four_column_explicit_mapping_under_profile_0_3_0(tmp_path: Path) -> None:
    header = ("Study", "Experiment", "Protein Count", "Intensity Sum")
    path = _write(
        tmp_path / "explicit.csv",
        header,
        (("PXDTEST", "Experiment_A", "100", "12345.0"),),
    )
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mapping_specification_version": "1.0.0",
                "columns": dict(zip(FOUR_CANONICAL, header)),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    result = validate_input(path, _reduced_profile(), column_map=mapping)
    assert result.summary.total_findings == 0
    assert result.column_mapping.mode.value == "explicit"
    assert len(result.column_mapping.entries) == 4


def test_same_six_column_record_preserves_profile_policy_difference(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "six.csv",
        SIX_CANONICAL,
        (("PXDTEST", "Experiment_A", "", "", "100", "12345.0"),),
    )
    strict = validate_input(path, load_default_profile())
    reduced = validate_input(path, _reduced_profile())
    assert strict.summary.total_findings == 2
    assert {
        finding.location.field_name
        for finding in strict.findings
        if finding.location is not None
    } == {"experimental_condition", "sample_preparation_batch"}
    assert reduced.summary.total_findings == 0


def test_profile_0_3_0_still_detects_missing_required_column(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "missing_study.csv",
        ("sample_id", "quantified_protein_group_count", "protein_group_intensity_sum"),
        (("Experiment_A", "100", "12345.0"),),
    )
    result = validate_input(path, _reduced_profile())
    findings = [f for f in result.findings if f.code == "SCHEMA_MISSING_REQUIRED_COLUMN"]
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.field_name == "study_id"


def test_profile_0_3_0_still_detects_blank_required_metric(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "blank_metric.csv",
        FOUR_CANONICAL,
        (("PXDTEST", "Experiment_A", "", "12345.0"),),
    )
    result = validate_input(path, _reduced_profile())
    findings = [f for f in result.findings if f.code == "MISSINGNESS_REQUIRED_VALUE"]
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.field_name == "quantified_protein_group_count"


def test_profile_0_3_0_preserves_identifier_validation(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "identifiers.csv",
        FOUR_CANONICAL,
        (
            ("PXDTEST", "Experiment_A", "100", "1000.0"),
            ("PXDTEST", "Experiment_A", "101", "1100.0"),
            ("PXDTEST", "", "102", "1200.0"),
        ),
    )
    result = validate_input(path, _reduced_profile())
    codes = [finding.code for finding in result.findings]
    assert codes.count("IDENTIFIER_DUPLICATE_SAMPLE_ID") == 2
    assert codes.count("IDENTIFIER_MISSING_SAMPLE_ID") == 1


def test_cli_selects_profile_and_reports_candidate_identity(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "four.csv",
        FOUR_CANONICAL,
        (("PXDTEST", "Experiment_A", "100", "12345.0"),),
    )
    report = tmp_path / "report.md"
    code = cli_module.main([
        str(path), "--profile-version", "0.3.0", "--output", str(report),
    ])
    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert "- Application version: `0.5.1`" in text
    assert "- Profile version: `0.3.0`" in text
    assert "- Total findings: `0`" in text
    assert "Version 0.3.0 checks CSV structure" not in text


def test_cli_rejects_unknown_profile_version_without_report(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "four.csv",
        FOUR_CANONICAL,
        (("PXDTEST", "Experiment_A", "100", "12345.0"),),
    )
    report = tmp_path / "report.md"
    code = cli_module.main([
        str(path), "--profile-version", "999.0.0", "--output", str(report),
    ])
    assert code == 4
    assert not report.exists()


def test_cli_help_describes_general_processed_sample_input() -> None:
    help_text = cli_module._parser().format_help()
    assert "processed-sample proteomics CSV" in help_text
    assert "synthetic proteomics" not in help_text
    assert "--profile-version VERSION" in help_text
