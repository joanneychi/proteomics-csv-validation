"""End-to-end tests for installed command surfaces and published evidence."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
from typing import Final

import pytest

from proteomics_csv_validation import __version__
from proteomics_csv_validation.models import (
    EntityReference,
    Finding,
    FindingValue,
    ValidationResult,
)
from proteomics_csv_validation.pipeline import (
    validate_input,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


_CONSOLE_SCRIPT_NAME: Final = (
    "proteomics-csv-validate"
)

_PACKAGE_MODULE_NAME: Final = (
    "proteomics_csv_validation"
)

_PROCESS_TIMEOUT_SECONDS: Final = 30.0

_TIMESTAMP_PATTERN = re.compile(
    r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z\b"
)

CommandPrefix = tuple[
    str,
    ...,
]

JsonLike = (
    None
    | bool
    | int
    | float
    | str
    | list[
        "JsonLike"
    ]
    | dict[
        str,
        "JsonLike",
    ]
)


def _child_environment() -> dict[str, str]:
    """Return a UTF-8 child environment without source-path injection."""

    environment = dict(
        os.environ
    )

    environment.pop(
        "PYTHONPATH",
        None,
    )

    environment[
        "PYTHONUTF8"
    ] = "1"

    environment[
        "PYTHONIOENCODING"
    ] = "utf-8"

    return environment


def _run_process(
    command_prefix: CommandPrefix,
    arguments: tuple[
        str | Path,
        ...,
    ],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one installed command surface without invoking a shell."""

    command = [
        *command_prefix,
        *(
            str(
                argument
            )
            for argument in arguments
        ),
    ]

    return subprocess.run(
        command,
        cwd=cwd,
        env=_child_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        shell=False,
        timeout=(
            _PROCESS_TIMEOUT_SECONDS
        ),
    )


def _console_script_candidates() -> tuple[
    Path,
    ...,
]:
    """Return platform-appropriate wrapper candidates for this interpreter."""

    scripts_path = (
        sysconfig.get_path(
            "scripts"
        )
    )

    if scripts_path is None:
        raise AssertionError(
            "The active interpreter did not "
            "expose an installation scripts "
            "directory."
        )

    scripts_directory = Path(
        scripts_path
    )

    suffixes = (
        (
            ".exe",
            ".cmd",
            ".bat",
            "",
        )
        if os.name == "nt"
        else (
            "",
        )
    )

    return tuple(
        scripts_directory
        / (
            f"{_CONSOLE_SCRIPT_NAME}"
            f"{suffix}"
        )
        for suffix in suffixes
    )


@pytest.fixture(
    scope="module"
)
def module_command_prefix() -> CommandPrefix:
    """Return the installed package-module command prefix."""

    if not sys.executable:
        raise AssertionError(
            "The active Python executable "
            "could not be identified."
        )

    return (
        sys.executable,
        "-m",
        _PACKAGE_MODULE_NAME,
    )


@pytest.fixture(
    scope="module"
)
def console_script_path() -> Path:
    """Return the console wrapper installed for the active interpreter."""

    candidates = (
        _console_script_candidates()
    )

    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.is_file()
    )

    if not matches:
        pytest.fail(
            "The installed console-script "
            "wrapper was not found in the "
            "active interpreter's scripts "
            "directory. "
            f"Checked: {candidates!r}"
        )

    return matches[
        0
    ].resolve()


@pytest.fixture(
    scope="module"
)
def console_command_prefix(
    console_script_path: Path,
) -> CommandPrefix:
    """Return the installed console-script command prefix."""

    return (
        str(
            console_script_path
        ),
    )


def _finding_value_projection(
    value: FindingValue,
) -> JsonLike:
    """Convert one finding scalar into expected-fixture JSON form."""

    if isinstance(
        value,
        Decimal,
    ):
        return str(
            value
        )

    return value


def _entity_projection(
    entity: EntityReference | None,
) -> JsonLike:
    """Project one optional entity reference into JSON-compatible evidence."""

    if entity is None:
        return None

    return {
        "entity_type": (
            entity.entity_type
        ),
        "key_parts": [
            {
                "field_name": (
                    key_part.field_name
                ),
                "value": (
                    _finding_value_projection(
                        key_part.value
                    )
                ),
            }
            for key_part
            in entity.key_parts
        ],
    }


