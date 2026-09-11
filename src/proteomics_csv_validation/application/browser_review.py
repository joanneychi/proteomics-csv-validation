"""Application-facing workflow facade for one browser Review submission."""

from __future__ import annotations
from collections import Counter

from dataclasses import dataclass
import hashlib
import json
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from proteomics_csv_validation.application.publication import (
    PublicationService,
)
from proteomics_csv_validation.application.review_execution import (
    QueuedReviewExecution,
    ResultPublicationError,
    ResultPublicationRecoveryError,
    ReviewExecutionService,
)
from proteomics_csv_validation.application.run_lifecycle import (
    RunLifecycleService,
)
from proteomics_csv_validation.application.structural_review import (
    StructuralReviewFailure,
    StructuralReviewRequest,
)
from proteomics_csv_validation.domain.result_artifact import (
    RESULT_BUNDLE_ARTIFACT_KIND,
    RESULT_BUNDLE_SCHEMA_ID,
    RESULT_BUNDLE_SCHEMA_VERSION,
    ResultBundleConfiguration,
    ResultStoreError,
    SourceFileEvidence,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    LedgerRecordNotFoundError,
    RunState,
)

_WORKSPACE_ID = "local-default"


class ResultReader(
    Protocol
):
    """Port required for verified result reads."""

    def read_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bytes:
        ...


@dataclass(
    frozen=True,
    slots=True,
)
class ReviewHistoryEntryView:
    """Application-safe durable run-history evidence for presentation."""

    run_id: str
    configuration_id: str
    configuration_sha256: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    source_display_name: str
    source_sha256: str
    source_byte_count: int
    profile_version: str
    mapping_mode: str

@dataclass(
    frozen=True,
    slots=True,
)
class ReviewSubmission:
    """Byte-bound input needed to create and execute one Review run."""

    input_path: Path
    profile_version: str
    mapping_mode: str
    source_display_name: str
    source_sha256: str
    source_byte_count: int
    mapping_path: Path | None = None
    mapping_display_name: str | None = None
    mapping_sha256: str | None = None
    mapping_byte_count: int | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class ResultRuleView:
    """Presentation-safe configured-rule identity."""

    rule_id: str
    rule_version: str


@dataclass(
    frozen=True,
    slots=True,
)
class ResultFileEvidenceView:
    """Presentation-safe submitted-file evidence."""

    display_name: str
    sha256: str
    byte_count: int


@dataclass(
    frozen=True,
    slots=True,
)
class ResultTaggedValueView:
    """Typed finding value rendered without exposing implementation objects."""

    value_type: str
    display_value: str


@dataclass(
    frozen=True,
    slots=True,
)
class ResultLocationView:
    """Presentation-safe source location."""

    row_number: int | None
    field_name: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class ResultEntityKeyPartView:
    """One stable entity-key component."""

    field_name: str
    value: ResultTaggedValueView


