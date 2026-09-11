"""CSV ingestion and reportable parse-integrity review."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from proteomics_csv_validation.errors import (
    InputAccessError,
)
from proteomics_csv_validation.models import (
    Finding,
    FindingCategory,
    IngestionFailure,
    ParsedRecord,
    ParsedTable,
    RuleReference,
    Scope,
    Severity,
    SourceLocation,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


INPUT_LIMITS_RULE = RuleReference(
    rule_id="ingestion.input_limits",
    rule_version="1.0.0",
)

CSV_PARSE_RULE = RuleReference(
    rule_id="ingestion.csv_parse",
    rule_version="1.0.0",
)

INGESTION_RULES = (
    INPUT_LIMITS_RULE,
    CSV_PARSE_RULE,
)

_MAX_INPUT_BYTES = 10_000_000
_MAX_ROWS = 100_000
_MAX_COLUMNS = 1_000


def _parse_error(
    input_name: str,
    message: str,
) -> IngestionFailure:
    return IngestionFailure(
        input_name=input_name,
        finding=Finding(
            code="INGESTION_CSV_PARSE_ERROR",
            category=FindingCategory.INGESTION,
            severity=Severity.ERROR,
            scope=Scope.FILE,
            rule=CSV_PARSE_RULE,
            location=SourceLocation(
                row_number=None,
                field_name=None,
            ),
            entity=None,
            observed_value=None,
            expected_value="parseable_csv",
            message=message,
        ),
    )


def _limit_error(
    input_name: str,
    *,
    observed_value: int,
    expected_value: str,
    message: str,
) -> IngestionFailure:
    return IngestionFailure(
        input_name=input_name,
        finding=Finding(
            code="INGESTION_INPUT_LIMIT_EXCEEDED",
            category=FindingCategory.INGESTION,
            severity=Severity.ERROR,
            scope=Scope.FILE,
            rule=INPUT_LIMITS_RULE,
            location=SourceLocation(
                row_number=None,
                field_name=None,
            ),
            entity=None,
            observed_value=observed_value,
            expected_value=expected_value,
            message=message,
        ),
    )


def ingest_csv(
    input_path: Path,
    profile: ProfileDefinition,
) -> ParsedTable | IngestionFailure:
    """Read one accessible CSV into immutable records or a stopped finding."""

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

    input_name = input_path.name

    try:
        if not input_path.is_file():
            raise InputAccessError(
                "Input is not an accessible regular file: "
                f"{input_name!r}."
            )

        if input_path.suffix.lower() != ".csv":
            raise InputAccessError(
                "Input must use the .csv extension: "
                f"{input_name!r}."
            )

        data = input_path.read_bytes()
    except InputAccessError:
        raise
    except (
        OSError,
        RuntimeError,
    ) as exc:
        raise InputAccessError(
            "Input could not be read: "
            f"{input_name!r}."
        ) from exc

    if len(
        data
    ) > _MAX_INPUT_BYTES:
        return _limit_error(
            input_name,
            observed_value=len(
                data
            ),
            expected_value=(
                f"at_most_{_MAX_INPUT_BYTES}_bytes"
            ),
            message=(
                "Input exceeded the configured "
                "input byte limit."
            ),
        )

    if data == b"":
        return _parse_error(
            input_name,
            "The accessible CSV input is empty.",
        )

    if data.startswith(
        b"\xef\xbb\xbf"
    ):
        if not (
            profile
            .csv_dialect
            .allow_utf8_bom
        ):
            return _parse_error(
                input_name,
                "A UTF-8 byte-order mark is not permitted.",
            )

        data = data[
            3:
        ]

    try:
        text = data.decode(
            profile.csv_dialect.encoding
        )
    except UnicodeDecodeError:
        return _parse_error(
            input_name,
            "The CSV input is not valid UTF-8 text.",
        )

    if "\x00" in text:
        return _parse_error(
            input_name,
            "The CSV input contains a NUL character.",
        )

    stream = io.StringIO(
        text,
        newline="",
    )

    reader = csv.reader(
        stream,
        delimiter=(
            profile
            .csv_dialect
            .delimiter
        ),
        quotechar=(
            profile
            .csv_dialect
            .quote_character
        ),
        strict=True,
    )

    rows: list[
        list[str]
    ] = []

    previous_line_number = 0

    try:
        for row in reader:
            current_line_number = (
                reader.line_num
            )

            if (
                not profile
                .csv_dialect
                .allow_embedded_newlines
                and current_line_number
                != previous_line_number
                + 1
            ):
                return _parse_error(
                    input_name,
                    "Embedded quoted line breaks are unsupported.",
                )

            rows.append(
                row
            )

            previous_line_number = (
                current_line_number
            )
    except csv.Error as exc:
        return _parse_error(
            input_name,
            "The CSV parser rejected malformed content: "
            f"{exc}.",
        )

    if not rows:
        return _parse_error(
            input_name,
            "The CSV input does not contain a header.",
        )

    header = tuple(
        rows[
            0
        ]
    )

    if (
        not header
        or all(
            item == ""
            for item
            in header
        )
    ):
        return _parse_error(
            input_name,
            "The CSV header is missing.",
        )

    if len(
        header
    ) > _MAX_COLUMNS:
        return _limit_error(
            input_name,
            observed_value=len(
                header
            ),
            expected_value=(
                f"at_most_{_MAX_COLUMNS}_columns"
            ),
            message=(
                "Input exceeded the configured "
                "input column limit."
            ),
        )

    if len(
        set(
            header
        )
    ) != len(
        header
    ):
        return _parse_error(
            input_name,
            "The CSV header contains duplicate names.",
        )

    data_rows = rows[
        1:
    ]

    if len(
        data_rows
    ) > _MAX_ROWS:
        return _limit_error(
            input_name,
            observed_value=len(
                data_rows
            ),
            expected_value=(
                f"at_most_{_MAX_ROWS}_records"
            ),
            message=(
                "Input exceeded the configured "
                "input row limit."
            ),
        )

    records: list[
        ParsedRecord
    ] = []

    for index, row in enumerate(
        data_rows,
        start=2,
    ):
        if (
            not profile
            .csv_dialect
            .allow_blank_records
            and (
                not row
                or all(
                    value == ""
                    for value
                    in row
                )
            )
        ):
            return _parse_error(
                input_name,
                "Blank physical CSV records are unsupported.",
            )

        if len(
            row
        ) != len(
            header
        ):
            return _parse_error(
                input_name,
                "A CSV record contains a different "
                "field count than the header.",
            )

        records.append(
            ParsedRecord(
                row_number=index,
                values=dict(
                    zip(
                        header,
                        row,
                        strict=True,
                    )
                ),
            )
        )

    return ParsedTable(
        input_name=input_name,
        header=header,
        records=tuple(
            records
        ),
    )