def _finding_projection(
    finding: Finding,
) -> dict[
    str,
    JsonLike,
]:
    """Project one finding while excluding nonfixture message prose."""

    location: JsonLike

    if finding.location is None:
        location = None
    else:
        location = {
            "row_number": (
                finding
                .location
                .row_number
            ),
            "field_name": (
                finding
                .location
                .field_name
            ),
        }

    return {
        "code": finding.code,
        "category": (
            finding.category.value
        ),
        "severity": (
            finding.severity.value
        ),
        "scope": (
            finding.scope.value
        ),
        "rule": {
            "rule_id": (
                finding.rule.rule_id
            ),
            "rule_version": (
                finding
                .rule
                .rule_version
            ),
        },
        "location": location,
        "entity": (
            _entity_projection(
                finding.entity
            )
        ),
        "observed_value": (
            _finding_value_projection(
                finding.observed_value
            )
        ),
        "expected_value": (
            _finding_value_projection(
                finding.expected_value
            )
        ),
    }


def _result_projection(
    result: ValidationResult,
) -> dict[
    str,
    JsonLike,
]:
    """Project deterministic validation evidence into fixture schema 1.0.0."""

    return {
        "fixture_schema_version": (
            "1.0.0"
        ),
        "input_name": (
            result.input_name
        ),
        "descriptor_schema_version": (
            result
            .descriptor_schema_version
        ),
        "profile_id": (
            result.profile_id
        ),
        "profile_version": (
            result.profile_version
        ),
        "status": (
            result.status.value
        ),
        "rows": result.rows,
        "configured_rules": [
            {
                "rule_id": (
                    rule.rule_id
                ),
                "rule_version": (
                    rule.rule_version
                ),
            }
            for rule
            in result.configured_rules
        ],
        "summary": {
            "total_findings": (
                result
                .summary
                .total_findings
            ),
            "category_counts": [
                {
                    "category": (
                        item
                        .category
                        .value
                    ),
                    "count": (
                        item.count
                    ),
                }
                for item
                in (
                    result
                    .summary
                    .category_counts
                )
            ],
            "code_counts": [
                {
                    "code": (
                        item.code
                    ),
                    "count": (
                        item.count
                    ),
                }
                for item
                in (
                    result
                    .summary
                    .code_counts
                )
            ],
            "severity_counts": [
                {
                    "severity": (
                        item
                        .severity
                        .value
                    ),
                    "count": (
                        item.count
                    ),
                }
                for item
                in (
                    result
                    .summary
                    .severity_counts
                )
            ],
            "scope_counts": [
                {
                    "scope": (
                        item
                        .scope
                        .value
                    ),
                    "count": (
                        item.count
                    ),
                }
                for item
                in (
                    result
                    .summary
                    .scope_counts
                )
            ],
        },
        "findings": [
            _finding_projection(
                finding
            )
            for finding
            in result.findings
        ],
    }


def _thaw_json_value(
    value: object,
) -> JsonLike:
    """Convert the frozen expected fixture into ordinary JSON containers."""

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(
                key
            ): (
                _thaw_json_value(
                    item
                )
            )
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        tuple,
    ):
        return [
            _thaw_json_value(
                item
            )
            for item in value
        ]

    if (
        value is None
        or isinstance(
            value,
            (
                bool,
                int,
                float,
                str,
            ),
        )
    ):
        return value

    raise TypeError(
        "The frozen expected fixture "
        "contained an unsupported value: "
        f"{type(value)!r}."
    )


def _assert_report_hides_paths(
    report_text: str,
    *paths: Path,
) -> None:
    """Require local absolute paths to be absent in raw and escaped form."""

    for path in paths:
        absolute_path = str(
            path.resolve()
        )

        escaped_path = (
            json.dumps(
                absolute_path,
                ensure_ascii=True,
            )[
                1:-1
            ]
        )

        assert (
            absolute_path
            not in report_text
        )

        assert (
            escaped_path
            not in report_text
        )


def _normalize_publication_time(
    report_text: str,
) -> str:
    """Replace the single UTC publication timestamp for report comparison."""

    timestamps = (
        _TIMESTAMP_PATTERN
        .findall(
            report_text
        )
    )

    assert len(
        timestamps
    ) == 1

    return (
        _TIMESTAMP_PATTERN
        .sub(
            "<GENERATED_AT>",
            report_text,
            count=1,
        )
    )


def _assert_success_process(
    completed: subprocess.CompletedProcess[
        str
    ],
) -> None:
    """Require a successful command with stdout-only summary output."""

    assert (
        completed.returncode
        == 0
    )

    assert (
        completed.stdout
        != ""
    )

    assert (
        completed.stderr
        == ""
    )

    assert (
        "Traceback"
        not in completed.stdout
    )


def test_installed_module_and_console_version_surfaces(
    tmp_path: Path,
    module_command_prefix: CommandPrefix,
    console_command_prefix: CommandPrefix,
) -> None:
    """Both installed launch surfaces expose the same distribution version."""

    module_result = (
        _run_process(
            module_command_prefix,
            (
                "--version",
            ),
            cwd=tmp_path,
        )
    )

    console_result = (
        _run_process(
            console_command_prefix,
            (
                "--version",
            ),
            cwd=tmp_path,
        )
    )

    for completed in (
        module_result,
        console_result,
    ):
        _assert_success_process(
            completed
        )

        assert (
            __version__
            in completed.stdout
        )

        assert (
            completed.stdout
            .endswith(
                "\n"
            )
        )

    assert (
        module_result.stdout
        == console_result.stdout
    )


