"""Tests for validation orchestration, path safety, and report publication."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Final

import pytest

from proteomics_csv_validation import (
    __version__,
)
from proteomics_csv_validation import (
    pipeline as pipeline_module,
)
from proteomics_csv_validation.errors import (
    InputAccessError,
    OutputWriteError,
    ProfileDefinitionError,
)
from proteomics_csv_validation.models import (
    FindingCategory,
    Scope,
    Severity,
    ValidationResult,
    ValidationStatus,
)
from proteomics_csv_validation.pipeline import (
    validate_and_write,
    validate_input,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


_FIXED_TIME: Final = datetime(
    2026,
    7,
    14,
    23,
    45,
    6,
    tzinfo=timezone.utc,
)

_EXPECTED_COMPLETED_RULES: Final = (
    (
        "ingestion.input_limits",
        "1.0.0",
    ),
    (
        "ingestion.csv_parse",
        "1.0.0",
    ),
    (
        "schema.required_column",
        "1.0.0",
    ),
    (
        "identifier.sample_id_required",
        "1.0.0",
    ),
    (
        "identifier.sample_id_unique",
        "1.0.0",
    ),
    (
        "missingness.required_value",
        "1.0.0",
    ),
)

_EXPECTED_INGESTION_RULES: Final = (
    (
        "ingestion.input_limits",
        "1.0.0",
    ),
    (
        "ingestion.csv_parse",
        "1.0.0",
    ),
)


def _configured_rule_pairs(
    result: ValidationResult,
) -> tuple[tuple[str, str], ...]:
    """Return configured rule identities in result order."""

    return tuple(
        (
            rule.rule_id,
            rule.rule_version,
        )
        for rule in result.configured_rules
    )


def _code_counts(
    result: ValidationResult,
) -> tuple[tuple[str, int], ...]:
    """Return present finding-code counts in canonical order."""

    return tuple(
        (
            item.code,
            item.count,
        )
        for item in result.summary.code_counts
    )


def _category_counts(
    result: ValidationResult,
) -> tuple[tuple[str, int], ...]:
    """Return every category count in canonical order."""

    return tuple(
        (
            item.category.value,
            item.count,
        )
        for item in result.summary.category_counts
    )


def _severity_counts(
    result: ValidationResult,
) -> tuple[tuple[str, int], ...]:
    """Return every severity count in canonical order."""

    return tuple(
        (
            item.severity.value,
            item.count,
        )
        for item in result.summary.severity_counts
    )


def _scope_counts(
    result: ValidationResult,
) -> tuple[tuple[str, int], ...]:
    """Return every scope count in canonical order."""

    return tuple(
        (
            item.scope.value,
            item.count,
        )
        for item in result.summary.scope_counts
    )


def _write_valid_input(
    tmp_path: Path,
    *,
    name: str = "valid.csv",
) -> Path:
    """Write one compact valid input for path and orchestration tests."""

    path = (
        tmp_path
        / name
    )

    path.write_text(
        (
            "study_id,sample_id,"
            "experimental_condition,"
            "sample_preparation_batch,"
            "quantified_protein_group_count,"
            "protein_group_intensity_sum\n"
            "STUDY_SYNTH_001,S001,"
            "control,PREP01,5120,"
            "128450000.25\n"
        ),
        encoding="utf-8",
        newline="",
    )

    return path


def _patch_fixed_clock(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str] | None = None,
) -> list[datetime]:
    """Patch the pipeline clock and record each call."""

    calls: list[datetime] = []

    def fixed_utc_now() -> datetime:
        if events is not None:
            events.append(
                "clock"
            )

        calls.append(
            _FIXED_TIME
        )

        return _FIXED_TIME

    assert hasattr(
        pipeline_module,
        "_utc_now",
    ), (
        "pipeline.py must expose the locked "
        "_utc_now orchestration seam."
    )

    monkeypatch.setattr(
        pipeline_module,
        "_utc_now",
        fixed_utc_now,
    )

    return calls


def test_validate_input_requires_path_object(
    default_profile: ProfileDefinition,
) -> None:
    """Validation accepts pathlib input paths rather than path strings."""

    with pytest.raises(
        TypeError
    ):
        validate_input(
            "input.csv",
            default_profile,
        )


def test_validate_input_requires_profile_definition(
    baseline_input_path: Path,
) -> None:
    """Validation requires one resolved immutable profile."""

    with pytest.raises(
        TypeError
    ):
        validate_input(
            baseline_input_path,
            object(),
        )


def test_baseline_validation_is_completed_without_findings(
    baseline_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """The reviewed baseline input completes with zero defects."""

    before = (
        baseline_input_path
        .read_bytes()
    )

    result = validate_input(
        baseline_input_path,
        default_profile,
    )

    after = (
        baseline_input_path
        .read_bytes()
    )

    assert result.status is (
        ValidationStatus.COMPLETED
    )

    assert result.input_name == (
        "baseline_valid.csv"
    )

    assert result.input_name == (
        baseline_input_path.name
    )

    assert result.application_version == (
        __version__
    )

    assert (
        result.descriptor_schema_version
        == "1.0.0"
    )

    assert (
        result.profile_id
        == "proteomics_processed_sample_summary"
    )

    assert (
        result.profile_version
        == "0.2.0"
    )

    assert result.rows == 8

    assert (
        result.findings
        == ()
    )

    assert (
        result.summary.total_findings
        == 0
    )

    assert (
        _configured_rule_pairs(
            result
        )
        == _EXPECTED_COMPLETED_RULES
    )

    assert _category_counts(
        result
    ) == (
        (
            "ingestion",
            0,
        ),
        (
            "schema",
            0,
        ),
        (
            "identifier",
            0,
        ),
        (
            "missingness",
            0,
        ),
    )

    assert _severity_counts(
        result
    ) == (
        (
            "error",
            0,
        ),
        (
            "warning",
            0,
        ),
        (
            "information",
            0,
        ),
    )

    assert _scope_counts(
        result
    ) == (
        (
            "file",
            0,
        ),
        (
            "row",
            0,
        ),
    )

    assert _code_counts(
        result
    ) == ()

    assert after == before


def test_seeded_validation_produces_exact_four_findings(
    seeded_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """The reviewed seeded input produces the locked evidence sequence."""

    before = (
        seeded_input_path
        .read_bytes()
    )

    result = validate_input(
        seeded_input_path,
        default_profile,
    )

    after = (
        seeded_input_path
        .read_bytes()
    )

    assert result.status is (
        ValidationStatus.COMPLETED
    )

    assert result.input_name == (
        "seeded_errors.csv"
    )

    assert result.rows == 8

    assert (
        result.summary.total_findings
        == 4
    )

    assert (
        _configured_rule_pairs(
            result
        )
        == _EXPECTED_COMPLETED_RULES
    )

    assert tuple(
        finding.code
        for finding in result.findings
    ) == (
        "SCHEMA_MISSING_REQUIRED_COLUMN",
        "IDENTIFIER_DUPLICATE_SAMPLE_ID",
        "IDENTIFIER_DUPLICATE_SAMPLE_ID",
        "IDENTIFIER_MISSING_SAMPLE_ID",
    )

    assert tuple(
        finding.category
        for finding in result.findings
    ) == (
        FindingCategory.SCHEMA,
        FindingCategory.IDENTIFIER,
        FindingCategory.IDENTIFIER,
        FindingCategory.IDENTIFIER,
    )

    assert tuple(
        finding.scope
        for finding in result.findings
    ) == (
        Scope.FILE,
        Scope.ROW,
        Scope.ROW,
        Scope.ROW,
    )

    assert tuple(
        (
            finding.location.row_number
            if finding.location is not None
            else None
        )
        for finding in result.findings
    ) == (
        None,
        4,
        5,
        9,
    )

    assert tuple(
        (
            finding.location.field_name
            if finding.location is not None
            else None
        )
        for finding in result.findings
    ) == (
        "study_id",
        "sample_id",
        "sample_id",
        "sample_id",
    )

    assert tuple(
        finding.observed_value
        for finding in result.findings
    ) == (
        None,
        "S003",
        "S003",
        "",
    )

    assert tuple(
        finding.expected_value
        for finding in result.findings
    ) == (
        "study_id",
        "unique_within_input_file",
        "unique_within_input_file",
        "nonmissing",
    )

    assert (
        result.findings[0].entity
        is None
    )

    assert (
        result.findings[1].entity
        is not None
    )

    assert (
        result.findings[2].entity
        is not None
    )

    assert (
        result.findings[3].entity
        is None
    )

    assert _category_counts(
        result
    ) == (
        (
            "ingestion",
            0,
        ),
        (
            "schema",
            1,
        ),
        (
            "identifier",
            3,
        ),
        (
            "missingness",
            0,
        ),
    )

    assert _severity_counts(
        result
    ) == (
        (
            "error",
            4,
        ),
        (
            "warning",
            0,
        ),
        (
            "information",
            0,
        ),
    )

    assert _scope_counts(
        result
    ) == (
        (
            "file",
            1,
        ),
        (
            "row",
            3,
        ),
    )

    assert _code_counts(
        result
    ) == (
        (
            "SCHEMA_MISSING_REQUIRED_COLUMN",
            1,
        ),
        (
            "IDENTIFIER_DUPLICATE_SAMPLE_ID",
            2,
        ),
        (
            "IDENTIFIER_MISSING_SAMPLE_ID",
            1,
        ),
    )

    assert after == before


def test_accessible_fatal_input_returns_stopped_result(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """An accessible malformed file becomes reportable stopped evidence."""

    input_path = (
        tmp_path
        / "empty.csv"
    )

    input_path.write_bytes(
        b""
    )

    result = validate_input(
        input_path,
        default_profile,
    )

    assert result.status is (
        ValidationStatus
        .STOPPED_AFTER_INGESTION_FINDING
    )

    assert result.input_name == (
        "empty.csv"
    )

    assert result.rows == 0

    assert (
        result.summary.total_findings
        == 1
    )

    assert (
        _configured_rule_pairs(
            result
        )
        == _EXPECTED_INGESTION_RULES
    )

    assert tuple(
        finding.code
        for finding in result.findings
    ) == (
        "INGESTION_CSV_PARSE_ERROR",
    )

    finding = result.findings[0]

    assert (
        finding.category
        is FindingCategory.INGESTION
    )

    assert (
        finding.severity
        is Severity.ERROR
    )

    assert (
        finding.scope
        is Scope.FILE
    )

    assert _category_counts(
        result
    ) == (
        (
            "ingestion",
            1,
        ),
        (
            "schema",
            0,
        ),
        (
            "identifier",
            0,
        ),
        (
            "missingness",
            0,
        ),
    )

    assert _code_counts(
        result
    ) == (
        (
            "INGESTION_CSV_PARSE_ERROR",
            1,
        ),
    )


def test_missing_input_raises_access_error_without_result(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """An inaccessible path remains an operational failure."""

    input_path = (
        tmp_path
        / "missing.csv"
    )

    with pytest.raises(
        InputAccessError
    ):
        validate_input(
            input_path,
            default_profile,
        )


def test_validate_and_write_publishes_baseline_report(
    baseline_input_path: Path,
    tmp_path: Path,
) -> None:
    """The complete pipeline validates and writes one new report."""

    output_path = (
        tmp_path
        / "baseline_report.md"
    )

    before = (
        baseline_input_path
        .read_bytes()
    )

    result = validate_and_write(
        baseline_input_path,
        output_path,
        overwrite=False,
    )

    after = (
        baseline_input_path
        .read_bytes()
    )

    assert result.status is (
        ValidationStatus.COMPLETED
    )

    assert (
        result.summary.total_findings
        == 0
    )

    assert output_path.is_file()

    report_text = (
        output_path.read_text(
            encoding="utf-8"
        )
    )

    assert "baseline_valid.csv" in (
        report_text
    )

    assert "completed" in (
        report_text
    )

    assert "## data and scope boundary" in (
        report_text.lower()
    )

    assert (
        str(
            baseline_input_path
        )
        not in report_text
    )

    assert after == before


def test_validate_and_write_publishes_seeded_report(
    seeded_input_path: Path,
    tmp_path: Path,
) -> None:
    """Finding-bearing validation still publishes and returns normally."""

    output_path = (
        tmp_path
        / "seeded_report.md"
    )

    result = validate_and_write(
        seeded_input_path,
        output_path,
        overwrite=False,
    )

    assert result.status is (
        ValidationStatus.COMPLETED
    )

    assert (
        result.summary.total_findings
        == 4
    )

    assert output_path.is_file()

    report_text = (
        output_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        "SCHEMA_MISSING_REQUIRED_COLUMN"
        in report_text
    )

    assert (
        "IDENTIFIER_DUPLICATE_SAMPLE_ID"
        in report_text
    )

    assert (
        "IDENTIFIER_MISSING_SAMPLE_ID"
        in report_text
    )


def test_validate_and_write_publishes_stopped_report(
    tmp_path: Path,
) -> None:
    """Fatal accessible content still receives a technical review report."""

    input_path = (
        tmp_path
        / "malformed.csv"
    )

    output_path = (
        tmp_path
        / "malformed_report.md"
    )

    input_path.write_bytes(
        b""
    )

    result = validate_and_write(
        input_path,
        output_path,
        overwrite=False,
    )

    assert result.status is (
        ValidationStatus
        .STOPPED_AFTER_INGESTION_FINDING
    )

    assert result.rows == 0

    assert (
        _configured_rule_pairs(
            result
        )
        == _EXPECTED_INGESTION_RULES
    )

    assert output_path.is_file()

    report_text = (
        output_path.read_text(
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


def test_inaccessible_input_does_not_create_report(
    tmp_path: Path,
) -> None:
    """An operational input failure stops before report publication."""

    input_path = (
        tmp_path
        / "missing.csv"
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    with pytest.raises(
        InputAccessError
    ):
        validate_and_write(
            input_path,
            output_path,
            overwrite=False,
        )

    assert not output_path.exists()


def test_pipeline_calls_clock_profile_validation_renderer_and_writer_once(
    baseline_input_path: Path,
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publication pipeline coordinates its stages in locked order."""

    output_path = (
        tmp_path
        / "coordinated_report.md"
    )

    real_result = validate_input(
        baseline_input_path,
        default_profile,
    )

    events: list[str] = []

    clock_calls = _patch_fixed_clock(
        monkeypatch,
        events,
    )

    profile_calls: list[
        ProfileDefinition
    ] = []

    validation_calls: list[
        tuple[
            Path,
            ProfileDefinition,
        ]
    ] = []

    render_calls: list[
        tuple[
            ValidationResult,
            datetime,
        ]
    ] = []

    write_calls: list[
        tuple[
            Path,
            str,
            bool,
        ]
    ] = []

    def fake_load_default_profile() -> ProfileDefinition:
        events.append(
            "profile"
        )

        profile_calls.append(
            default_profile
        )

        return default_profile

    def fake_validate_input(
        input_path: Path,
        profile: ProfileDefinition,
    ) -> ValidationResult:
        events.append(
            "validate"
        )

        validation_calls.append(
            (
                input_path,
                profile,
            )
        )

        return real_result

    def fake_render(
        result: ValidationResult,
        *,
        generated_at: datetime,
    ) -> str:
        events.append(
            "render"
        )

        render_calls.append(
            (
                result,
                generated_at,
            )
        )

        return "rendered report\n"

    def fake_write(
        path: Path,
        report_text: str,
        *,
        overwrite: bool,
    ) -> None:
        events.append(
            "write"
        )

        write_calls.append(
            (
                path,
                report_text,
                overwrite,
            )
        )

    monkeypatch.setattr(
        pipeline_module,
        "load_default_profile",
        fake_load_default_profile,
    )

    monkeypatch.setattr(
        pipeline_module,
        "validate_input",
        fake_validate_input,
    )

    monkeypatch.setattr(
        pipeline_module,
        "render_markdown_report",
        fake_render,
    )

    monkeypatch.setattr(
        pipeline_module,
        "write_markdown_report",
        fake_write,
    )

    returned = validate_and_write(
        baseline_input_path,
        output_path,
        overwrite=True,
    )

    assert returned is real_result

    assert events == [
        "clock",
        "profile",
        "validate",
        "render",
        "write",
    ]

    assert clock_calls == [
        _FIXED_TIME,
    ]

    assert profile_calls == [
        default_profile,
    ]

    assert validation_calls == [
        (
            baseline_input_path,
            default_profile,
        ),
    ]

    assert render_calls == [
        (
            real_result,
            _FIXED_TIME,
        ),
    ]

    assert write_calls == [
        (
            output_path,
            "rendered report\n",
            True,
        ),
    ]


