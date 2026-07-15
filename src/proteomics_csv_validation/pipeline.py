"""Validation orchestration, path safety, and report publication."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from proteomics_csv_validation import (
    __version__,
)
from proteomics_csv_validation.aggregate import (
    build_validation_result,
)
from proteomics_csv_validation.errors import (
    InputAccessError,
    OutputWriteError,
)
from proteomics_csv_validation.ingest import (
    INGESTION_RULES,
    ingest_csv,
)
from proteomics_csv_validation.models import (
    IngestionFailure,
    ParsedTable,
    ValidationResult,
    ValidationStatus,
)
from proteomics_csv_validation.profiles.loader import (
    load_default_profile,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)
from proteomics_csv_validation.report import (
    render_markdown_report,
    write_markdown_report,
)
from proteomics_csv_validation.validators.identifier import (
    IDENTIFIER_RULES,
    validate_identifiers,
)
from proteomics_csv_validation.validators.schema import (
    SCHEMA_RULES,
    validate_schema,
)


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(
        timezone.utc
    )


def _ensure_distinct_input_and_output(
    input_path: Path,
    output_path: Path,
) -> None:
    """Reject lexical and filesystem aliases of the protected input."""

    if not isinstance(
        input_path,
        Path,
    ):
        raise TypeError(
            "input_path must be a pathlib.Path."
        )

    if not isinstance(
        output_path,
        Path,
    ):
        raise TypeError(
            "output_path must be a pathlib.Path."
        )

    try:
        resolved_input = input_path.resolve(
            strict=False
        )
    except (
        OSError,
        RuntimeError,
    ) as exc:
        raise InputAccessError(
            "The input path could not be resolved safely."
        ) from exc

    try:
        resolved_output = output_path.resolve(
            strict=False
        )
    except (
        OSError,
        RuntimeError,
    ) as exc:
        raise OutputWriteError(
            "The output path could not be resolved safely."
        ) from exc

    if resolved_input == resolved_output:
        raise OutputWriteError(
            "The report target cannot replace the input file."
        )

    if (
        input_path.exists()
        and output_path.exists()
    ):
        try:
            same_file = input_path.samefile(
                output_path
            )
        except (
            OSError,
            RuntimeError,
        ) as exc:
            raise OutputWriteError(
                "Filesystem identity could not be "
                "verified for the selected output."
            ) from exc

        if same_file:
            raise OutputWriteError(
                "The report target cannot reference "
                "the same file as the input."
            )


def validate_input(
    input_path: Path,
    profile: ProfileDefinition,
) -> ValidationResult:
    """Validate one accessible input using one resolved profile."""

    if not isinstance(
        input_path,
        Path,
    ):
        raise TypeError(
            "input_path must be a pathlib.Path."
        )

    if not isinstance(
        profile,
        ProfileDefinition,
    ):
        raise TypeError(
            "profile must be a ProfileDefinition."
        )

    ingested = ingest_csv(
        input_path,
        profile,
    )

    if isinstance(
        ingested,
        IngestionFailure,
    ):
        return build_validation_result(
            application_version=(
                __version__
            ),
            descriptor_schema_version=(
                profile
                .descriptor_schema_version
            ),
            profile_id=profile.profile_id,
            profile_version=(
                profile.profile_version
            ),
            input_name=(
                ingested.input_name
            ),
            status=(
                ValidationStatus
                .STOPPED_AFTER_INGESTION_FINDING
            ),
            rows=0,
            configured_rules=(
                INGESTION_RULES
            ),
            findings=(
                ingested.finding,
            ),
        )

    if not isinstance(
        ingested,
        ParsedTable,
    ):
        raise TypeError(
            "The ingestion layer returned an "
            "unsupported result type."
        )

    schema_findings = validate_schema(
        ingested,
        profile,
    )

    identifier_findings = (
        validate_identifiers(
            ingested,
            profile,
        )
    )

    configured_rules = (
        *INGESTION_RULES,
        *SCHEMA_RULES,
        *IDENTIFIER_RULES,
    )

    return build_validation_result(
        application_version=(
            __version__
        ),
        descriptor_schema_version=(
            profile
            .descriptor_schema_version
        ),
        profile_id=profile.profile_id,
        profile_version=(
            profile.profile_version
        ),
        input_name=ingested.input_name,
        status=ValidationStatus.COMPLETED,
        rows=len(
            ingested.records
        ),
        configured_rules=(
            configured_rules
        ),
        findings=(
            *schema_findings,
            *identifier_findings,
        ),
    )


def validate_and_write(
    input_path: Path,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> ValidationResult:
    """Validate one input and publish its Markdown technical report."""

    generated_at = _utc_now()

    _ensure_distinct_input_and_output(
        input_path,
        output_path,
    )

    profile = load_default_profile()

    result = validate_input(
        input_path,
        profile,
    )

    report_text = render_markdown_report(
        result,
        generated_at=generated_at,
    )

    write_markdown_report(
        output_path,
        report_text,
        overwrite=overwrite,
    )

    return result
