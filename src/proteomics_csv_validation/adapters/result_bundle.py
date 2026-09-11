"""Adapter from validation models to result-bundle JSON v1."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
import json
import re

from proteomics_csv_validation.application.structural_review import (
    StructuralReviewEvidence,
)
from proteomics_csv_validation.domain.result_artifact import (
    RESULT_BUNDLE_JSON_SCHEMA_DIALECT,
    RESULT_BUNDLE_SCHEMA_ID,
    RESULT_BUNDLE_SCHEMA_VERSION,
    ResultBundleConfiguration,
    ResultBundleSerializationError,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    AnalysisRunRecord,
    RunState,
)
_RUN_ID_PATTERN = re.compile(
    r"^[0-9a-f]{32}$"
)


from proteomics_csv_validation.models import (
    CategoryCount,
    CodeCount,
    ColumnMappingEntry,
    ColumnMappingEvidence,
    EntityReference,
    Finding,
    FindingSummary,
    FindingValue,
    RuleReference,
    ScopeCount,
    SeverityCount,
    SourceLocation,
    ValidationResult,
)


def result_bundle_schema() -> dict[
    str,
    Any,
]:
    """Return the version 1 JSON Schema contract."""

    return {
        "$schema": (
            RESULT_BUNDLE_JSON_SCHEMA_DIALECT
        ),
        "$id": (
            "urn:proteomics-csv-validation:"
            "result-bundle:1.0.0"
        ),
        "title": (
            "Proteomics CSV Validation "
            "Result Bundle 1.0.0"
        ),
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_id",
            "schema_version",
            "run",
            "configuration",
            "validation",
        ],
        "properties": {
            "schema_id": {
                "const": (
                    RESULT_BUNDLE_SCHEMA_ID
                ),
            },
            "schema_version": {
                "const": (
                    RESULT_BUNDLE_SCHEMA_VERSION
                ),
            },
            "run": {
                "$ref": "#/$defs/run",
            },
            "configuration": {
                "$ref": "#/$defs/configuration",
            },
            "validation": {
                "$ref": "#/$defs/validation",
            },
        },
        "$defs": {
            "nullableString": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "fileEvidence": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "display_name",
                    "sha256",
                    "byte_count",
                ],
                "properties": {
                    "display_name": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": "^[^/\\\\\u0000]+$",
                        "not": {
                            "enum": [
                                ".",
                                "..",
                            ],
                        },
                    },
                    "sha256": {
                        "type": "string",
                        "pattern": (
                            "^[0-9a-f]{64}$"
                        ),
                    },
                    "byte_count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
            },
            "taggedValue": {
                "oneOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "value",
                        ],
                        "properties": {
                            "type": {
                                "const": "null",
                            },
                            "value": {
                                "type": "null",
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "value",
                        ],
                        "properties": {
                            "type": {
                                "const": "boolean",
                            },
                            "value": {
                                "type": "boolean",
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "value",
                        ],
                        "properties": {
                            "type": {
                                "const": "integer",
                            },
                            "value": {
                                "type": "integer",
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "value",
                        ],
                        "properties": {
                            "type": {
                                "const": "decimal",
                            },
                            "value": {
                                "type": "string",
                                "minLength": 1,
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "value",
                        ],
                        "properties": {
                            "type": {
                                "const": "string",
                            },
                            "value": {
                                "type": "string",
                            },
                        },
                    },
                ],
            },
            "rule": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "rule_id",
                    "rule_version",
                ],
                "properties": {
                    "rule_id": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "rule_version": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
            },
            "location": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "row_number",
                    "field_name",
                ],
                "properties": {
                    "row_number": {
                        "type": [
                            "integer",
                            "null",
                        ],
                        "minimum": 1,
                    },
                    "field_name": {
                        "$ref": (
                            "#/$defs/nullableString"
                        ),
                    },
                },
            },
            "keyPart": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "field_name",
                    "value",
                ],
                "properties": {
                    "field_name": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "value": {
                        "$ref": (
                            "#/$defs/taggedValue"
                        ),
                    },
                },
            },
            "entity": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "entity_type",
                    "key_parts",
                ],
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "key_parts": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "$ref": (
                                "#/$defs/keyPart"
                            ),
                        },
                    },
                },
            },
            "finding": {
                "type": "object",
                "additionalProperties": False,
                "required": [
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
                ],
                "properties": {
                    "code": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "category": {
                        "enum": [
                            "ingestion",
                            "schema",
                            "identifier",
                            "missingness",
                        ],
                    },
                    "severity": {
                        "enum": [
                            "error",
                            "warning",
                            "information",
                        ],
                    },
                    "scope": {
                        "enum": [
                            "file",
                            "row",
                        ],
                    },
                    "rule": {
                        "$ref": "#/$defs/rule",
                    },
                    "location": {
                        "oneOf": [
                            {
                                "type": "null",
                            },
                            {
                                "$ref": (
                                    "#/$defs/location"
                                ),
                            },
                        ],
                    },
                    "entity": {
                        "oneOf": [
                            {
                                "type": "null",
                            },
                            {
                                "$ref": (
                                    "#/$defs/entity"
                                ),
                            },
                        ],
                    },
                    "observed_value": {
                        "$ref": (
                            "#/$defs/taggedValue"
                        ),
                    },
                    "expected_value": {
                        "$ref": (
                            "#/$defs/taggedValue"
                        ),
                    },
                    "message": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
            },
            "categoryCount": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "category",
                    "count",
                ],
                "properties": {
                    "category": {
                        "enum": [
                            "ingestion",
                            "schema",
                            "identifier",
                            "missingness",
                        ],
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
            },
            "codeCount": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "code",
                    "count",
                ],
                "properties": {
                    "code": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
            },
            "severityCount": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "severity",
                    "count",
                ],
                "properties": {
                    "severity": {
                        "enum": [
                            "error",
                            "warning",
                            "information",
                        ],
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
            },
            "scopeCount": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "scope",
                    "count",
                ],
                "properties": {
                    "scope": {
                        "enum": [
                            "file",
                            "row",
                        ],
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
            },
            "summary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "total_findings",
                    "category_counts",
                    "code_counts",
                    "severity_counts",
                    "scope_counts",
                ],
                "properties": {
                    "total_findings": {
                        "type": "integer",
                        "minimum": 0,
                    },
                    "category_counts": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/categoryCount"
                            ),
                        },
                    },
                    "code_counts": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/codeCount"
                            ),
                        },
                    },
                    "severity_counts": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/severityCount"
                            ),
                        },
                    },
                    "scope_counts": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/scopeCount"
                            ),
                        },
                    },
                },
            },
            "mappingEntry": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_field",
                    "target_field",
                ],
                "properties": {
                    "source_field": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "target_field": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
            },
            "columnMapping": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "specification_version",
                    "mode",
                    "resolution_completed",
                    "entries",
                ],
                "properties": {
                    "specification_version": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "mode": {
                        "enum": [
                            "strict",
                            "automatic",
                            "explicit",
                        ],
                    },
                    "resolution_completed": {
                        "type": "boolean",
                    },
                    "entries": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/mappingEntry"
                            ),
                        },
                    },
                },
            },
            "validation": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "application_version",
                    "descriptor_schema_version",
                    "profile_id",
                    "profile_version",
                    "input_name",
                    "status",
                    "rows",
                    "configured_rules",
                    "findings",
                    "summary",
                    "column_mapping",
                ],
                "properties": {
                    "application_version": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "descriptor_schema_version": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "profile_id": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "profile_version": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "input_name": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "status": {
                        "enum": [
                            "completed",
                            (
                                "stopped_after_"
                                "ingestion_finding"
                            ),
                        ],
                    },
                    "rows": {
                        "type": "integer",
                        "minimum": 0,
                    },
                    "configured_rules": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/rule"
                            ),
                        },
                    },
                    "findings": {
                        "type": "array",
                        "items": {
                            "$ref": (
                                "#/$defs/finding"
                            ),
                        },
                    },
                    "summary": {
                        "$ref": "#/$defs/summary",
                    },
                    "column_mapping": {
                        "$ref": (
                            "#/$defs/columnMapping"
                        ),
                    },
                },
            },
            "run": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "run_id",
                    "workspace_id",
                    "configuration_id",
                    "status",
                    "created_at",
                    "queued_at",
                    "started_at",
                    "finished_at",
                    "cancel_requested_at",
                ],
                "properties": {
                    "run_id": {
                        "type": "string",
                        "pattern": (
                            "^[0-9a-f]{32}$"
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "configuration_id": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "status": {
                        "const": "SUCCEEDED",
                    },
                    "created_at": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "queued_at": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "started_at": {
                        "$ref": (
                            "#/$defs/nullableString"
                        ),
                    },
                    "finished_at": {
                        "$ref": (
                            "#/$defs/nullableString"
                        ),
                    },
                    "cancel_requested_at": {
                        "$ref": (
                            "#/$defs/nullableString"
                        ),
                    },
                },
            },
            "configuration": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "profile_version",
                    "mapping_mode",
                    "source",
                    "column_mapping_source",
                ],
                "properties": {
                    "profile_version": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "mapping_mode": {
                        "enum": [
                            "strict",
                            "automatic",
                            "explicit",
                        ],
                    },
                    "source": {
                        "$ref": (
                            "#/$defs/fileEvidence"
                        ),
                    },
                    "column_mapping_source": {
                        "oneOf": [
                            {
                                "type": "null",
                            },
                            {
                                "$ref": (
                                    "#/$defs/fileEvidence"
                                ),
                            },
                        ],
                    },
                },
                "allOf": [
                    {
                        "if": {
                            "properties": {
                                "mapping_mode": {
                                    "const": "explicit",
                                },
                            },
                            "required": [
                                "mapping_mode",
                            ],
                        },
                        "then": {
                            "properties": {
                                "column_mapping_source": {
                                    "$ref": (
                                        "#/$defs/fileEvidence"
                                    ),
                                },
                            },
                        },
                        "else": {
                            "properties": {
                                "column_mapping_source": {
                                    "type": "null",
                                },
                            },
                        },
                    },
                ],
            },
        },
    }


def _file_evidence_document(
    evidence: Any,
) -> dict[str, Any]:
    return {
        "display_name": (
            evidence.display_name
        ),
        "sha256": evidence.sha256,
        "byte_count": (
            evidence.byte_count
        ),
    }


def _tagged_value(
    value: FindingValue,
) -> dict[str, Any]:
    if value is None:
        return {
            "type": "null",
            "value": None,
        }

    if isinstance(
        value,
        bool,
    ):
        return {
            "type": "boolean",
            "value": value,
        }

    if isinstance(
        value,
        int,
    ):
        return {
            "type": "integer",
            "value": value,
        }

    if isinstance(
        value,
        Decimal,
    ):
        if not value.is_finite():
            raise ResultBundleSerializationError(
                "Result evidence contains a non-finite decimal."
            )

        return {
            "type": "decimal",
            "value": str(
                value
            ),
        }

    if isinstance(
        value,
        str,
    ):
        return {
            "type": "string",
            "value": value,
        }

    raise ResultBundleSerializationError(
        "Result evidence contains an unsupported finding value."
    )


def _rule_document(
    rule: RuleReference,
) -> dict[str, str]:
    return {
        "rule_id": rule.rule_id,
        "rule_version": (
            rule.rule_version
        ),
    }


def _location_document(
    location: SourceLocation
    | None,
) -> dict[str, Any] | None:
    if location is None:
        return None

    return {
        "row_number": (
            location.row_number
        ),
        "field_name": (
            location.field_name
        ),
    }


def _entity_document(
    entity: EntityReference
    | None,
) -> dict[str, Any] | None:
    if entity is None:
        return None

    return {
        "entity_type": (
            entity.entity_type
        ),
        "key_parts": [
            {
                "field_name": (
                    part.field_name
                ),
                "value": _tagged_value(
                    part.value
                ),
            }
            for part in entity.key_parts
        ],
    }


def _finding_document(
    finding: Finding,
) -> dict[str, Any]:
    return {
        "code": finding.code,
        "category": (
            finding.category.value
        ),
        "severity": (
            finding.severity.value
        ),
        "scope": (
            finding.scope.value
        ),
        "rule": _rule_document(
            finding.rule
        ),
        "location": (
            _location_document(
                finding.location
            )
        ),
        "entity": (
            _entity_document(
                finding.entity
            )
        ),
        "observed_value": (
            _tagged_value(
                finding.observed_value
            )
        ),
        "expected_value": (
            _tagged_value(
                finding.expected_value
            )
        ),
        "message": finding.message,
    }


def _category_count_document(
    item: CategoryCount,
) -> dict[str, Any]:
    return {
        "category": (
            item.category.value
        ),
        "count": item.count,
    }


def _code_count_document(
    item: CodeCount,
) -> dict[str, Any]:
    return {
        "code": item.code,
        "count": item.count,
    }


def _severity_count_document(
    item: SeverityCount,
) -> dict[str, Any]:
    return {
        "severity": (
            item.severity.value
        ),
        "count": item.count,
    }


def _scope_count_document(
    item: ScopeCount,
) -> dict[str, Any]:
    return {
        "scope": (
            item.scope.value
        ),
        "count": item.count,
    }


def _summary_document(
    summary: FindingSummary,
) -> dict[str, Any]:
    return {
        "total_findings": (
            summary.total_findings
        ),
        "category_counts": [
            _category_count_document(
                item
            )
            for item
            in summary.category_counts
        ],
        "code_counts": [
            _code_count_document(
                item
            )
            for item
            in summary.code_counts
        ],
        "severity_counts": [
            _severity_count_document(
                item
            )
            for item
            in summary.severity_counts
        ],
        "scope_counts": [
            _scope_count_document(
                item
            )
            for item
            in summary.scope_counts
        ],
    }


def _mapping_entry_document(
    entry: ColumnMappingEntry,
) -> dict[str, str]:
    return {
        "source_field": (
            entry.source_field
        ),
        "target_field": (
            entry.target_field
        ),
    }


def _mapping_document(
    mapping: ColumnMappingEvidence,
) -> dict[str, Any]:
    return {
        "specification_version": (
            mapping.specification_version
        ),
        "mode": mapping.mode.value,
        "resolution_completed": (
            mapping.resolution_completed
        ),
        "entries": [
            _mapping_entry_document(
                entry
            )
            for entry in mapping.entries
        ],
    }


def _validation_document(
    result: ValidationResult,
) -> dict[str, Any]:
    return {
        "application_version": (
            result.application_version
        ),
        "descriptor_schema_version": (
            result.descriptor_schema_version
        ),
        "profile_id": (
            result.profile_id
        ),
        "profile_version": (
            result.profile_version
        ),
        "input_name": (
            result.input_name
        ),
        "status": (
            result.status.value
        ),
        "rows": result.rows,
        "configured_rules": [
            _rule_document(
                rule
            )
            for rule
            in result.configured_rules
        ],
        "findings": [
            _finding_document(
                finding
            )
            for finding
            in result.findings
        ],
        "summary": (
            _summary_document(
                result.summary
            )
        ),
        "column_mapping": (
            _mapping_document(
                result.column_mapping
            )
        ),
    }


def _run_document(
    run: AnalysisRunRecord,
) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "workspace_id": (
            run.workspace_id
        ),
        "configuration_id": (
            run.configuration_id
        ),
        "status": run.status.value,
        "created_at": run.created_at,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "cancel_requested_at": (
            run.cancel_requested_at
        ),
    }


class ValidationResultBundleSerializer:
    """Serialize one completed validation result."""

    def serialize(
        self,
        *,
        run: AnalysisRunRecord,
        configuration: ResultBundleConfiguration,
        validation: StructuralReviewEvidence,
    ) -> bytes:
        if not isinstance(
            run,
            AnalysisRunRecord,
        ):
            raise TypeError(
                "run must be an AnalysisRunRecord."
            )

        if not isinstance(
            configuration,
            ResultBundleConfiguration,
        ):
            raise TypeError(
                "configuration must be a ResultBundleConfiguration."
            )

        if not isinstance(
            validation,
            ValidationResult,
        ):
            raise ResultBundleSerializationError(
                "The configured result serializer received unsupported review evidence."
            )

        if (
            _RUN_ID_PATTERN.fullmatch(
                run.run_id
            )
            is None
        ):
            raise ResultBundleSerializationError(
                "A result bundle requires a 32-character lowercase hexadecimal run ID."
            )

        if (
            run.status
            is not RunState.SUCCEEDED
        ):
            raise ResultBundleSerializationError(
                "A result bundle requires a SUCCEEDED run."
            )

        if (
            configuration.profile_version
            != validation.profile_version
        ):
            raise ResultBundleSerializationError(
                "Configured and validated profile versions differ."
            )

        if (
            configuration.mapping_mode
            != validation.column_mapping.mode.value
        ):
            raise ResultBundleSerializationError(
                "Configured and validated mapping modes differ."
            )

        document = {
            "schema_id": (
                RESULT_BUNDLE_SCHEMA_ID
            ),
            "schema_version": (
                RESULT_BUNDLE_SCHEMA_VERSION
            ),
            "run": _run_document(
                run
            ),
            "configuration": {
                "profile_version": (
                    configuration.profile_version
                ),
                "mapping_mode": (
                    configuration.mapping_mode
                ),
                "source": (
                    _file_evidence_document(
                        configuration.source
                    )
                ),
                "column_mapping_source": (
                    None
                    if (
                        configuration
                        .column_mapping_source
                        is None
                    )
                    else (
                        _file_evidence_document(
                            configuration
                            .column_mapping_source
                        )
                    )
                ),
            },
            "validation": (
                _validation_document(
                    validation
                )
            ),
        }

        try:
            text = json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(
                    ",",
                    ":",
                ),
                allow_nan=False,
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ResultBundleSerializationError(
                "Result evidence could not be serialized deterministically."
            ) from exc

        return (
            text.encode(
                "utf-8"
            )
            + b"\n"
        )
