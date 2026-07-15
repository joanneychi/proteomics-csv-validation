"""Tests for command parsing, exit codes, and stream separation."""

from __future__ import annotations

from pathlib import Path

import pytest

from proteomics_csv_validation import __version__
from proteomics_csv_validation import cli as cli_module
from proteomics_csv_validation.errors import (
    InputAccessError,
    OutputWriteError,
    ProfileDefinitionError,
)
from proteomics_csv_validation.models import (
    ValidationResult,
    ValidationStatus,
)
from proteomics_csv_validation.pipeline import (
    validate_input,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


def test_version_surface_uses_installed_distribution_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command exposes one authoritative package version."""

    with pytest.raises(
        SystemExit
    ) as captured:
        cli_module.main(
            [
                "--version",
            ]
        )

    assert captured.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_findings_return_zero_and_preserve_code_order(
    seeded_input_path: Path,
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Completed technical findings do not masquerade as process failure."""

    result = validate_input(
        seeded_input_path,
        default_profile,
    )

    output = tmp_path / "seeded.md"

    def fake_validate_and_write(
        input_path: Path,
        output_path: Path,
        *,
        overwrite: bool,
    ) -> ValidationResult:
        assert input_path == seeded_input_path
        assert output_path == output
        assert overwrite is False
        return result

    monkeypatch.setattr(
        cli_module,
        "validate_and_write",
        fake_validate_and_write,
    )

    exit_code = cli_module.main(
        [
            str(
                seeded_input_path
            ),
            "--output",
            str(
                output
            ),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""

    positions = tuple(
        captured.out.index(
            code
        )
        for code in (
            "SCHEMA_MISSING_REQUIRED_COLUMN",
            "IDENTIFIER_DUPLICATE_SAMPLE_ID",
            "IDENTIFIER_MISSING_SAMPLE_ID",
        )
    )

    assert positions == tuple(
        sorted(
            positions
        )
    )


def test_stopped_result_returns_three_on_stdout(
    baseline_input_path: Path,
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reportable stopped evidence uses stdout and exit status three."""

    completed = validate_input(
        baseline_input_path,
        default_profile,
    )

    stopped = ValidationResult(
        application_version=completed.application_version,
        descriptor_schema_version=completed.descriptor_schema_version,
        profile_id=completed.profile_id,
        profile_version=completed.profile_version,
        input_name="empty.csv",
        status=(
            ValidationStatus
            .STOPPED_AFTER_INGESTION_FINDING
        ),
        rows=0,
        configured_rules=completed.configured_rules,
        findings=completed.findings,
        summary=completed.summary,
    )

    monkeypatch.setattr(
        cli_module,
        "validate_and_write",
        lambda *args, **kwargs: stopped,
    )

    code = cli_module.main(
        [
            str(
                baseline_input_path
            ),
            "--output",
            str(
                tmp_path / "report.md"
            ),
        ]
    )

    captured = capsys.readouterr()

    assert code == 3
    assert captured.err == ""
    assert (
        "stopped_after_ingestion_finding"
        in captured.out
    )


@pytest.mark.parametrize(
    (
        "exception",
        "expected_code",
    ),
    (
        (
            InputAccessError(
                "input failure"
            ),
            3,
        ),
        (
            ProfileDefinitionError(
                "profile failure"
            ),
            4,
        ),
        (
            OutputWriteError(
                "output failure"
            ),
            5,
        ),
    ),
)
def test_expected_operational_failures_use_stderr(
    baseline_input_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception: Exception,
    expected_code: int,
) -> None:
    """Expected failures produce no traceback and no stdout summary."""

    def fail(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise exception

    monkeypatch.setattr(
        cli_module,
        "validate_and_write",
        fail,
    )

    code = cli_module.main(
        [
            str(
                baseline_input_path
            ),
            "--output",
            str(
                tmp_path / "report.md"
            ),
        ]
    )

    captured = capsys.readouterr()

    assert code == expected_code
    assert captured.out == ""
    assert captured.err != ""
    assert "Traceback" not in captured.err
