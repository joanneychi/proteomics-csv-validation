"""Immutable domain models for parsed records and validation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, TypeAlias


FindingValue: TypeAlias = (
    None
    | bool
    | int
    | Decimal
    | str
)


class FindingCategory(str, Enum):
    """Supported validation categories in canonical summary order."""

    INGESTION = "ingestion"
    SCHEMA = "schema"
    IDENTIFIER = "identifier"
    MISSINGNESS = "missingness"


class Severity(str, Enum):
    """Controlled technical-review severities."""

    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"


class Scope(str, Enum):
    """Finding scope within one input file."""

    FILE = "file"
    ROW = "row"


class ValidationStatus(str, Enum):
    """Completion state for one validation attempt."""

    COMPLETED = "completed"
    STOPPED_AFTER_INGESTION_FINDING = (
        "stopped_after_ingestion_finding"
    )


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Optional physical CSV location for one finding."""

    row_number: int | None
    field_name: str | None

    def __post_init__(self) -> None:
        if (
            self.row_number is not None
            and self.row_number < 1
        ):
            raise ValueError(
                "row_number must be positive when present."
            )

        if (
            self.field_name is not None
            and self.field_name == ""
        ):
            raise ValueError(
                "field_name cannot be empty when present."
            )


@dataclass(frozen=True, slots=True)
class EntityKeyPart:
    """One named component of a structured entity key."""

    field_name: str
    value: FindingValue

    def __post_init__(self) -> None:
        if self.field_name == "":
            raise ValueError(
                "Entity key field_name cannot be empty."
            )


@dataclass(frozen=True, slots=True)
class EntityReference:
    """Structured reference to the affected record entity."""

    entity_type: str
    key_parts: tuple[EntityKeyPart, ...]

    def __post_init__(self) -> None:
        if self.entity_type == "":
            raise ValueError(
                "entity_type cannot be empty."
            )

        if not self.key_parts:
            raise ValueError(
                "EntityReference requires at least one key part."
            )


@dataclass(frozen=True, slots=True)
class RuleReference:
    """Stable rule identity attached to configured and observed evidence."""

    rule_id: str
    rule_version: str

    def __post_init__(self) -> None:
        if self.rule_id == "":
            raise ValueError(
                "rule_id cannot be empty."
            )

        if self.rule_version == "":
            raise ValueError(
                "rule_version cannot be empty."
            )


@dataclass(frozen=True, slots=True)
class Finding:
    """One immutable technical validation finding."""

    code: str
    category: FindingCategory
    severity: Severity
    scope: Scope
    rule: RuleReference
    location: SourceLocation | None
    entity: EntityReference | None
    observed_value: FindingValue
    expected_value: FindingValue
    message: str

    def __post_init__(self) -> None:
        if self.code == "":
            raise ValueError(
                "Finding code cannot be empty."
            )

        if self.message.strip() == "":
            raise ValueError(
                "Finding message cannot be empty."
            )

        if (
            self.scope is Scope.ROW
            and (
                self.location is None
                or self.location.row_number is None
            )
        ):
            raise ValueError(
                "Row-scope findings require a row_number."
            )


@dataclass(frozen=True, slots=True)
class CategoryCount:
    """Finding count for one category."""

    category: FindingCategory
    count: int


@dataclass(frozen=True, slots=True)
class CodeCount:
    """Finding count for one observed code."""

    code: str
    count: int


@dataclass(frozen=True, slots=True)
class SeverityCount:
    """Finding count for one severity."""

    severity: Severity
    count: int


@dataclass(frozen=True, slots=True)
class ScopeCount:
    """Finding count for one scope."""

    scope: Scope
    count: int


@dataclass(frozen=True, slots=True)
class FindingSummary:
    """Zero-inclusive aggregate counts for one result."""

    total_findings: int
    category_counts: tuple[CategoryCount, ...]
    code_counts: tuple[CodeCount, ...]
    severity_counts: tuple[SeverityCount, ...]
    scope_counts: tuple[ScopeCount, ...]


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """One decoded CSV record and its physical row location."""

    row_number: int
    values: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.row_number < 2:
            raise ValueError(
                "Parsed data rows begin at physical row 2."
            )

        object.__setattr__(
            self,
            "values",
            MappingProxyType(
                dict(
                    self.values
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ParsedTable:
    """One successfully parsed CSV input."""

    input_name: str
    header: tuple[str, ...]
    records: tuple[ParsedRecord, ...]

    def __post_init__(self) -> None:
        if self.input_name == "":
            raise ValueError(
                "input_name cannot be empty."
            )

        if not self.header:
            raise ValueError(
                "ParsedTable requires a header."
            )


@dataclass(frozen=True, slots=True)
class IngestionFailure:
    """Reportable fatal content failure for an accessible input."""

    input_name: str
    finding: Finding


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Complete immutable evidence from one validation attempt."""

    application_version: str
    descriptor_schema_version: str
    profile_id: str
    profile_version: str
    input_name: str
    status: ValidationStatus
    rows: int
    configured_rules: tuple[RuleReference, ...]
    findings: tuple[Finding, ...]
    summary: FindingSummary

    def __post_init__(self) -> None:
        if self.rows < 0:
            raise ValueError(
                "rows cannot be negative."
            )

        if (
            self.summary.total_findings
            != len(
                self.findings
            )
        ):
            raise ValueError(
                "Summary total must equal the number of findings."
            )


FindingSeverity = Severity
FindingScope = Scope