def test_clock_is_captured_before_collision_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run time is captured before input-output collision evaluation."""

    input_path = _write_valid_input(
        tmp_path
    )

    events: list[str] = []

    clock_calls = _patch_fixed_clock(
        monkeypatch,
        events,
    )

    def forbidden_profile_load() -> None:
        events.append(
            "profile"
        )

        raise AssertionError(
            "Profile loading must not occur "
            "after collision detection fails."
        )

    def forbidden_validation(
        *args: object,
        **kwargs: object,
    ) -> None:
        events.append(
            "validate"
        )

        raise AssertionError(
            "Validation must not occur after "
            "collision detection fails."
        )

    monkeypatch.setattr(
        pipeline_module,
        "load_default_profile",
        forbidden_profile_load,
    )

    monkeypatch.setattr(
        pipeline_module,
        "validate_input",
        forbidden_validation,
    )

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            input_path,
            overwrite=True,
        )

    assert events == [
        "clock",
    ]

    assert clock_calls == [
        _FIXED_TIME,
    ]


def test_identical_input_and_output_path_is_rejected(
    tmp_path: Path,
) -> None:
    """The source file can never be selected as its own report."""

    input_path = _write_valid_input(
        tmp_path
    )

    before = input_path.read_bytes()

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            input_path,
            overwrite=True,
        )

    assert input_path.read_bytes() == (
        before
    )


def test_relative_alias_of_input_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute input and relative output alias cannot bypass protection."""

    monkeypatch.chdir(tmp_path)

    input_path = (
        _write_valid_input(
            tmp_path
        ).resolve()
    )

    relative_alias = Path(
        os.path.relpath(
            input_path,
            start=Path.cwd(),
        )
    )

    assert relative_alias != input_path

    before = input_path.read_bytes()

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            relative_alias,
            overwrite=True,
        )

    assert input_path.read_bytes() == (
        before
    )


