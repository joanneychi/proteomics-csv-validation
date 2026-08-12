"""Deterministic resolution of input column names to profile field names."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from proteomics_csv_validation.errors import (
    ColumnMappingError,
)
from proteomics_csv_validation.models import (
    ColumnMappingEntry,
    ColumnMappingEvidence,
    ColumnMappingMode,
    ParsedRecord,
    ParsedTable,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


COLUMN_MAPPING_SPECIFICATION_VERSION = "1.0.0"

_SEPARATOR_PATTERN = re.compile(
    r"[ _-]+"
)


def _normalized_label(
    value: str,
) -> str:
    """Return the conservative lexical key used by automatic mapping."""

    return _SEPARATOR_PATTERN.sub(
        "_",
        value.strip(),
    ).casefold()


def _strict_object(
    pairs: list[
        tuple[
            str,
            Any,
        ]
    ],
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate JSON key: {key!r}"
            )

        result[key] = value

    return result


def _reject_constant(
    value: str,
) -> None:
    raise ValueError(
        f"Nonstandard JSON constant: {value}"
    )


def _mapping_mode(
    *,
    auto_map: bool,
    column_map: Path | None,
) -> ColumnMappingMode:
    if not isinstance(
        auto_map,
        bool,
    ):
        raise TypeError(
            "auto_map must be boolean."
        )

    if (
        column_map is not None
        and not isinstance(
            column_map,
            Path,
        )
    ):
        raise TypeError(
            "column_map must be a pathlib.Path or None."
        )

    if (
        auto_map
        and column_map is not None
    ):
        raise ColumnMappingError(
            "Automatic and explicit column mapping "
            "cannot be requested together."
        )

    if column_map is not None:
        return ColumnMappingMode.EXPLICIT

    if auto_map:
        return ColumnMappingMode.AUTOMATIC

    return ColumnMappingMode.STRICT


def pending_column_mapping_evidence(
    *,
    auto_map: bool = False,
    column_map: Path | None = None,
) -> ColumnMappingEvidence:
    """Return requested mapping mode before the CSV header is available."""

    return ColumnMappingEvidence(
        specification_version=(
            COLUMN_MAPPING_SPECIFICATION_VERSION
        ),
        mode=_mapping_mode(
            auto_map=auto_map,
            column_map=column_map,
        ),
        resolution_completed=False,
        entries=(),
    )


def _completed_evidence(
    mode: ColumnMappingMode,
    entries: tuple[
        ColumnMappingEntry,
        ...,
    ],
) -> ColumnMappingEvidence:
    return ColumnMappingEvidence(
        specification_version=(
            COLUMN_MAPPING_SPECIFICATION_VERSION
        ),
        mode=mode,
        resolution_completed=True,
        entries=entries,
    )


def _apply_entries(
    table: ParsedTable,
    entries: tuple[
        ColumnMappingEntry,
        ...,
    ],
) -> ParsedTable:
    rename = {
        entry.source_field: entry.target_field
        for entry in entries
    }

    header = tuple(
        rename.get(
            field,
            field,
        )
        for field in table.header
    )

    if len(
        set(
            header
        )
    ) != len(
        header
    ):
        raise ColumnMappingError(
            "Column mapping would create duplicate "
            "resolved header names."
        )

    records = tuple(
        ParsedRecord(
            row_number=record.row_number,
            values={
                rename.get(
                    field,
                    field,
                ): record.values[
                    field
                ]
                for field in table.header
            },
        )
        for record in table.records
    )

    return ParsedTable(
        input_name=table.input_name,
        header=header,
        records=records,
    )


def _automatic_entries(
    table: ParsedTable,
    profile: ProfileDefinition,
) -> tuple[
    ColumnMappingEntry,
    ...,
]:
    canonical_names = tuple(
        field.name
        for field in profile.fields
    )

    canonical_set = set(
        canonical_names
    )

    alias_targets: dict[
        str,
        set[str],
    ] = {}

    for field in profile.fields:
        for alias in (
            field.name,
            field.title,
        ):
            key = _normalized_label(
                alias
            )

            alias_targets.setdefault(
                key,
                set(),
            ).add(
                field.name
            )

    candidates: dict[
        str,
        list[str],
    ] = {
        name: []
        for name in canonical_names
    }

    for source in table.header:
        if source in canonical_set:
            continue

        targets = alias_targets.get(
            _normalized_label(
                source
            ),
            set(),
        )

        if not targets:
            continue

        if len(
            targets
        ) != 1:
            raise ColumnMappingError(
                "Automatic column mapping found "
                f"ambiguous profile targets for {source!r}."
            )

        target = next(
            iter(
                targets
            )
        )

        candidates[
            target
        ].append(
            source
        )

    entries: list[
        ColumnMappingEntry
    ] = []

    for target in canonical_names:
        sources = candidates[
            target
        ]

        if not sources:
            continue

        if target in table.header:
            raise ColumnMappingError(
                "Automatic column mapping would "
                "collide with the existing canonical "
                f"column {target!r}."
            )

        if len(
            sources
        ) > 1:
            raise ColumnMappingError(
                "Automatic column mapping found "
                f"multiple source columns for {target!r}: "
                f"{tuple(sources)!r}."
            )

        entries.append(
            ColumnMappingEntry(
                source_field=sources[
                    0
                ],
                target_field=target,
            )
        )

    return tuple(
        entries
    )


def _load_explicit_document(
    mapping_path: Path,
) -> dict[
    str,
    Any,
]:
    mapping_name = (
        mapping_path.name
    )

    try:
        if not mapping_path.is_file():
            raise ColumnMappingError(
                "Column-mapping file is not an "
                "accessible regular file: "
                f"{mapping_name!r}."
            )

        text = mapping_path.read_text(
            encoding="utf-8-sig"
        )
    except ColumnMappingError:
        raise
    except (
        OSError,
        RuntimeError,
        UnicodeError,
    ) as exc:
        raise ColumnMappingError(
            "Column-mapping file could not be read: "
            f"{mapping_name!r}."
        ) from exc

    try:
        loaded = json.loads(
            text,
            object_pairs_hook=(
                _strict_object
            ),
            parse_constant=(
                _reject_constant
            ),
        )
    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise ColumnMappingError(
            "Column-mapping file is not valid strict JSON: "
            f"{mapping_name!r}."
        ) from exc

    if not isinstance(
        loaded,
        dict,
    ):
        raise ColumnMappingError(
            "Column-mapping document must be a JSON object."
        )

    expected_keys = {
        "mapping_specification_version",
        "columns",
    }

    if set(
        loaded
    ) != expected_keys:
        raise ColumnMappingError(
            "Column-mapping document must contain exactly "
            "'mapping_specification_version' and 'columns'."
        )

    version = loaded[
        "mapping_specification_version"
    ]

    if version != (
        COLUMN_MAPPING_SPECIFICATION_VERSION
    ):
        raise ColumnMappingError(
            "Unsupported column-mapping specification "
            f"version: {version!r}."
        )

    columns = loaded[
        "columns"
    ]

    if not isinstance(
        columns,
        dict,
    ):
        raise ColumnMappingError(
            "Column-mapping 'columns' must be a JSON object."
        )

    if not columns:
        raise ColumnMappingError(
            "Explicit column mapping requires at least one entry."
        )

    return columns


def _explicit_entries(
    table: ParsedTable,
    profile: ProfileDefinition,
    mapping_path: Path,
) -> tuple[
    ColumnMappingEntry,
    ...,
]:
    columns = _load_explicit_document(
        mapping_path
    )

    profile_names = tuple(
        field.name
        for field in profile.fields
    )

    profile_set = set(
        profile_names
    )

    source_header = set(
        table.header
    )

    sources_seen: set[
        str
    ] = set()

    source_by_target: dict[
        str,
        str,
    ] = {}

    for target, source in columns.items():
        if (
            not isinstance(
                target,
                str,
            )
            or target == ""
        ):
            raise ColumnMappingError(
                "Column-mapping targets must be nonempty strings."
            )

        if target not in profile_set:
            raise ColumnMappingError(
                "Column mapping references an unknown "
                f"profile field: {target!r}."
            )

        if (
            not isinstance(
                source,
                str,
            )
            or source == ""
        ):
            raise ColumnMappingError(
                "Column-mapping source names must be "
                "nonempty strings."
            )

        if source not in source_header:
            raise ColumnMappingError(
                "Column mapping references a source "
                f"column that is absent: {source!r}."
            )

        if source == target:
            raise ColumnMappingError(
                "Explicit column mapping must not repeat "
                f"an already canonical name: {target!r}."
            )

        if (
            source in profile_set
            and source != target
        ):
            raise ColumnMappingError(
                "Explicit column mapping cannot repurpose "
                f"canonical profile field {source!r}."
            )

        if target in source_header:
            raise ColumnMappingError(
                "Explicit column mapping would collide "
                "with the existing canonical column "
                f"{target!r}."
            )

        if source in sources_seen:
            raise ColumnMappingError(
                "One source column cannot map to more "
                f"than one profile field: {source!r}."
            )

        sources_seen.add(
            source
        )

        source_by_target[
            target
        ] = source

    return tuple(
        ColumnMappingEntry(
            source_field=(
                source_by_target[
                    target
                ]
            ),
            target_field=target,
        )
        for target in profile_names
        if target in source_by_target
    )


def resolve_column_mapping(
    table: ParsedTable,
    profile: ProfileDefinition,
    *,
    auto_map: bool = False,
    column_map: Path | None = None,
) -> tuple[
    ParsedTable,
    ColumnMappingEvidence,
]:
    """Resolve requested column names and preserve all source values."""

    if not isinstance(
        table,
        ParsedTable,
    ):
        raise TypeError(
            "table must be a ParsedTable."
        )

    if not isinstance(
        profile,
        ProfileDefinition,
    ):
        raise TypeError(
            "profile must be a ProfileDefinition."
        )

    mode = _mapping_mode(
        auto_map=auto_map,
        column_map=column_map,
    )

    if mode is ColumnMappingMode.STRICT:
        entries: tuple[
            ColumnMappingEntry,
            ...,
        ] = ()
    elif mode is ColumnMappingMode.AUTOMATIC:
        entries = _automatic_entries(
            table,
            profile,
        )
    else:
        assert column_map is not None

        entries = _explicit_entries(
            table,
            profile,
            column_map,
        )

    mapped = _apply_entries(
        table,
        entries,
    )

    return (
        mapped,
        _completed_evidence(
            mode,
            entries,
        ),
    )