def test_module_and_console_publish_equivalent_baseline_reports(
    baseline_input_path: Path,
    tmp_path: Path,
    module_command_prefix: CommandPrefix,
    console_command_prefix: CommandPrefix,
) -> None:
    """Both installed command surfaces publish equivalent baseline evidence."""

    module_output = (
        tmp_path
        / "baseline_module_report.md"
    )

    console_output = (
        tmp_path
        / "baseline_console_report.md"
    )

    source_before = (
        baseline_input_path
        .read_bytes()
    )

    module_result = (
        _run_process(
            module_command_prefix,
            (
                baseline_input_path,
                "--output",
                module_output,
            ),
            cwd=tmp_path,
        )
    )

    console_result = (
        _run_process(
            console_command_prefix,
            (
                baseline_input_path,
                "--output",
                console_output,
            ),
            cwd=tmp_path,
        )
    )

    for completed in (
        module_result,
        console_result,
    ):
        _assert_success_process(
            completed
        )

        assert (
            "completed"
            in completed.stdout
        )

        assert (
            "none"
            in completed
            .stdout
            .lower()
        )

    assert (
        baseline_input_path
        .read_bytes()
        == source_before
    )

    assert module_output.is_file()
    assert console_output.is_file()

    module_report = (
        module_output
        .read_text(
            encoding="utf-8"
        )
    )

    console_report = (
        console_output
        .read_text(
            encoding="utf-8"
        )
    )

    for (
        report_text,
        output_path,
    ) in (
        (
            module_report,
            module_output,
        ),
        (
            console_report,
            console_output,
        ),
    ):
        assert (
            "baseline_valid.csv"
            in report_text
        )

        assert (
            "completed"
            in report_text
        )

        assert (
            "synthetic"
            in report_text.lower()
        )

        assert (
            "\r"
            not in report_text
        )

        assert (
            report_text.endswith(
                "\n"
            )
        )

        assert not (
            report_text.endswith(
                "\n\n"
            )
        )

        _assert_report_hides_paths(
            report_text,
            baseline_input_path,
            output_path,
        )

    assert (
        _normalize_publication_time(
            module_report
        )
        ==
        _normalize_publication_time(
            console_report
        )
    )


def test_seeded_result_matches_expected_fixture_exactly(
    seeded_input_path: Path,
    default_profile: ProfileDefinition,
    loaded_seeded_expected: Mapping[
        str,
        object,
    ],
) -> None:
    """Deterministic seeded evidence exactly matches the reviewed oracle."""

    source_before = (
        seeded_input_path
        .read_bytes()
    )

    first = validate_input(
        seeded_input_path,
        default_profile,
    )

    second = validate_input(
        seeded_input_path,
        default_profile,
    )

    assert first == second

    assert (
        _result_projection(
            first
        )
        ==
        _thaw_json_value(
            loaded_seeded_expected
        )
    )

    assert (
        _result_projection(
            second
        )
        ==
        _result_projection(
            first
        )
    )

    assert (
        seeded_input_path
        .read_bytes()
        == source_before
    )


def test_seeded_console_process_publishes_expected_findings(
    seeded_input_path: Path,
    tmp_path: Path,
    console_command_prefix: CommandPrefix,
) -> None:
    """The installed console command publishes the canonical seeded report."""

    output_path = (
        tmp_path
        / "seeded_console_report.md"
    )

    source_before = (
        seeded_input_path
        .read_bytes()
    )

    completed = (
        _run_process(
            console_command_prefix,
            (
                seeded_input_path,
                "--output",
                output_path,
            ),
            cwd=tmp_path,
        )
    )

    _assert_success_process(
        completed
    )

    expected_codes = (
        "SCHEMA_MISSING_REQUIRED_COLUMN",
        "IDENTIFIER_DUPLICATE_SAMPLE_ID",
        "IDENTIFIER_MISSING_SAMPLE_ID",
    )

    stdout_positions = tuple(
        completed
        .stdout
        .index(
            code
        )
        for code
        in expected_codes
    )

    assert (
        stdout_positions
        == tuple(
            sorted(
                stdout_positions
            )
        )
    )

    assert output_path.is_file()

    report_text = (
        output_path
        .read_text(
            encoding="utf-8"
        )
    )

    report_positions = tuple(
        report_text.index(
            code
        )
        for code
        in expected_codes
    )

    assert (
        report_positions
        == tuple(
            sorted(
                report_positions
            )
        )
    )

    assert (
        report_text.count(
            "IDENTIFIER_DUPLICATE_SAMPLE_ID"
        )
        >= 2
    )

    assert "S003" in report_text
    assert "study_id" in report_text
    assert "sample_id" in report_text

    _assert_report_hides_paths(
        report_text,
        seeded_input_path,
        output_path,
    )

    assert (
        seeded_input_path
        .read_bytes()
        == source_before
    )