def test_parent_traversal_alias_of_input_is_rejected(
    tmp_path: Path,
) -> None:
    """A path containing parent traversal resolves to the protected input."""

    input_path = _write_valid_input(
        tmp_path
    )

    alias = (
        input_path.parent
        / "unused_directory"
        / ".."
        / input_path.name
    )

    assert alias != input_path

    before = input_path.read_bytes()

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            alias,
            overwrite=True,
        )

    assert input_path.read_bytes() == (
        before
    )


def test_symlink_alias_of_input_is_rejected_when_supported(
    tmp_path: Path,
) -> None:
    """A report path resolving through a symlink cannot overwrite input."""

    input_path = _write_valid_input(
        tmp_path
    )

    alias = (
        tmp_path
        / "input_alias.md"
    )

    try:
        alias.symlink_to(
            input_path
        )
    except (
        OSError,
        NotImplementedError,
    ) as exc:
        pytest.skip(
            "The active filesystem cannot "
            f"create a test symlink: {exc}"
        )

    before = input_path.read_bytes()

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            alias,
            overwrite=True,
        )

    assert input_path.read_bytes() == (
        before
    )

    assert alias.is_symlink()


def test_hard_link_alias_of_input_is_rejected_when_supported(
    tmp_path: Path,
) -> None:
    """Distinct names for the same inode cannot bypass source protection."""

    input_path = _write_valid_input(
        tmp_path
    )

    alias = (
        tmp_path
        / "input_hard_link.md"
    )

    try:
        os.link(
            input_path,
            alias,
        )
    except (
        OSError,
        NotImplementedError,
    ) as exc:
        pytest.skip(
            "The active filesystem cannot "
            f"create a test hard link: {exc}"
        )

    before = input_path.read_bytes()

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            alias,
            overwrite=True,
        )

    assert input_path.read_bytes() == (
        before
    )

    assert alias.read_bytes() == before


