"""Tests for deterministic, private, and protected Markdown reporting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from proteomics_csv_validation.errors import (
    OutputWriteError,
)
from proteomics_csv_validation.pipeline import (
    validate_input,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)
from proteomics_csv_validation.report import (
    render_markdown_report,
    write_markdown_report,
)


_FIXED_TIME = datetime(
    2026,
    7,
    14,
    23,
    45,
    6,
    tzinfo=timezone.utc,
)


def test_baseline_report_has_one_timestamp_and_no_source_path(
    baseline_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Rendering uses filename-only identity and exactly one final newline."""

    result = validate_input(
        baseline_input_path,
        default_profile,
    )

    report = render_markdown_report(
        result,
        generated_at=_FIXED_TIME,
    )

    assert report.count(
        "2026-07-14T23:45:06Z"
    ) == 1

    assert "baseline_valid.csv" in report
    assert "Report format version: `1.1.0`" in report
    assert "## Column mapping" in report
    assert "Mapping mode: `strict`" in report
    assert "Resolved columns: `0`" in report

    assert (
        str(
            baseline_input_path
        )
        not in report
    )

    assert report.endswith("\n")
    assert not report.endswith("\n\n")

    assert (
        "No validation findings were detected "
        "under the configured rules."
        in report
    )

    assert (
        "required non-key values"
        in report
    )

    assert (
        "Reviewers decide dataset acceptance."
        in report
    )


def test_writer_refuses_existing_output_without_overwrite(
    tmp_path: Path,
) -> None:
    """Reviewed reports are protected by default."""

    output = tmp_path / "report.md"
    output.write_text(
        "reviewed\n",
        encoding="utf-8",
        newline="",
    )

    with pytest.raises(
        OutputWriteError
    ):
        write_markdown_report(
            output,
            "replacement\n",
            overwrite=False,
        )

    assert output.read_text(
        encoding="utf-8"
    ) == "reviewed\n"


def test_finding_section_displays_rule_identity(
    required_value_missing_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Report format 1.1.0 attaches rule identity to each finding."""

    result = validate_input(
        required_value_missing_input_path,
        default_profile,
    )

    report = render_markdown_report(
        result,
        generated_at=_FIXED_TIME,
    )

    assert (
        "- Rule: `missingness.required_value` "
        "version `1.0.0`"
        in report
    )