def test_stopped_ingestion_module_process_writes_report_and_returns_three(
    tmp_path: Path,
    module_command_prefix: CommandPrefix,
) -> None:
    """Fatal accessible content publishes a stopped report with exit code 3."""

    input_path = (
        tmp_path
        / "empty.csv"
    )

    output_path = (
        tmp_path
        / "empty_report.md"
    )

    input_path.write_bytes(
        b""
    )

    source_before = (
        input_path.read_bytes()
    )

    completed = (
        _run_process(
            module_command_prefix,
            (
                input_path,
                "--output",
                output_path,
            ),
            cwd=tmp_path,
        )
    )

    assert (
        completed.returncode
        == 3
    )

    assert (
        completed.stdout
        != ""
    )

    assert (
        completed.stderr
        == ""
    )

    assert (
        "stopped_after_ingestion_finding"
        in completed.stdout
    )

    assert (
        "INGESTION_CSV_PARSE_ERROR"
        in completed.stdout
    )

    assert output_path.is_file()

    report_text = (
        output_path
        .read_text(
            encoding="utf-8"
        )
    )

    assert (
        "stopped_after_ingestion_finding"
        in report_text
    )

    assert (
        "INGESTION_CSV_PARSE_ERROR"
        in report_text
    )

    _assert_report_hides_paths(
        report_text,
        input_path,
        output_path,
    )

    assert (
        input_path.read_bytes()
        == source_before
    )


def test_missing_input_console_process_returns_three_without_report(
    tmp_path: Path,
    console_command_prefix: CommandPrefix,
) -> None:
    """An inaccessible source returns exit code 3 without report publication."""

    input_path = (
        tmp_path
        / "missing.csv"
    )

    output_path = (
        tmp_path
        / "missing_report.md"
    )

    completed = (
        _run_process(
            console_command_prefix,
            (
                input_path,
                "--output",
                output_path,
            ),
            cwd=tmp_path,
        )
    )

    assert (
        completed.returncode
        == 3
    )

    assert (
        completed.stdout
        == ""
    )

    assert (
        completed.stderr
        != ""
    )

    assert (
        "Traceback"
        not in completed.stderr
    )

    assert not output_path.exists()


def test_existing_output_refusal_then_explicit_console_overwrite(
    baseline_input_path: Path,
    tmp_path: Path,
    module_command_prefix: CommandPrefix,
    console_command_prefix: CommandPrefix,
) -> None:
    """Default refusal preserves output, while explicit overwrite replaces it."""

    output_path = (
        tmp_path
        / "reviewed_report.md"
    )

    original_report = (
        "existing reviewed report\n"
    )

    output_path.write_text(
        original_report,
        encoding="utf-8",
        newline="",
    )

    source_before = (
        baseline_input_path
        .read_bytes()
    )

    refused = (
        _run_process(
            module_command_prefix,
            (
                baseline_input_path,
                "--output",
                output_path,
            ),
            cwd=tmp_path,
        )
    )

    assert (
        refused.returncode
        == 5
    )

    assert (
        refused.stdout
        == ""
    )

    assert (
        refused.stderr
        != ""
    )

    assert (
        "Traceback"
        not in refused.stderr
    )

    assert (
        output_path
        .read_text(
            encoding="utf-8"
        )
        == original_report
    )

    overwritten = (
        _run_process(
            console_command_prefix,
            (
                baseline_input_path,
                "--output",
                output_path,
                "--overwrite",
            ),
            cwd=tmp_path,
        )
    )

    _assert_success_process(
        overwritten
    )

    replacement = (
        output_path
        .read_text(
            encoding="utf-8"
        )
    )

    assert (
        replacement
        != original_report
    )

    assert (
        "baseline_valid.csv"
        in replacement
    )

    assert (
        "completed"
        in replacement
    )

    _assert_report_hides_paths(
        replacement,
        baseline_input_path,
        output_path,
    )

    assert (
        baseline_input_path
        .read_bytes()
        == source_before
    )


def test_console_wrapper_belongs_to_active_interpreter_scripts_directory(
    console_script_path: Path,
) -> None:
    """The invoked wrapper comes from the active interpreter environment."""

    scripts_path = (
        sysconfig.get_path(
            "scripts"
        )
    )

    assert scripts_path is not None

    assert (
        console_script_path.parent
        ==
        Path(
            scripts_path
        ).resolve()
    )

    assert console_script_path.is_file()