@pytest.mark.parametrize(
    "exception",
    (
        OSError(
            "simulated input resolution failure"
        ),
        RuntimeError(
            "simulated input resolution loop"
        ),
    ),
)
def test_input_resolution_failure_maps_to_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    """Input canonicalization failures remain input-access errors."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    original_resolve = (
        Path.resolve
    )

    def failing_resolve(
        self: Path,
        *args: object,
        **kwargs: object,
    ) -> Path:
        if self == input_path:
            raise exception

        return original_resolve(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "resolve",
        failing_resolve,
    )

    with pytest.raises(
        InputAccessError
    ):
        validate_and_write(
            input_path,
            output_path,
            overwrite=False,
        )

    assert not output_path.exists()


@pytest.mark.parametrize(
    "exception",
    (
        OSError(
            "simulated output resolution failure"
        ),
        RuntimeError(
            "simulated output resolution loop"
        ),
    ),
)
def test_output_resolution_failure_maps_to_output_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    """Output canonicalization failures remain publication errors."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    original_resolve = (
        Path.resolve
    )

    def failing_resolve(
        self: Path,
        *args: object,
        **kwargs: object,
    ) -> Path:
        if self == output_path:
            raise exception

        return original_resolve(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "resolve",
        failing_resolve,
    )

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            output_path,
            overwrite=False,
        )

    assert not output_path.exists()