@dataclass(
    frozen=True,
    slots=True,
)
class ResultEntityView:
    """Presentation-safe finding entity."""

    entity_type: str
    key_parts: tuple[
        ResultEntityKeyPartView,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class ResultFindingView:
    """One fully reconciled structural finding."""

    code: str
    category: str
    severity: str
    scope: str
    rule: ResultRuleView
    location: ResultLocationView
    entity: ResultEntityView | None
    observed_value: ResultTaggedValueView
    expected_value: ResultTaggedValueView
    message: str


@dataclass(
    frozen=True,
    slots=True,
)
class ResultCountView:
    """One reconciled summary count."""

    label: str
    count: int


@dataclass(
    frozen=True,
    slots=True,
)
class ResultSummaryView:
    """Reconciled finding summary."""

    total_findings: int
    category_counts: tuple[
        ResultCountView,
        ...,
    ]
    code_counts: tuple[
        ResultCountView,
        ...,
    ]
    severity_counts: tuple[
        ResultCountView,
        ...,
    ]
    scope_counts: tuple[
        ResultCountView,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class ResultMappingEntryView:
    """One resolved source-to-canonical column mapping."""

    source_field: str
    target_field: str


@dataclass(
    frozen=True,
    slots=True,
)
class ResultColumnMappingView:
    """Presentation-safe column-mapping evidence."""

    specification_version: str
    mode: str
    resolution_completed: bool
    entries: tuple[
        ResultMappingEntryView,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class ResultConfigurationView:
    """Reconciled immutable configuration evidence."""

    profile_version: str
    mapping_mode: str
    source: ResultFileEvidenceView
    column_mapping_source: (
        ResultFileEvidenceView
        | None
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ResultValidationView:
    """Fully reconciled validation evidence."""

    application_version: str
    descriptor_schema_version: str
    profile_id: str
    profile_version: str
    status: str
    rows: int
    configured_rules: tuple[
        ResultRuleView,
        ...,
    ]
    column_mapping: ResultColumnMappingView
    summary: ResultSummaryView
    findings: tuple[
        ResultFindingView,
        ...,
    ]


def _exact_object(
    value: object,
    *,
    keys: set[str],
    label: str,
) -> dict[
    str,
    object,
]:
    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            label
            + " must be an object."
        )

    if set(
        value
    ) != keys:
        raise ValueError(
            label
            + " has an unexpected shape."
        )

    return value


def _nonempty_string(
    value: object,
    *,
    label: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or value == ""
    ):
        raise ValueError(
            label
            + " must be a nonempty string."
        )

    return value


def _nonnegative_integer(
    value: object,
    *,
    label: str,
) -> int:
    if (
        type(
            value
        )
        is not int
        or value < 0
    ):
        raise ValueError(
            label
            + " must be a nonnegative integer."
        )

    return value


def _file_evidence_view(
    value: object,
) -> ResultFileEvidenceView:
    document = _exact_object(
        value,
        keys={
            "display_name",
            "sha256",
            "byte_count",
        },
        label="File evidence",
    )

    display_name = _nonempty_string(
        document[
            "display_name"
        ],
        label="File display name",
    )

    if (
        "/"
        in display_name
        or "\\"
        in display_name
    ):
        raise ValueError(
            "File evidence display name must not contain a path."
        )

    digest = _nonempty_string(
        document[
            "sha256"
        ],
        label="File SHA-256",
    )

    if (
        len(
            digest
        )
        != 64
        or any(
            character
            not in "0123456789abcdef"
            for character in digest
        )
    ):
        raise ValueError(
            "File SHA-256 is invalid."
        )

    byte_count = (
        _nonnegative_integer(
            document[
                "byte_count"
            ],
            label="File byte count",
        )
    )

    return ResultFileEvidenceView(
        display_name=display_name,
        sha256=digest,
        byte_count=byte_count,
    )


def _tagged_value_view(
    value: object,
) -> ResultTaggedValueView:
    document = _exact_object(
        value,
        keys={
            "type",
            "value",
        },
        label="Tagged value",
    )

    value_type = (
        _nonempty_string(
            document[
                "type"
            ],
            label="Tagged-value type",
        )
    )

    raw = document[
        "value"
    ]

    if value_type == "null":
        if raw is not None:
            raise ValueError(
                "Null tagged value has an invalid payload."
            )

        display = "null"

    elif value_type == "boolean":
        if type(
            raw
        ) is not bool:
            raise ValueError(
                "Boolean tagged value has an invalid payload."
            )

        display = (
            "true"
            if raw
            else "false"
        )

    elif value_type == "integer":
        if type(
            raw
        ) is not int:
            raise ValueError(
                "Integer tagged value has an invalid payload."
            )

        display = str(
            raw
        )

    elif value_type in {
        "string",
        "decimal",
    }:
        if not isinstance(
            raw,
            str,
        ):
            raise ValueError(
                "String-like tagged value has an invalid payload."
            )

        display = raw

    else:
        raise ValueError(
            "Tagged-value type is unsupported."
        )

    return ResultTaggedValueView(
        value_type=value_type,
        display_value=display,
    )


def _rule_view(
    value: object,
) -> ResultRuleView:
    document = _exact_object(
        value,
        keys={
            "rule_id",
            "rule_version",
        },
        label="Rule reference",
    )

    return ResultRuleView(
        rule_id=_nonempty_string(
            document[
                "rule_id"
            ],
            label="Rule ID",
        ),
        rule_version=(
            _nonempty_string(
                document[
                    "rule_version"
                ],
                label="Rule version",
            )
        ),
    )


def _location_view(
    value: object,
) -> ResultLocationView:
    document = _exact_object(
        value,
        keys={
            "row_number",
            "field_name",
        },
        label="Finding location",
    )

    row_number = document[
        "row_number"
    ]

    if (
        row_number is not None
        and (
            type(
                row_number
            )
            is not int
            or row_number < 1
        )
    ):
        raise ValueError(
            "Finding row number is invalid."
        )

    field_name = document[
        "field_name"
    ]

    if (
        field_name is not None
        and (
            not isinstance(
                field_name,
                str,
            )
            or field_name == ""
        )
    ):
        raise ValueError(
            "Finding field name is invalid."
        )

    return ResultLocationView(
        row_number=row_number,
        field_name=field_name,
    )


def _entity_view(
    value: object,
) -> ResultEntityView | None:
    if value is None:
        return None

    document = _exact_object(
        value,
        keys={
            "entity_type",
            "key_parts",
        },
        label="Finding entity",
    )

    raw_parts = document[
        "key_parts"
    ]

    if not isinstance(
        raw_parts,
        list,
    ):
        raise ValueError(
            "Finding entity key parts must be an array."
        )

    parts: list[
        ResultEntityKeyPartView
    ] = []

    for raw_part in raw_parts:
        part = _exact_object(
            raw_part,
            keys={
                "field_name",
                "value",
            },
            label="Entity key part",
        )

        parts.append(
            ResultEntityKeyPartView(
                field_name=(
                    _nonempty_string(
                        part[
                            "field_name"
                        ],
                        label=(
                            "Entity key field"
                        ),
                    )
                ),
                value=(
                    _tagged_value_view(
                        part[
                            "value"
                        ]
                    )
                ),
            )
        )

    if not parts:
        raise ValueError(
            "Finding entity must contain at least one key part."
        )

    return ResultEntityView(
        entity_type=(
            _nonempty_string(
                document[
                    "entity_type"
                ],
                label="Entity type",
            )
        ),
        key_parts=tuple(
            parts
        ),
    )


def _finding_view(
    value: object,
) -> ResultFindingView:
    document = _exact_object(
        value,
        keys={
            "code",
            "category",
            "severity",
            "scope",
            "rule",
            "location",
            "entity",
            "observed_value",
            "expected_value",
            "message",
        },
        label="Finding",
    )

    category = _nonempty_string(
        document[
            "category"
        ],
        label="Finding category",
    )

    if category not in {
        "ingestion",
        "schema",
        "identifier",
        "missingness",
    }:
        raise ValueError(
            "Finding category is invalid."
        )

    severity = _nonempty_string(
        document[
            "severity"
        ],
        label="Finding severity",
    )

    if severity not in {
        "error",
        "warning",
        "information",
    }:
        raise ValueError(
            "Finding severity is invalid."
        )

    scope = _nonempty_string(
        document[
            "scope"
        ],
        label="Finding scope",
    )

    if scope not in {
        "file",
        "row",
    }:
        raise ValueError(
            "Finding scope is invalid."
        )

    return ResultFindingView(
        code=_nonempty_string(
            document[
                "code"
            ],
            label="Finding code",
        ),
        category=category,
        severity=severity,
        scope=scope,
        rule=_rule_view(
            document[
                "rule"
            ]
        ),
        location=_location_view(
            document[
                "location"
            ]
        ),
        entity=_entity_view(
            document[
                "entity"
            ]
        ),
        observed_value=(
            _tagged_value_view(
                document[
                    "observed_value"
                ]
            )
        ),
        expected_value=(
            _tagged_value_view(
                document[
                    "expected_value"
                ]
            )
        ),
        message=_nonempty_string(
            document[
                "message"
            ],
            label="Finding message",
        ),
    )


def _count_views(
    value: object,
    *,
    label_key: str,
    label: str,
) -> tuple[
    ResultCountView,
    ...,
]:
    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            label
            + " must be an array."
        )

    result: list[
        ResultCountView
    ] = []

    seen: set[
        str
    ] = set()

    for raw in value:
        document = _exact_object(
            raw,
            keys={
                label_key,
                "count",
            },
            label=label,
        )

        name = _nonempty_string(
            document[
                label_key
            ],
            label=(
                label
                + " label"
            ),
        )

        if name in seen:
            raise ValueError(
                label
                + " contains a duplicate label."
            )

        seen.add(
            name
        )

        result.append(
            ResultCountView(
                label=name,
                count=(
                    _nonnegative_integer(
                        document[
                            "count"
                        ],
                        label=(
                            label
                            + " count"
                        ),
                    )
                ),
            )
        )

    return tuple(
        result
    )


def _summary_view(
    value: object,
) -> ResultSummaryView:
    document = _exact_object(
        value,
        keys={
            "total_findings",
            "category_counts",
            "code_counts",
            "severity_counts",
            "scope_counts",
        },
        label="Finding summary",
    )

    return ResultSummaryView(
        total_findings=(
            _nonnegative_integer(
                document[
                    "total_findings"
                ],
                label=(
                    "Total findings"
                ),
            )
        ),
        category_counts=(
            _count_views(
                document[
                    "category_counts"
                ],
                label_key="category",
                label=(
                    "Category counts"
                ),
            )
        ),
        code_counts=(
            _count_views(
                document[
                    "code_counts"
                ],
                label_key="code",
                label="Code counts",
            )
        ),
        severity_counts=(
            _count_views(
                document[
                    "severity_counts"
                ],
                label_key="severity",
                label=(
                    "Severity counts"
                ),
            )
        ),
        scope_counts=(
            _count_views(
                document[
                    "scope_counts"
                ],
                label_key="scope",
                label="Scope counts",
            )
        ),
    )


def _mapping_view(
    value: object,
) -> ResultColumnMappingView:
    document = _exact_object(
        value,
        keys={
            "specification_version",
            "mode",
            "resolution_completed",
            "entries",
        },
        label="Column-mapping evidence",
    )

    mode = _nonempty_string(
        document[
            "mode"
        ],
        label="Column-mapping mode",
    )

    if mode not in {
        "strict",
        "automatic",
        "explicit",
    }:
        raise ValueError(
            "Column-mapping mode is invalid."
        )

    resolution_completed = document[
        "resolution_completed"
    ]

    if type(
        resolution_completed
    ) is not bool:
        raise ValueError(
            "Column-mapping completion flag is invalid."
        )

    raw_entries = document[
        "entries"
    ]

    if not isinstance(
        raw_entries,
        list,
    ):
        raise ValueError(
            "Column-mapping entries must be an array."
        )

    entries: list[
        ResultMappingEntryView
    ] = []

    sources_seen: set[
        str
    ] = set()

    targets_seen: set[
        str
    ] = set()

    for raw in raw_entries:
        entry = _exact_object(
            raw,
            keys={
                "source_field",
                "target_field",
            },
            label="Column-mapping entry",
        )

        source_field = (
            _nonempty_string(
                entry[
                    "source_field"
                ],
                label=(
                    "Mapping source field"
                ),
            )
        )

        target_field = (
            _nonempty_string(
                entry[
                    "target_field"
                ],
                label=(
                    "Mapping target field"
                ),
            )
        )

        if (
            source_field
            == target_field
        ):
            raise ValueError(
                "Column-mapping entries must rename a source field."
            )

        if source_field in sources_seen:
            raise ValueError(
                "Column-mapping source fields must be unique."
            )

        if target_field in targets_seen:
            raise ValueError(
                "Column-mapping target fields must be unique."
            )

        sources_seen.add(
            source_field
        )

        targets_seen.add(
            target_field
        )

        entries.append(
            ResultMappingEntryView(
                source_field=source_field,
                target_field=target_field,
            )
        )

    if (
        not resolution_completed
        and entries
    ):
        raise ValueError(
            "Incomplete column mapping must not contain resolved entries."
        )

    if (
        mode == "strict"
        and entries
    ):
        raise ValueError(
            "Strict mapping must not contain mapping entries."
        )

    return ResultColumnMappingView(
        specification_version=(
            _nonempty_string(
                document[
                    "specification_version"
                ],
                label=(
                    "Mapping specification version"
                ),
            )
        ),
        mode=mode,
        resolution_completed=(
            resolution_completed
        ),
        entries=tuple(
            entries
        ),
    )


def _configuration_view(
    value: object,
) -> ResultConfigurationView:
    document = _exact_object(
        value,
        keys={
            "profile_version",
            "mapping_mode",
            "source",
            "column_mapping_source",
        },
        label="Result configuration",
    )

    mapping_mode = _nonempty_string(
        document[
            "mapping_mode"
        ],
        label="Configuration mapping mode",
    )

    if mapping_mode not in {
        "strict",
        "automatic",
        "explicit",
    }:
        raise ValueError(
            "Configuration mapping mode is invalid."
        )

    raw_mapping_source = document[
        "column_mapping_source"
    ]

    mapping_source = (
        None
        if raw_mapping_source
        is None
        else _file_evidence_view(
            raw_mapping_source
        )
    )

    if (
        mapping_mode == "explicit"
        and mapping_source is None
    ):
        raise ValueError(
            "Explicit mapping requires mapping-source evidence."
        )

    if (
        mapping_mode != "explicit"
        and mapping_source is not None
    ):
        raise ValueError(
            "Only explicit mapping may have mapping-source evidence."
        )

    return ResultConfigurationView(
        profile_version=(
            _nonempty_string(
                document[
                    "profile_version"
                ],
                label=(
                    "Configuration profile version"
                ),
            )
        ),
        mapping_mode=mapping_mode,
        source=_file_evidence_view(
            document[
                "source"
            ]
        ),
        column_mapping_source=(
            mapping_source
        ),
    )


def _reconcile_count_dimension(
    stored: tuple[
        ResultCountView,
        ...,
    ],
    actual: dict[
        str,
        int,
    ],
    *,
    label: str,
) -> None:
    stored_map = {
        entry.label: entry.count
        for entry in stored
    }

    if not set(
        actual
    ).issubset(
        stored_map
    ):
        raise ValueError(
            label
            + " omit an observed finding label."
        )

    for name, count in stored_map.items():
        if count != actual.get(
            name,
            0,
        ):
            raise ValueError(
                label
                + " do not reconcile with findings."
            )


def _validation_view(
    value: object,
    *,
    configuration: ResultConfigurationView,
) -> ResultValidationView:
    document = _exact_object(
        value,
        keys={
            "application_version",
            "column_mapping",
            "configured_rules",
            "descriptor_schema_version",
            "findings",
            "input_name",
            "profile_id",
            "profile_version",
            "rows",
            "status",
            "summary",
        },
        label="Validation evidence",
    )

    _nonempty_string(
        document[
            "input_name"
        ],
        label="Validation input name",
    )

    status = _nonempty_string(
        document[
            "status"
        ],
        label="Validation status",
    )

    if status not in {
        "completed",
        "stopped_after_ingestion_finding",
    }:
        raise ValueError(
            "Validation status is invalid."
        )

    raw_rules = document[
        "configured_rules"
    ]

    if not isinstance(
        raw_rules,
        list,
    ):
        raise ValueError(
            "Configured rules must be an array."
        )

    configured_rules = tuple(
        _rule_view(
            raw
        )
        for raw in raw_rules
    )

    rule_keys = tuple(
        (
            rule.rule_id,
            rule.rule_version,
        )
        for rule in configured_rules
    )

    if len(
        set(
            rule_keys
        )
    ) != len(
        rule_keys
    ):
        raise ValueError(
            "Configured-rule identities must be unique."
        )

    raw_findings = document[
        "findings"
    ]

    if not isinstance(
        raw_findings,
        list,
    ):
        raise ValueError(
            "Findings must be an array."
        )

    findings = tuple(
        _finding_view(
            raw
        )
        for raw in raw_findings
    )

    rule_set = set(
        rule_keys
    )

    for finding in findings:
        if (
            finding.rule.rule_id,
            finding.rule.rule_version,
        ) not in rule_set:
            raise ValueError(
                "Finding references an unconfigured rule."
            )

    summary = _summary_view(
        document[
            "summary"
        ]
    )

    if summary.total_findings != len(
        findings
    ):
        raise ValueError(
            "Finding total does not reconcile with findings."
        )

    actual_category: dict[
        str,
        int,
    ] = {}

    actual_code: dict[
        str,
        int,
    ] = {}

    actual_severity: dict[
        str,
        int,
    ] = {}

    actual_scope: dict[
        str,
        int,
    ] = {}

    for finding in findings:
        for mapping, key in (
            (
                actual_category,
                finding.category,
            ),
            (
                actual_code,
                finding.code,
            ),
            (
                actual_severity,
                finding.severity,
            ),
            (
                actual_scope,
                finding.scope,
            ),
        ):
            mapping[
                key
            ] = (
                mapping.get(
                    key,
                    0,
                )
                + 1
            )

    _reconcile_count_dimension(
        summary.category_counts,
        actual_category,
        label="Category counts",
    )

    _reconcile_count_dimension(
        summary.code_counts,
        actual_code,
        label="Code counts",
    )

    _reconcile_count_dimension(
        summary.severity_counts,
        actual_severity,
        label="Severity counts",
    )

    _reconcile_count_dimension(
        summary.scope_counts,
        actual_scope,
        label="Scope counts",
    )

    profile_version = (
        _nonempty_string(
            document[
                "profile_version"
            ],
            label=(
                "Validation profile version"
            ),
        )
    )

    if (
        profile_version
        != configuration.profile_version
    ):
        raise ValueError(
            "Validation and configuration profile identities differ."
        )

    column_mapping = _mapping_view(
        document[
            "column_mapping"
        ]
    )

    if (
        column_mapping.mode
        != configuration.mapping_mode
    ):
        raise ValueError(
            "Validation and configuration mapping modes differ."
        )

    if (
        column_mapping.mode
        == "explicit"
        and not column_mapping.entries
    ):
        raise ValueError(
            "Explicit mapping requires mapping entries."
        )

    return ResultValidationView(
        application_version=(
            _nonempty_string(
                document[
                    "application_version"
                ],
                label=(
                    "Application version"
                ),
            )
        ),
        descriptor_schema_version=(
            _nonempty_string(
                document[
                    "descriptor_schema_version"
                ],
                label=(
                    "Descriptor schema version"
                ),
            )
        ),
        profile_id=(
            _nonempty_string(
                document[
                    "profile_id"
                ],
                label="Profile ID",
            )
        ),
        profile_version=(
            profile_version
        ),
        status=status,
        rows=_nonnegative_integer(
            document[
                "rows"
            ],
            label="Processed rows",
        ),
        configured_rules=(
            configured_rules
        ),
        column_mapping=(
            column_mapping
        ),
        summary=summary,
        findings=findings,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class ReviewResultView:
    """Application-safe durable result state for presentation."""

    run_id: str
    configuration_id: str
    status: str
    started_at: str | None
    finished_at: str | None
    artifact_sha256: str | None
    artifact_byte_count: int | None
    artifact_schema_id: str | None
    artifact_schema_version: str | None
    total_findings: int | None
    evidence_available: bool
    validation_status: str | None = None
    configuration: (
        ResultConfigurationView
        | None
    ) = None
    validation: (
        ResultValidationView
        | None
    ) = None



class ReviewSubmissionError(
    RuntimeError
):
    """Expected application-facing Review submission failure."""

    def __init__(
        self,
        code: str,
    ) -> None:
        super().__init__(
            "The structural review could not be completed."
        )

        self.code = code


class ReviewResultNotFound(
    LookupError
):
    """Raised when a requested durable run does not exist."""


class ReviewHistoryUnavailable(
    RuntimeError
):
    """Raised when durable History evidence cannot be trusted."""


@dataclass(frozen=True)
class ResultCountComparisonView:
    """One deterministic left/right summary-count comparison."""

    label: str
    left_count: int
    right_count: int
    delta: int


@dataclass(frozen=True)
class ReviewComparisonView:
    """Presentation-safe comparison of two reconciled review results."""

    left: ReviewResultView
    right: ReviewResultView
    same_source_bytes: bool
    same_profile_version: bool
    same_mapping_mode: bool
    same_mapping_source: bool
    same_application_version: bool
    same_descriptor_schema_version: bool
    same_profile_id: bool
    same_validation_profile_version: bool
    same_configured_rules: bool
    same_column_mapping: bool
    total_findings: ResultCountComparisonView
    category_counts: tuple[ResultCountComparisonView, ...]
    code_counts: tuple[ResultCountComparisonView, ...]
    severity_counts: tuple[ResultCountComparisonView, ...]
    scope_counts: tuple[ResultCountComparisonView, ...]
    common_findings: tuple[ResultFindingView, ...]
    left_only_findings: tuple[ResultFindingView, ...]
    right_only_findings: tuple[ResultFindingView, ...]


@dataclass(frozen=True)
class ReviewResultExportView:
    """Exact verified Result Bundle bytes with safe download metadata."""

    run_id: str
    filename: str
    media_type: str
    payload: bytes
    sha256: str
    byte_count: int


class ReviewComparisonInvalid(ValueError):
    """Raised when a comparison request is structurally invalid."""


class ReviewComparisonIneligible(RuntimeError):
    """Raised when a run is not an eligible completed comparison result."""


class ReviewComparisonUnavailable(RuntimeError):
    """Raised when trustworthy comparison evidence is unavailable."""


class ReviewExportIneligible(RuntimeError):
    """Raised when a run is not eligible for Result Bundle export."""


class ReviewExportUnavailable(RuntimeError):
    """Raised when trustworthy export evidence is unavailable."""


def _same_file_bytes(
    left: ResultFileEvidenceView | None,
    right: ResultFileEvidenceView | None,
) -> bool:
    if left is None or right is None:
        return left is right

    return (
        left.sha256 == right.sha256
        and left.byte_count == right.byte_count
    )


def _compare_count_views(
    left: tuple[ResultCountView, ...],
    right: tuple[ResultCountView, ...],
) -> tuple[ResultCountComparisonView, ...]:
    left_map = {
        item.label: item.count
        for item in left
    }

    right_map = {
        item.label: item.count
        for item in right
    }

    if (
        len(left_map) != len(left)
        or len(right_map) != len(right)
    ):
        raise ReviewComparisonUnavailable(
            "Summary count labels are not unique."
        )

    return tuple(
        ResultCountComparisonView(
            label=label,
            left_count=left_map.get(
                label,
                0,
            ),
            right_count=right_map.get(
                label,
                0,
            ),
            delta=(
                right_map.get(
                    label,
                    0,
                )
                - left_map.get(
                    label,
                    0,
                )
            ),
        )
        for label in sorted(
            set(left_map)
            | set(right_map)
        )
    )


def _take_findings(
    findings: tuple[ResultFindingView, ...],
    counts: Counter[ResultFindingView],
) -> tuple[ResultFindingView, ...]:
    remaining = counts.copy()
    selected: list[
        ResultFindingView
    ] = []

    for finding in findings:
        if remaining[
            finding
        ] <= 0:
            continue

        selected.append(
            finding
        )

        remaining[
            finding
        ] -= 1

    if any(
        remaining.values()
    ):
        raise ReviewComparisonUnavailable(
            "Finding multiplicity could not be reconstructed."
        )

    return tuple(
        selected
    )


def _exact_finding_multiset(
    left: tuple[ResultFindingView, ...],
    right: tuple[ResultFindingView, ...],
) -> tuple[
    tuple[ResultFindingView, ...],
    tuple[ResultFindingView, ...],
    tuple[ResultFindingView, ...],
]:
    left_counts = Counter(
        left
    )

    right_counts = Counter(
        right
    )

    common_counts = (
        left_counts
        & right_counts
    )

    left_only_counts = (
        left_counts
        - right_counts
    )

    right_only_counts = (
        right_counts
        - left_counts
    )

    return (
        _take_findings(
            left,
            common_counts,
        ),
        _take_findings(
            left,
            left_only_counts,
        ),
        _take_findings(
            right,
            right_only_counts,
        ),
    )


class ReviewWorkflowPort(
    Protocol
):
    """Presentation-facing Review workflow contract."""

    def recover_interrupted_runs(
        self,
    ) -> None:
        ...

    def submit(
        self,
        submission: ReviewSubmission,
    ) -> str:
        ...

    def history(
        self,
    ) -> tuple[
        ReviewHistoryEntryView,
        ...,
    ]:
        ...

    def result(
        self,
        run_id: str,
    ) -> ReviewResultView:
        ...

    def compare(
        self,
        left_run_id: str,
        right_run_id: str,
    ) -> ReviewComparisonView:
        ...

    def export_result(
        self,
        run_id: str,
    ) -> ReviewResultExportView:
        ...



class ReviewWorkflowService:
    """Coordinate browser submission using configured application services."""

    def __init__(
        self,
        *,
        lifecycle: RunLifecycleService,
        execution: ReviewExecutionService,
        publication: PublicationService,
        result_reader: ResultReader,
    ) -> None:
        self._lifecycle = lifecycle
        self._execution = execution
        self._publication = publication
        self._result_reader = result_reader

    def recover_interrupted_runs(
        self,
    ) -> None:
        self._lifecycle.ensure_workspace(
            _WORKSPACE_ID
        )

        self._lifecycle.recover_interrupted_runs()

    @staticmethod
    def _mapping_source(
        submission: ReviewSubmission,
    ) -> SourceFileEvidence | None:
        if submission.mapping_path is None:
            if any(
                value is not None
                for value in (
                    submission.mapping_display_name,
                    submission.mapping_sha256,
                    submission.mapping_byte_count,
                )
            ):
                raise ValueError(
                    "Mapping evidence requires a mapping path."
                )

            return None

        if (
            submission.mapping_display_name is None
            or submission.mapping_sha256 is None
            or submission.mapping_byte_count is None
        ):
            raise ValueError(
                "Mapping path requires complete mapping evidence."
            )

        return SourceFileEvidence(
            display_name=(
                submission.mapping_display_name
            ),
            sha256=submission.mapping_sha256,
            byte_count=(
                submission.mapping_byte_count
            ),
        )

    @staticmethod
    def _configuration_json(
        *,
        profile_version: str,
        mapping_mode: str,
        source: SourceFileEvidence,
        mapping_source: (
            SourceFileEvidence
            | None
        ),
    ) -> str:
        document: dict[
            str,
            object,
        ] = {
            "mapping_mode": mapping_mode,
            "profile_version": (
                profile_version
            ),
            "source": {
                "byte_count": (
                    source.byte_count
                ),
                "display_name": (
                    source.display_name
                ),
                "sha256": source.sha256,
            },
        }

        if mapping_source is not None:
            document[
                "column_mapping_source"
            ] = {
                "byte_count": (
                    mapping_source.byte_count
                ),
                "display_name": (
                    mapping_source.display_name
                ),
                "sha256": (
                    mapping_source.sha256
                ),
            }

        return json.dumps(
            document,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

    def submit(
        self,
        submission: ReviewSubmission,
    ) -> str:
        source = SourceFileEvidence(
            display_name=(
                submission.source_display_name
            ),
            sha256=submission.source_sha256,
            byte_count=(
                submission.source_byte_count
            ),
        )

        mapping_source = (
            self._mapping_source(
                submission
            )
        )

        result_configuration = (
            ResultBundleConfiguration(
                profile_version=(
                    submission.profile_version
                ),
                mapping_mode=(
                    submission.mapping_mode
                ),
                source=source,
                column_mapping_source=(
                    mapping_source
                ),
            )
        )

        configuration_id = uuid4().hex
        run_id = uuid4().hex
        artifact_id = uuid4().hex

        self._lifecycle.ensure_workspace(
            _WORKSPACE_ID
        )

        self._lifecycle.snapshot_configuration(
            configuration_id,
            _WORKSPACE_ID,
            self._configuration_json(
                profile_version=(
                    submission.profile_version
                ),
                mapping_mode=(
                    submission.mapping_mode
                ),
                source=source,
                mapping_source=(
                    mapping_source
                ),
            ),
        )

        self._lifecycle.queue_run(
            run_id,
            _WORKSPACE_ID,
            configuration_id,
        )

        command = QueuedReviewExecution(
            run_id=run_id,
            artifact_id=artifact_id,
            workspace_id=_WORKSPACE_ID,
            configuration_id=(
                configuration_id
            ),
            review_request=(
                StructuralReviewRequest(
                    input_path=(
                        submission.input_path
                    ),
                    profile_version=(
                        submission.profile_version
                    ),
                    auto_map=(
                        submission.mapping_mode
                        == "automatic"
                    ),
                    column_map=(
                        submission.mapping_path
                        if (
                            submission.mapping_mode
                            == "explicit"
                        )
                        else None
                    ),
                )
            ),
            result_configuration=(
                result_configuration
            ),
        )

        try:
            self._execution.execute(
                command
            )

        except StructuralReviewFailure as exc:
            raise ReviewSubmissionError(
                exc.code
            ) from exc

        except (
            ResultPublicationError,
            ResultPublicationRecoveryError,
        ):
            # Analysis state is durable and the result page
            # communicates publication unavailability separately.
            pass

        return run_id

    def history(
        self,
    ) -> tuple[
        ReviewHistoryEntryView,
        ...,
    ]:
        runs = self._lifecycle.list_runs(
            _WORKSPACE_ID,
            limit=50,
        )

        entries: list[
            ReviewHistoryEntryView
        ] = []

        for run in runs:
            try:
                if (
                    run.workspace_id
                    != _WORKSPACE_ID
                ):
                    raise ValueError(
                        "History run workspace is inconsistent."
                    )

                configuration = (
                    self._lifecycle
                    .get_configuration(
                        run.configuration_id
                    )
                )

                if (
                    configuration.configuration_id
                    != run.configuration_id
                ):
                    raise ValueError(
                        "History configuration identity is inconsistent."
                    )

                if (
                    configuration.workspace_id
                    != run.workspace_id
                ):
                    raise ValueError(
                        "History configuration workspace is inconsistent."
                    )

                actual_configuration_sha = (
                    hashlib.sha256(
                        configuration.canonical_json.encode(
                            "utf-8"
                        )
                    ).hexdigest()
                )

                if (
                    actual_configuration_sha
                    != configuration.sha256
                ):
                    raise ValueError(
                        "History configuration checksum is inconsistent."
                    )

                document = json.loads(
                    configuration.canonical_json
                )

                if not isinstance(
                    document,
                    dict,
                ):
                    raise ValueError(
                        "History configuration must be an object."
                    )

                required_keys = {
                    "mapping_mode",
                    "profile_version",
                    "source",
                }

                allowed_keys = (
                    required_keys
                    | {
                        "column_mapping_source",
                    }
                )

                if (
                    not required_keys.issubset(
                        document
                    )
                    or not set(
                        document
                    ).issubset(
                        allowed_keys
                    )
                ):
                    raise ValueError(
                        "History configuration shape is invalid."
                    )

                profile_version = (
                    document[
                        "profile_version"
                    ]
                )

                if (
                    not isinstance(
                        profile_version,
                        str,
                    )
                    or not profile_version
                    or len(
                        profile_version.split(
                            "."
                        )
                    ) != 3
                    or not all(
                        part.isdigit()
                        for part in profile_version.split(
                            "."
                        )
                    )
                ):
                    raise ValueError(
                        "History profile identity is invalid."
                    )

                mapping_mode = (
                    document[
                        "mapping_mode"
                    ]
                )

                if mapping_mode not in {
                    "strict",
                    "automatic",
                    "explicit",
                }:
                    raise ValueError(
                        "History mapping mode is invalid."
                    )

                def source_evidence(
                    value: object,
                ) -> SourceFileEvidence:
                    if not isinstance(
                        value,
                        dict,
                    ):
                        raise ValueError(
                            "History source evidence is invalid."
                        )

                    if set(
                        value
                    ) != {
                        "byte_count",
                        "display_name",
                        "sha256",
                    }:
                        raise ValueError(
                            "History source evidence shape is invalid."
                        )

                    display_name = value[
                        "display_name"
                    ]

                    digest = value[
                        "sha256"
                    ]

                    byte_count = value[
                        "byte_count"
                    ]

                    if (
                        not isinstance(
                            display_name,
                            str,
                        )
                        or not display_name
                        or "/"
                        in display_name
                        or "\\"
                        in display_name
                        or any(
                            ord(
                                character
                            ) < 32
                            or ord(
                                character
                            ) == 127
                            for character
                            in display_name
                        )
                    ):
                        raise ValueError(
                            "History source display name is invalid."
                        )

                    if (
                        not isinstance(
                            digest,
                            str,
                        )
                        or len(
                            digest
                        ) != 64
                    ):
                        raise ValueError(
                            "History source checksum is invalid."
                        )

                    try:
                        bytes.fromhex(
                            digest
                        )

                    except ValueError as error:
                        raise ValueError(
                            "History source checksum is invalid."
                        ) from error

                    if (
                        isinstance(
                            byte_count,
                            bool,
                        )
                        or not isinstance(
                            byte_count,
                            int,
                        )
                        or byte_count < 0
                    ):
                        raise ValueError(
                            "History source byte count is invalid."
                        )

                    return SourceFileEvidence(
                        display_name=display_name,
                        sha256=digest,
                        byte_count=byte_count,
                    )

                source = source_evidence(
                    document[
                        "source"
                    ]
                )

                has_mapping_source = (
                    "column_mapping_source"
                    in document
                )

                if (
                    mapping_mode
                    == "explicit"
                ):
                    if not has_mapping_source:
                        raise ValueError(
                            "Explicit History configuration lacks mapping evidence."
                        )

                    source_evidence(
                        document[
                            "column_mapping_source"
                        ]
                    )

                elif has_mapping_source:
                    raise ValueError(
                        "Non-explicit History configuration has unexpected mapping evidence."
                    )

                entries.append(
                    ReviewHistoryEntryView(
                        run_id=run.run_id,
                        configuration_id=(
                            run.configuration_id
                        ),
                        configuration_sha256=(
                            configuration.sha256
                        ),
                        status=run.status.value,
                        created_at=run.created_at,
                        started_at=run.started_at,
                        finished_at=run.finished_at,
                        source_display_name=(
                            source.display_name
                        ),
                        source_sha256=(
                            source.sha256
                        ),
                        source_byte_count=(
                            source.byte_count
                        ),
                        profile_version=(
                            profile_version
                        ),
                        mapping_mode=(
                            mapping_mode
                        ),
                    )
                )

            except (
                LedgerRecordNotFoundError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as error:
                raise ReviewHistoryUnavailable(
                    "History evidence is unavailable."
                ) from error

        return tuple(
            entries
        )

    def result(
        self,
        run_id: str,
    ) -> ReviewResultView:
        try:
            run = self._lifecycle.get_run(
                run_id
            )

        except LedgerRecordNotFoundError as exc:
            raise ReviewResultNotFound(
                run_id
            ) from exc

        artifacts = tuple(
            artifact
            for artifact in self._publication.list_artifacts(
                run_id
            )
            if (
                artifact.kind
                == RESULT_BUNDLE_ARTIFACT_KIND
            )
        )

        if len(
            artifacts
        ) > 1:
            raise RuntimeError(
                "More than one result bundle exists for the run."
            )

        artifact = (
            artifacts[
                0
            ]
            if artifacts
            else None
        )

        if (
            run.status
            is not RunState.SUCCEEDED
            and artifact
            is not None
        ):
            raise RuntimeError(
                "A non-successful run unexpectedly has a result bundle."
            )

        total_findings: (
            int
            | None
        ) = None

        validation_status: (
            str
            | None
        ) = None

        configuration_view: (
            ResultConfigurationView
            | None
        ) = None

        validation_view: (
            ResultValidationView
            | None
        ) = None

        evidence_available = False

        if artifact is not None:
            try:
                if (
                    artifact.schema_id
                    != RESULT_BUNDLE_SCHEMA_ID
                    or artifact.schema_version
                    != RESULT_BUNDLE_SCHEMA_VERSION
                ):
                    raise ValueError(
                        "Result artifact schema identity is invalid."
                    )

                payload = (
                    self._result_reader
                    .read_verified(
                        artifact.relative_path,
                        expected_sha256=(
                            artifact.sha256
                        ),
                        expected_byte_count=(
                            artifact.byte_count
                        ),
                    )
                )

                document = json.loads(
                    payload
                )

                document = _exact_object(
                    document,
                    keys={
                        "schema_id",
                        "schema_version",
                        "run",
                        "configuration",
                        "validation",
                    },
                    label="Result bundle",
                )

                if (
                    document[
                        "schema_id"
                    ]
                    != RESULT_BUNDLE_SCHEMA_ID
                    or document[
                        "schema_version"
                    ]
                    != RESULT_BUNDLE_SCHEMA_VERSION
                ):
                    raise ValueError(
                        "Result bundle schema identity is invalid."
                    )

                run_document = (
                    _exact_object(
                        document[
                            "run"
                        ],
                        keys={
                            "run_id",
                            "workspace_id",
                            "configuration_id",
                            "status",
                            "created_at",
                            "queued_at",
                            "started_at",
                            "finished_at",
                            "cancel_requested_at",
                        },
                        label=(
                            "Result bundle run"
                        ),
                    )
                )

                expected_run = {
                    "run_id": run.run_id,
                    "workspace_id": (
                        run.workspace_id
                    ),
                    "configuration_id": (
                        run.configuration_id
                    ),
                    "status": (
                        run.status.value
                    ),
                    "created_at": (
                        run.created_at
                    ),
                    "queued_at": (
                        run.queued_at
                    ),
                    "started_at": (
                        run.started_at
                    ),
                    "finished_at": (
                        run.finished_at
                    ),
                    "cancel_requested_at": (
                        run.cancel_requested_at
                    ),
                }

                if run_document != expected_run:
                    raise ValueError(
                        "Result bundle run identity does not match the durable run."
                    )

                configuration_record = (
                    self._lifecycle
                    .get_configuration(
                        run.configuration_id
                    )
                )

                if (
                    configuration_record.configuration_id
                    != run.configuration_id
                    or configuration_record.workspace_id
                    != run.workspace_id
                ):
                    raise ValueError(
                        "Durable run configuration identity does not match the run."
                    )

                configuration_digest = (
                    sha256(
                        configuration_record
                        .canonical_json
                        .encode(
                            "utf-8"
                        )
                    )
                    .hexdigest()
                )

                if (
                    configuration_digest
                    != configuration_record.sha256
                ):
                    raise ValueError(
                        "Durable run configuration SHA-256 is invalid."
                    )

                durable_configuration = (
                    json.loads(
                        configuration_record
                        .canonical_json
                    )
                )

                if not isinstance(
                    durable_configuration,
                    dict,
                ):
                    raise ValueError(
                        "Durable run configuration must be an object."
                    )

                bundle_configuration = (
                    _exact_object(
                        document[
                            "configuration"
                        ],
                        keys={
                            "profile_version",
                            "mapping_mode",
                            "source",
                            "column_mapping_source",
                        },
                        label=(
                            "Result bundle configuration"
                        ),
                    )
                )

                configuration_view = (
                    _configuration_view(
                        bundle_configuration
                    )
                )

                if (
                    configuration_view.mapping_mode
                    == "explicit"
                ):
                    if set(
                        durable_configuration
                    ) != {
                        "profile_version",
                        "mapping_mode",
                        "source",
                        "column_mapping_source",
                    }:
                        raise ValueError(
                            "Explicit durable configuration has an unexpected shape."
                        )

                    if (
                        durable_configuration
                        != bundle_configuration
                    ):
                        raise ValueError(
                            "Explicit configuration evidence does not reconcile."
                        )

                else:
                    if set(
                        durable_configuration
                    ) != {
                        "profile_version",
                        "mapping_mode",
                        "source",
                    }:
                        raise ValueError(
                            "Non-explicit durable configuration has an unexpected shape."
                        )

                    normalized_configuration = dict(
                        durable_configuration
                    )

                    normalized_configuration[
                        "column_mapping_source"
                    ] = None

                    if (
                        normalized_configuration
                        != bundle_configuration
                    ):
                        raise ValueError(
                            "Non-explicit configuration evidence does not reconcile."
                        )

                validation_view = (
                    _validation_view(
                        document[
                            "validation"
                        ],
                        configuration=(
                            configuration_view
                        ),
                    )
                )

                total_findings = (
                    validation_view
                    .summary
                    .total_findings
                )

                validation_status = (
                    validation_view.status
                )

                evidence_available = True

            except (
                ResultStoreError,
                LedgerRecordNotFoundError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
            ):
                total_findings = None
                validation_status = None
                configuration_view = None
                validation_view = None
                evidence_available = False

        return ReviewResultView(
            run_id=run.run_id,
            configuration_id=(
                run.configuration_id
            ),
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            artifact_sha256=(
                artifact.sha256
                if artifact is not None
                else None
            ),
            artifact_byte_count=(
                artifact.byte_count
                if artifact is not None
                else None
            ),
            artifact_schema_id=(
                artifact.schema_id
                if artifact is not None
                else None
            ),
            artifact_schema_version=(
                artifact.schema_version
                if artifact is not None
                else None
            ),
            total_findings=(
                total_findings
            ),
            validation_status=(
                validation_status
            ),
            evidence_available=(
                evidence_available
            ),
            configuration=(
                configuration_view
            ),
            validation=(
                validation_view
            ),
        )

    def compare(
        self,
        left_run_id: str,
        right_run_id: str,
    ) -> ReviewComparisonView:
        """Compare exact evidence from two reconciled completed reviews."""

        if left_run_id == right_run_id:
            raise ReviewComparisonInvalid(
                "Comparison requires two distinct run IDs."
            )

        try:
            left = self.result(
                left_run_id
            )

            right = self.result(
                right_run_id
            )

        except ReviewResultNotFound:
            raise

        except RuntimeError as exc:
            raise ReviewComparisonUnavailable(
                "Comparison evidence could not be reconciled."
            ) from exc

        if (
            left.status
            != RunState.SUCCEEDED.value
            or right.status
            != RunState.SUCCEEDED.value
        ):
            raise ReviewComparisonIneligible(
                "Comparison requires completed successful reviews."
            )

        if (
            not left.evidence_available
            or not right.evidence_available
            or left.configuration is None
            or right.configuration is None
            or left.validation is None
            or right.validation is None
        ):
            raise ReviewComparisonUnavailable(
                "Trustworthy comparison evidence is unavailable."
            )

        left_configuration = (
            left.configuration
        )

        right_configuration = (
            right.configuration
        )

        left_validation = (
            left.validation
        )

        right_validation = (
            right.validation
        )

        (
            common_findings,
            left_only_findings,
            right_only_findings,
        ) = _exact_finding_multiset(
            left_validation.findings,
            right_validation.findings,
        )

        left_total = (
            left_validation
            .summary
            .total_findings
        )

        right_total = (
            right_validation
            .summary
            .total_findings
        )

        return ReviewComparisonView(
            left=left,
            right=right,
            same_source_bytes=(
                _same_file_bytes(
                    left_configuration.source,
                    right_configuration.source,
                )
            ),
            same_profile_version=(
                left_configuration.profile_version
                == right_configuration.profile_version
            ),
            same_mapping_mode=(
                left_configuration.mapping_mode
                == right_configuration.mapping_mode
            ),
            same_mapping_source=(
                _same_file_bytes(
                    left_configuration.column_mapping_source,
                    right_configuration.column_mapping_source,
                )
            ),
            same_application_version=(
                left_validation.application_version
                == right_validation.application_version
            ),
            same_descriptor_schema_version=(
                left_validation.descriptor_schema_version
                == right_validation.descriptor_schema_version
            ),
            same_profile_id=(
                left_validation.profile_id
                == right_validation.profile_id
            ),
            same_validation_profile_version=(
                left_validation.profile_version
                == right_validation.profile_version
            ),
            same_configured_rules=(
                left_validation.configured_rules
                == right_validation.configured_rules
            ),
            same_column_mapping=(
                left_validation.column_mapping
                == right_validation.column_mapping
            ),
            total_findings=(
                ResultCountComparisonView(
                    label="total_findings",
                    left_count=left_total,
                    right_count=right_total,
                    delta=(
                        right_total
                        - left_total
                    ),
                )
            ),
            category_counts=(
                _compare_count_views(
                    left_validation
                    .summary
                    .category_counts,
                    right_validation
                    .summary
                    .category_counts,
                )
            ),
            code_counts=(
                _compare_count_views(
                    left_validation
                    .summary
                    .code_counts,
                    right_validation
                    .summary
                    .code_counts,
                )
            ),
            severity_counts=(
                _compare_count_views(
                    left_validation
                    .summary
                    .severity_counts,
                    right_validation
                    .summary
                    .severity_counts,
                )
            ),
            scope_counts=(
                _compare_count_views(
                    left_validation
                    .summary
                    .scope_counts,
                    right_validation
                    .summary
                    .scope_counts,
                )
            ),
            common_findings=(
                common_findings
            ),
            left_only_findings=(
                left_only_findings
            ),
            right_only_findings=(
                right_only_findings
            ),
        )

    def export_result(
        self,
        run_id: str,
    ) -> ReviewResultExportView:
        """Return exact verified Result Bundle bytes without republishing them."""

        try:
            result = self.result(
                run_id
            )

        except ReviewResultNotFound:
            raise

        except RuntimeError as exc:
            raise ReviewExportUnavailable(
                "Export evidence could not be reconciled."
            ) from exc

        if (
            result.status
            != RunState.SUCCEEDED.value
        ):
            raise ReviewExportIneligible(
                "Only completed successful reviews can be exported."
            )

        if (
            not result.evidence_available
            or result.configuration is None
            or result.validation is None
            or result.artifact_sha256 is None
            or result.artifact_byte_count is None
        ):
            raise ReviewExportUnavailable(
                "Trustworthy export evidence is unavailable."
            )

        try:
            artifacts = tuple(
                artifact
                for artifact
                in self._publication.list_artifacts(
                    result.run_id
                )
                if (
                    artifact.kind
                    == RESULT_BUNDLE_ARTIFACT_KIND
                )
            )

        except RuntimeError as exc:
            raise ReviewExportUnavailable(
                "Export artifact evidence is unavailable."
            ) from exc

        if len(
            artifacts
        ) != 1:
            raise ReviewExportUnavailable(
                "Exactly one Result Bundle is required for export."
            )

        artifact = artifacts[
            0
        ]

        if (
            artifact.export_attempt_id
            is not None
            or artifact.sha256
            != result.artifact_sha256
            or artifact.byte_count
            != result.artifact_byte_count
            or artifact.schema_id
            != result.artifact_schema_id
            or artifact.schema_version
            != result.artifact_schema_version
        ):
            raise ReviewExportUnavailable(
                "Export artifact identity does not match the reconciled result."
            )

        try:
            payload = (
                self._result_reader
                .read_verified(
                    artifact.relative_path,
                    expected_sha256=(
                        artifact.sha256
                    ),
                    expected_byte_count=(
                        artifact.byte_count
                    ),
                )
            )

        except (
            ResultStoreError,
            OSError,
            ValueError,
        ) as exc:
            raise ReviewExportUnavailable(
                "Export artifact bytes could not be verified."
            ) from exc

        if (
            len(
                payload
            )
            != artifact.byte_count
            or hashlib.sha256(
                payload
            ).hexdigest()
            != artifact.sha256
        ):
            raise ReviewExportUnavailable(
                "Export artifact byte identity is inconsistent."
            )

        return ReviewResultExportView(
            run_id=result.run_id,
            filename=(
                "result-bundle-"
                + result.run_id
                + ".json"
            ),
            media_type=(
                "application/json"
            ),
            payload=payload,
            sha256=artifact.sha256,
            byte_count=(
                artifact.byte_count
            ),
        )
