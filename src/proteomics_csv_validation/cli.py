"""Command-line interface for the local validation prototype."""

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
            "Validate a synthetic proteomics "
            "processed-sample CSV and publish "
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
        result = validate_and_write(
            arguments.input,
            arguments.output,
            overwrite=(
                arguments.overwrite
            ),
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