def test_samefile_failure_maps_to_output_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem identity-check failure does not permit publication."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "existing_report.md"
    )

    output_path.write_text(
        "existing report\n",
        encoding="utf-8",
        newline="",
    )

    original_path_samefile = (
        Path.samefile
    )

    def failing_path_samefile(
        self: Path,
        other_path: object,
    ) -> bool:
        if (
            self == input_path
            and Path(
                other_path
            ) == output_path
        ):
            raise OSError(
                "simulated samefile failure"
            )

        return original_path_samefile(
            self,
            other_path,
        )

    monkeypatch.setattr(
        Path,
        "samefile",
        failing_path_samefile,
    )

    if hasattr(
        pipeline_module,
        "os",
    ):
        original_os_samefile = (
            pipeline_module
            .os
            .path
            .samefile
        )

        def failing_os_samefile(
            first_path: object,
            second_path: object,
        ) -> bool:
            first = Path(
                first_path
            )

            second = Path(
                second_path
            )

            if (
                first == input_path
                and second == output_path
            ):
                raise OSError(
                    "simulated samefile failure"
                )

            return original_os_samefile(
                first_path,
                second_path,
            )

        monkeypatch.setattr(
            pipeline_module.os.path,
            "samefile",
            failing_os_samefile,
        )

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            output_path,
            overwrite=True,
        )

    assert output_path.read_text(
        encoding="utf-8"
    ) == "existing report\n"


