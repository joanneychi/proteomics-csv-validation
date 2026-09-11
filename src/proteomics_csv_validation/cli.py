"""Command-line interface for the local validation system."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from collections.abc import Sequence

from proteomics_csv_validation import (
    __version__,
)
from proteomics_csv_validation.errors import (
    ColumnMappingError,
    InputAccessError,
    OutputWriteError,
    ProfileError,
)
from proteomics_csv_validation.models import (
    ValidationResult,
    ValidationStatus,
)
from proteomics_csv_validation.pipeline import (
    validate_and_write,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proteomics-csv-validate",
        description=(
            "Validate a processed-sample proteomics "
            "CSV and publish "
            "a Markdown technical review report."
        ),
        allow_abbrev=False,
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to one authorized CSV input.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path for the Markdown technical review report.",
    )

    mapping_group = (
        parser.add_mutually_exclusive_group()
    )

    mapping_group.add_argument(
        "--auto-map",
        action="store_true",
        help=(
            "Resolve conservative lexical variants and "
            "profile field titles to canonical column names."
        ),
    )

    mapping_group.add_argument(
        "--column-map",
        type=Path,
        metavar="FILE",
        help=(
            "Apply an explicit versioned JSON column mapping."
        ),
    )

    parser.add_argument(
        "--profile-version",
        metavar="VERSION",
        help=(
            "Select a registered profile version. "
            "Default 0.2.0 requires all six profile fields; "
            "0.3.0 requires four fields, with "
            "experimental-condition and preparation-batch "
            "metadata optional."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing distinct report target.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=(
            "%(prog)s "
            f"{__version__}"
        ),
    )

    return parser


def _quoted(
    value: str,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
    )


def _print_summary(
    result: ValidationResult,
    output_path: Path,
) -> None:
    print(
        f"status: {result.status.value}"
    )

    print(
        f"input: {_quoted(result.input_name)}"
    )

    print(
        f"rows: {result.rows}"
    )

    print(
        "profile_version: "
        f"{result.profile_version}"
    )

    print(
        "mapping_mode: "
        f"{result.column_mapping.mode.value}"
    )

    print(
        "mapping_resolution: "
        f"{'completed' if result.column_mapping.resolution_completed else 'not_reached'}"
    )

    print(
        "mapped_columns: "
        f"{len(result.column_mapping.entries)}"
    )

    print(
        "total_findings: "
        f"{result.summary.total_findings}"
    )

    print(
        "category_counts:"
    )

    for item in (
        result
        .summary
        .category_counts
    ):
        print(
            "  "
            f"{item.category.value}: "
            f"{item.count}"
        )

    print(
        "finding_code_counts:"
    )

    if result.summary.code_counts:
        for item in (
            result
            .summary
            .code_counts
        ):
            print(
                "  "
                f"{item.code}: "
                f"{item.count}"
            )
    else:
        print(
            "  none"
        )

    print(
        f"report: {_quoted(output_path.name)}"
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the installed command surface and return a process exit code."""

    parser = _parser()

    arguments = parser.parse_args(
        argv
    )

    try:
        validation_options: dict[
            str,
            object,
        ] = {
            "overwrite": (
                arguments.overwrite
            ),
        }

        if arguments.auto_map:
            validation_options[
                "auto_map"
            ] = True

        if (
            arguments.column_map
            is not None
        ):
            validation_options[
                "column_map"
            ] = arguments.column_map

        if (
            arguments.profile_version
            is not None
        ):
            validation_options[
                "profile_version"
            ] = arguments.profile_version

        result = validate_and_write(
            arguments.input,
            arguments.output,
            **validation_options,
        )
    except InputAccessError as exc:
        print(
            f"input error: {exc}",
            file=sys.stderr,
        )

        return 3
    except ProfileError as exc:
        print(
            f"profile error: {exc}",
            file=sys.stderr,
        )

        return 4
    except ColumnMappingError as exc:
        print(
            f"mapping error: {exc}",
            file=sys.stderr,
        )

        return 6
    except OutputWriteError as exc:
        print(
            f"output error: {exc}",
            file=sys.stderr,
        )

        return 5
    except Exception as exc:
        print(
            "internal error: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        return 1

    _print_summary(
        result,
        arguments.output,
    )

    if (
        result.status
        is ValidationStatus
        .STOPPED_AFTER_INGESTION_FINDING
    ):
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
