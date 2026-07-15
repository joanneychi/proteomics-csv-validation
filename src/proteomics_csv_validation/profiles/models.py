"""Immutable models for versioned input-profile definitions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class LogicalType(str, Enum):
    """Logical field types declared by the built-in profile."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"


@dataclass(frozen=True, slots=True)
class MissingValuePolicy:
    """Field-specific missing-value interpretation."""

    blank_is_missing: bool
    whitespace_only_is_missing: bool
    missing_tokens: tuple[str, ...] = ()
    tokens_case_sensitive: bool = True

    def is_missing(
        self,
        raw_value: str,
    ) -> bool:
        """Return whether one preserved CSV value is missing."""

        if not isinstance(
            raw_value,
            str,
        ):
            raise TypeError(
                "Missing-value evaluation requires text."
            )

        if (
            self.blank_is_missing
            and raw_value == ""
        ):
            return True

        if (
            self.whitespace_only_is_missing
            and raw_value != ""
            and raw_value.strip() == ""
        ):
            return True

        if self.tokens_case_sensitive:
            return (
                raw_value
                in self.missing_tokens
            )

        folded = raw_value.casefold()

        return any(
            folded
            == token.casefold()
            for token
            in self.missing_tokens
        )


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    """One physical field in a profile."""

    name: str
    title: str
    description: str
    logical_type: LogicalType
    required: bool
    missing_value_policy: MissingValuePolicy

    def __post_init__(self) -> None:
        if self.name == "":
            raise ValueError(
                "Field name cannot be empty."
            )

        if self.title == "":
            raise ValueError(
                "Field title cannot be empty."
            )


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """Semantic definition for one quantitative summary field."""

    field_name: str
    metric_id: str
    unit: str
    scale: str
    minimum: int | Decimal
    value_origin: str
    normalization_state: str
    aggregation: str | None

    def __post_init__(self) -> None:
        if self.field_name == "":
            raise ValueError(
                "Metric field_name cannot be empty."
            )

        if self.metric_id == "":
            raise ValueError(
                "metric_id cannot be empty."
            )


@dataclass(frozen=True, slots=True)
class CsvDialectDefinition:
    """Physical CSV contract for one profile."""

    encoding: str
    delimiter: str
    quote_character: str
    header_required: bool
    allow_utf8_bom: bool
    allow_blank_records: bool
    allow_embedded_newlines: bool
    decimal_separator: str

    def __post_init__(self) -> None:
        if len(
            self.delimiter
        ) != 1:
            raise ValueError(
                "CSV delimiter must be one character."
            )

        if len(
            self.quote_character
        ) != 1:
            raise ValueError(
                "CSV quote character must be one character."
            )


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    """Complete immutable profile used by the current validation engine."""

    descriptor_schema_version: str
    profile_id: str
    profile_version: str
    entity_type: str
    title: str
    description: str
    record_grain: str
    file_grain: str
    fields: tuple[FieldDefinition, ...]
    key_fields: tuple[str, ...]
    factor_fields: tuple[str, ...]
    batch_fields: tuple[str, ...]
    metrics: tuple[MetricDefinition, ...]
    csv_dialect: CsvDialectDefinition

    def __post_init__(self) -> None:
        scalar_values = (
            self.descriptor_schema_version,
            self.profile_id,
            self.profile_version,
            self.entity_type,
            self.title,
            self.description,
            self.record_grain,
            self.file_grain,
        )

        if any(
            value == ""
            for value
            in scalar_values
        ):
            raise ValueError(
                "Profile scalar metadata cannot be empty."
            )

        names = tuple(
            field.name
            for field
            in self.fields
        )

        if not names:
            raise ValueError(
                "A profile requires at least one field."
            )

        if len(
            set(
                names
            )
        ) != len(
            names
        ):
            raise ValueError(
                "Profile field names must be unique."
            )

        known = set(
            names
        )

        references = (
            *self.key_fields,
            *self.factor_fields,
            *self.batch_fields,
            *(
                metric.field_name
                for metric
                in self.metrics
            ),
        )

        unknown = tuple(
            name
            for name
            in references
            if name not in known
        )

        if unknown:
            raise ValueError(
                "Profile references unknown fields: "
                f"{unknown!r}."
            )

    @property
    def required_fields(
        self,
    ) -> tuple[FieldDefinition, ...]:
        """Return required fields in deterministic profile order."""

        return tuple(
            field
            for field
            in self.fields
            if field.required
        )

    def field(
        self,
        name: str,
    ) -> FieldDefinition:
        """Return one field definition by exact physical name."""

        for field in self.fields:
            if field.name == name:
                return field

        raise KeyError(
            name
        )