def test_existing_distinct_output_is_refused_without_overwrite(
    tmp_path: Path,
) -> None:
    """A distinct reviewed report remains unchanged by default."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "report.md"
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
        input_path.read_bytes()
    )

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            input_path,
            output_path,
            overwrite=False,
        )

    assert output_path.read_text(
        encoding="utf-8"
    ) == original_report

    assert input_path.read_bytes() == (
        source_before
    )


def test_existing_distinct_output_is_replaced_with_overwrite(
    tmp_path: Path,
) -> None:
    """Explicit overwrite replaces a distinct report, never the source."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    output_path.write_text(
        "old report\n",
        encoding="utf-8",
        newline="",
    )

    source_before = (
        input_path.read_bytes()
    )

    result = validate_and_write(
        input_path,
        output_path,
        overwrite=True,
    )

    assert result.status is (
        ValidationStatus.COMPLETED
    )

    assert (
        output_path.read_text(
            encoding="utf-8"
        )
        != "old report\n"
    )

    assert input_path.read_bytes() == (
        source_before
    )


def test_profile_failure_stops_before_validation_and_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid built-in profile cannot produce a report."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    events: list[str] = []

    _patch_fixed_clock(
        monkeypatch,
        events,
    )

    def failing_profile_load() -> None:
        events.append(
            "profile"
        )

        raise ProfileDefinitionError(
            "simulated profile failure"
        )

    def forbidden_validation(
        *args: object,
        **kwargs: object,
    ) -> None:
        events.append(
            "validate"
        )

        raise AssertionError(
            "Validation must not run after "
            "profile loading fails."
        )

    def forbidden_render(
        *args: object,
        **kwargs: object,
    ) -> None:
        events.append(
            "render"
        )

        raise AssertionError(
            "Rendering must not run after "
            "profile loading fails."
        )

    def forbidden_write(
        *args: object,
        **kwargs: object,
    ) -> None:
        events.append(
            "write"
        )

        raise AssertionError(
            "Writing must not run after "
            "profile loading fails."
        )

    monkeypatch.setattr(
        pipeline_module,
        "load_default_profile",
        failing_profile_load,
    )

    monkeypatch.setattr(
        pipeline_module,
        "validate_input",
        forbidden_validation,
    )

    monkeypatch.setattr(
        pipeline_module,
        "render_markdown_report",
        forbidden_render,
    )

    monkeypatch.setattr(
        pipeline_module,
        "write_markdown_report",
        forbidden_write,
    )

    with pytest.raises(
        ProfileDefinitionError
    ):
        validate_and_write(
            input_path,
            output_path,
            overwrite=False,
        )

    assert events == [
        "clock",
        "profile",
    ]

    assert not output_path.exists()


