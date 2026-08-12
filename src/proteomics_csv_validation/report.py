"""Deterministic Markdown rendering and protected report publication."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile

from proteomics_csv_validation.errors import (
    OutputWriteError,
)
from proteomics_csv_validation.models import (
    Finding,
    FindingValue,
    ValidationResult,
)


_REPORT_FORMAT_VERSION = "1.1.0"


def _code_span(
    text: str,
) -> str:
    longest_run = 0
    current_run = 0

    for character in text:
        if character == "`":
            current_run += 1
            longest_run = max(
                longest_run,
                current_run,
            )
        else:
            current_run = 0

    delimiter = "`" * (
        longest_run
        + 1
    )

    needs_padding = (
        text.startswith(
            "`"
        )
        or text.endswith(
            "`"
        )
    )

    padding = (
        " "
        if needs_padding
        else ""
    )

    return (
        f"{delimiter}"
        f"{padding}{text}{padding}"
        f"{delimiter}"
    )


def _literal_text(
    value: FindingValue,
) -> str:
    if isinstance(
        value,
        Decimal,
    ):
        raw = str(
            value
        )
    else:
        raw = json.dumps(
            value,
            ensure_ascii=True,
            separators=(
                ",",
                ":",
            ),
        )

    return _code_span(
        raw
    )


def _utc_text(
    generated_at: datetime,
) -> str:
    if generated_at.tzinfo is None:
        raise ValueError(
            "generated_at must be timezone-aware."
        )

    normalized = (
        generated_at
        .astimezone(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
    )

    return (
        normalized
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def _finding_lines(
    finding: Finding,
) -> list[str]:
    location = (
        "file"
        if finding.location is None
        else (
            (
                "file"
                if (
                    finding
                    .location
                    .row_number
                    is None
                )
                else (
                    "row "
                    f"{finding.location.row_number}"
                )
            )
        )
    )

    field = (
        None
        if finding.location is None
        else finding.location.field_name
    )

    lines = [
        (
            f"### {_code_span(finding.code)}"
        ),
        "",
        f"- Category: {_code_span(finding.category.value)}",
        f"- Severity: {_code_span(finding.severity.value)}",
        f"- Scope: {_code_span(finding.scope.value)}",
        (
            "- Rule: "
            f"{_code_span(finding.rule.rule_id)} "
            f"version {_code_span(finding.rule.rule_version)}"
        ),
        f"- Location: {_code_span(location)}",
    ]

    if field is not None:
        lines.append(
            f"- Field: {_code_span(field)}"
        )

    if finding.entity is not None:
        entity_parts = ", ".join(
            (
                f"{part.field_name}="
                f"{json.dumps(part.value, ensure_ascii=True)}"
            )
            for part
            in finding.entity.key_parts
        )

        lines.append(
            "- Entity: "
            f"{_code_span(finding.entity.entity_type)} "
            f"({_code_span(entity_parts)})"
        )

    lines.extend(
        [
            (
                "- Observed: "
                f"{_literal_text(finding.observed_value)}"
            ),
            (
                "- Expected: "
                f"{_literal_text(finding.expected_value)}"
            ),
            f"- Technical message: {finding.message}",
            "",
        ]
    )

    return lines


def render_markdown_report(
    result: ValidationResult,
    *,
    generated_at: datetime,
) -> str:
    """Render one deterministic technical review report."""

    if not isinstance(
        result,
        ValidationResult,
    ):
        raise TypeError(
            "result must be a ValidationResult."
        )

    timestamp = _utc_text(
        generated_at
    )

    lines = [
        "# Proteomics CSV Validation Technical Review Report",
        "",
        "## Run identification",
        "",
        f"- Report format version: {_code_span(_REPORT_FORMAT_VERSION)}",
        f"- Application version: {_code_span(result.application_version)}",
        f"- Generated at: {_code_span(timestamp)}",
        f"- Input filename: {_code_span(result.input_name)}",
        f"- Validation status: {_code_span(result.status.value)}",
        f"- Rows processed: {_code_span(str(result.rows))}",
        "",
        "## Active profile",
        "",
        f"- Descriptor schema version: {_code_span(result.descriptor_schema_version)}",
        f"- Profile ID: {_code_span(result.profile_id)}",
        f"- Profile version: {_code_span(result.profile_version)}",
        "",
        "## Column mapping",
        "",
        (
            "- Mapping specification version: "
            f"{_code_span(result.column_mapping.specification_version)}"
        ),
        (
            "- Mapping mode: "
            f"{_code_span(result.column_mapping.mode.value)}"
        ),
        (
            "- Resolution status: "
            f"{_code_span('completed' if result.column_mapping.resolution_completed else 'not_reached')}"
        ),
        (
            "- Resolved columns: "
            f"{_code_span(str(len(result.column_mapping.entries)))}"
        ),
        "",
    ]

    if result.column_mapping.entries:
        lines.extend(
            [
                "### Resolved column names",
                "",
            ]
        )

        for entry in result.column_mapping.entries:
            lines.append(
                "- "
                f"{_code_span(entry.source_field)} "
                "-> "
                f"{_code_span(entry.target_field)}"
            )

        lines.append(
            ""
        )

    lines.extend(
        [
        "## Configured rules",
        "",
        ]
    )

    for rule in result.configured_rules:
        lines.append(
            "- "
            f"{_code_span(rule.rule_id)} "
            f"version {_code_span(rule.rule_version)}"
        )

    lines.extend(
        [
            "",
            "## Finding summary",
            "",
            f"- Total findings: {_code_span(str(result.summary.total_findings))}",
            "",
            "### Category counts",
            "",
        ]
    )

    for item in result.summary.category_counts:
        lines.append(
            "- "
            f"{_code_span(item.category.value)}: "
            f"{_code_span(str(item.count))}"
        )

    lines.extend(
        [
            "",
            "### Severity counts",
            "",
        ]
    )

    for item in result.summary.severity_counts:
        lines.append(
            "- "
            f"{_code_span(item.severity.value)}: "
            f"{_code_span(str(item.count))}"
        )

    lines.extend(
        [
            "",
            "### Scope counts",
            "",
        ]
    )

    for item in result.summary.scope_counts:
        lines.append(
            "- "
            f"{_code_span(item.scope.value)}: "
            f"{_code_span(str(item.count))}"
        )

    lines.extend(
        [
            "",
            "### Finding code counts",
            "",
        ]
    )

    if result.summary.code_counts:
        for item in result.summary.code_counts:
            lines.append(
                "- "
                f"{_code_span(item.code)}: "
                f"{_code_span(str(item.count))}"
            )
    else:
        lines.append(
            "- none"
        )

    lines.extend(
        [
            "",
            "## Findings",
            "",
        ]
    )

    if result.findings:
        for finding in result.findings:
            lines.extend(
                _finding_lines(
                    finding
                )
            )
    else:
        lines.extend(
            [
                "No validation findings were detected under the configured rules.",
                "",
            ]
        )

    lines.extend(
        [
            "## Technical interpretation",
            "",
            "Configured rules record detected structural conditions for technical review. Completed runs report the detected conditions. Reviewers decide dataset acceptance. Fatal ingestion conditions stop downstream validation and appear in the report when publication remains possible.",
            "",
            "## Data and scope boundary",
            "",
            f"Version {result.application_version} checks CSV structure, sample identifiers, and required non-key values under the named profile and rule versions. Column mapping renames headers and preserves source values and physical row locations. Caller-supplied explicit mappings define source-to-profile header assignments. Scientific validity of caller-supplied header assignments requires dataset-specific review. Raw LC-MS processing, normalization, statistical analysis, biological or clinical interpretation, repository conformance, and production deployment are outside the application.",
        ]
    )

    return (
        "\n".join(
            lines
        )
        .rstrip(
            "\n"
        )
        + "\n"
    )


def write_markdown_report(
    output_path: Path,
    report_text: str,
    *,
    overwrite: bool,
) -> None:
    """Publish one UTF-8 report without replacing existing output by default."""

    if not isinstance(
        output_path,
        Path,
    ):
        raise TypeError(
            "output_path must be a pathlib.Path."
        )

    if not isinstance(
        report_text,
        str,
    ):
        raise TypeError(
            "report_text must be a string."
        )

    if not isinstance(
        overwrite,
        bool,
    ):
        raise TypeError(
            "overwrite must be boolean."
        )

    if not report_text.endswith(
        "\n"
    ):
        raise OutputWriteError(
            "Report text must end with one LF newline."
        )

    if report_text.endswith(
        "\n\n"
    ):
        raise OutputWriteError(
            "Report text must not end with multiple LF characters."
        )

    try:
        if output_path.exists() and not overwrite:
            raise OutputWriteError(
                "The report target already exists. "
                "Use --overwrite only after reviewing "
                "the selected target."
            )

        parent = output_path.parent
        parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=parent,
                prefix=(
                    f".{output_path.name}."
                ),
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(
                    report_text
                )

                temporary_path = Path(
                    temporary.name
                )

            os.replace(
                temporary_path,
                output_path,
            )

            temporary_path = None
        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()
    except OutputWriteError:
        raise
    except (
        OSError,
        RuntimeError,
    ) as exc:
        raise OutputWriteError(
            "The technical report could not be published."
        ) from exc