def test_output_failure_is_propagated_after_rendering(
    baseline_input_path: Path,
    tmp_path: Path,
    default_profile: ProfileDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A publication failure does not masquerade as successful completion."""

    output_path = (
        tmp_path
        / "report.md"
    )

    real_result = validate_input(
        baseline_input_path,
        default_profile,
    )

    events: list[str] = []

    _patch_fixed_clock(
        monkeypatch,
        events,
    )

    def fake_load_default_profile() -> ProfileDefinition:
        events.append(
            "profile"
        )

        return default_profile

    def fake_validate_input(
        input_path: Path,
        profile: ProfileDefinition,
    ) -> ValidationResult:
        events.append(
            "validate"
        )

        assert input_path == (
            baseline_input_path
        )

        assert profile is (
            default_profile
        )

        return real_result

    def fake_render(
        result: ValidationResult,
        *,
        generated_at: datetime,
    ) -> str:
        events.append(
            "render"
        )

        assert result is real_result
        assert generated_at == _FIXED_TIME

        return "rendered report\n"

    def failing_write(
        path: Path,
        report_text: str,
        *,
        overwrite: bool,
    ) -> None:
        events.append(
            "write"
        )

        assert path == output_path
        assert report_text == (
            "rendered report\n"
        )

        assert overwrite is False

        raise OutputWriteError(
            "simulated output failure"
        )

    monkeypatch.setattr(
        pipeline_module,
        "load_default_profile",
        fake_load_default_profile,
    )

    monkeypatch.setattr(
        pipeline_module,
        "validate_input",
        fake_validate_input,
    )

    monkeypatch.setattr(
        pipeline_module,
        "render_markdown_report",
        fake_render,
    )

    monkeypatch.setattr(
        pipeline_module,
        "write_markdown_report",
        failing_write,
    )

    with pytest.raises(
        OutputWriteError
    ):
        validate_and_write(
            baseline_input_path,
            output_path,
            overwrite=False,
        )

    assert events == [
        "clock",
        "profile",
        "validate",
        "render",
        "write",
    ]

    assert not output_path.exists()


def test_pipeline_does_not_modify_source_during_overwrite_run(
    tmp_path: Path,
) -> None:
    """Output replacement remains isolated from exact input bytes."""

    input_path = _write_valid_input(
        tmp_path
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    output_path.write_text(
        "old report\n",
        encoding="utf-8",
        newline="",
    )

    source_before = (
        input_path.read_bytes()
    )

    validate_and_write(
        input_path,
        output_path,
        overwrite=True,
    )

    source_after = (
        input_path.read_bytes()
    )

    assert source_after == source_before


def test_repeated_validation_is_deterministic_before_rendering(
    seeded_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Validation evidence remains independent of publication time."""

    first = validate_input(
        seeded_input_path,
        default_profile,
    )

    second = validate_input(
        seeded_input_path,
        default_profile,
    )

    assert first == second

    assert first.findings == (
        second.findings
    )

    assert first.summary == (
        second.summary
    )

    assert first.configured_rules == (
        second.configured_rules
    )


def test_result_contains_filename_not_absolute_source_path(
    baseline_input_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Validation evidence avoids disclosing local directory structure."""

    result = validate_input(
        baseline_input_path,
        default_profile,
    )

    assert result.input_name == (
        baseline_input_path.name
    )

    assert result.input_name != (
        str(
            baseline_input_path
        )
    )

    assert (
        str(
            baseline_input_path.parent
        )
        not in result.input_name
    )


def test_auto_mapping_completes_validation_without_modifying_source(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Automatic lexical mapping precedes unchanged validator logic."""

    input_path = (
        tmp_path
        / "auto.csv"
    )

    input_path.write_text(
        (
            "Study ID,Sample Identifier,"
            "Experimental Condition,"
            "Sample Preparation Batch,"
            "Quantified Protein Group Count,"
            "Protein Group Intensity Sum\n"
            "STUDY001,S001,control,PREP01,1452,125000000.0\n"
        ),
        encoding="utf-8",
        newline="",
    )

    before = input_path.read_bytes()

    result = validate_input(
        input_path,
        default_profile,
        auto_map=True,
    )

    assert result.status is ValidationStatus.COMPLETED
    assert result.summary.total_findings == 0
    assert result.column_mapping.mode.value == "automatic"
    assert result.column_mapping.resolution_completed is True
    assert len(result.column_mapping.entries) == 6
    assert input_path.read_bytes() == before


def test_explicit_mapping_publishes_mapping_provenance_without_local_path(
    tmp_path: Path,
) -> None:
    """Explicit mappings appear by header identity while local paths stay private."""

    input_path = (
        tmp_path
        / "explicit.csv"
    )

    input_path.write_text(
        (
            "Study,Sample Name,Condition,Prep Batch,"
            "Protein Count,Total Intensity\n"
            "STUDY001,S001,control,PREP01,1452,125000000.0\n"
        ),
        encoding="utf-8",
        newline="",
    )

    mapping_path = (
        tmp_path
        / "mapping.json"
    )

    mapping_path.write_text(
        (
            "{\n"
            '  "mapping_specification_version": "1.0.0",\n'
            '  "columns": {\n'
            '    "study_id": "Study",\n'
            '    "sample_id": "Sample Name",\n'
            '    "experimental_condition": "Condition",\n'
            '    "sample_preparation_batch": "Prep Batch",\n'
            '    "quantified_protein_group_count": "Protein Count",\n'
            '    "protein_group_intensity_sum": "Total Intensity"\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    output_path = (
        tmp_path
        / "report.md"
    )

    input_before = input_path.read_bytes()
    mapping_before = mapping_path.read_bytes()

    result = validate_and_write(
        input_path,
        output_path,
        column_map=mapping_path,
    )

    assert result.status is ValidationStatus.COMPLETED
    assert result.summary.total_findings == 0
    assert result.column_mapping.mode.value == "explicit"
    assert len(result.column_mapping.entries) == 6

    report = output_path.read_text(
        encoding="utf-8"
    )

    assert "## Column mapping" in report
    assert "`Sample Name` -> `sample_id`" in report
    assert str(mapping_path) not in report
    assert str(tmp_path) not in report

    assert input_path.read_bytes() == input_before
    assert mapping_path.read_bytes() == mapping_before


def test_mapping_file_cannot_be_selected_as_report_target(
    tmp_path: Path,
) -> None:
    """Report publication cannot replace an explicit mapping file."""

    input_path = _write_valid_input(
        tmp_path
    )

    mapping_path = (
        tmp_path
        / "mapping.json"
    )

    original = (
        '{"mapping_specification_version":"1.0.0",'
        '"columns":{"study_id":"Study"}}\n'
    )

    mapping_path.write_text(
        original,
        encoding="utf-8",
    )

    with pytest.raises(
        OutputWriteError,
        match="column-mapping file",
    ):
        validate_and_write(
            input_path,
            mapping_path,
            overwrite=True,
            column_map=mapping_path,
        )

    assert mapping_path.read_text(
        encoding="utf-8"
    ) == original


def test_stopped_ingestion_records_mapping_stage_as_not_reached(
    tmp_path: Path,
    default_profile: ProfileDefinition,
) -> None:
    """Fatal ingestion stops before requested automatic mapping is resolved."""

    input_path = (
        tmp_path
        / "empty.csv"
    )

    input_path.write_bytes(
        b""
    )

    result = validate_input(
        input_path,
        default_profile,
        auto_map=True,
    )

    assert result.status is (
        ValidationStatus
        .STOPPED_AFTER_INGESTION_FINDING
    )

    assert result.column_mapping.mode.value == "automatic"
    assert result.column_mapping.resolution_completed is False
    assert result.column_mapping.entries == ()
