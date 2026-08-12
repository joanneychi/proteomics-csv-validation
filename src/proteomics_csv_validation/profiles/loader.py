"""Strict loading for registry-controlled built-in profiles."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from importlib import resources
import json
from typing import Any

from proteomics_csv_validation.errors import (
    ProfileDefinitionError,
    ProfileNotFoundError,
)
from proteomics_csv_validation.profiles.models import (
    CsvDialectDefinition,
    FieldDefinition,
    LogicalType,
    MetricDefinition,
    MissingValuePolicy,
    ProfileDefinition,
)


_DESCRIPTOR_SCHEMA_VERSION = "1.0.0"
_DEFAULT_PROFILE_ID = (
    "proteomics_processed_sample_summary"
)
_DEFAULT_PROFILE_VERSION = "0.2.0"

_PROFILE_REGISTRY = {
    (
        _DEFAULT_PROFILE_ID,
        "0.1.0",
    ): (
        "proteomics_processed_sample_summary-0.1.0.json"
    ),
    (
        _DEFAULT_PROFILE_ID,
        _DEFAULT_PROFILE_VERSION,
    ): (
        "proteomics_processed_sample_summary-0.2.0.json"
    ),
}


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


def _require_mapping(
    value: object,
    *,
    context: str,
) -> dict[str, Any]:
    if not isinstance(
        value,
        dict,
    ):
        raise ProfileDefinitionError(
            f"{context} must be a JSON object."
        )

    return value


def _require_list(
    value: object,
    *,
    context: str,
) -> list[Any]:
    if not isinstance(
        value,
        list,
    ):
        raise ProfileDefinitionError(
            f"{context} must be a JSON array."
        )

    return value


def _require_string(
    value: object,
    *,
    context: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or value == ""
    ):
        raise ProfileDefinitionError(
            f"{context} must be a nonempty string."
        )

    return value


def _require_bool(
    value: object,
    *,
    context: str,
) -> bool:
    if not isinstance(
        value,
        bool,
    ):
        raise ProfileDefinitionError(
            f"{context} must be boolean."
        )

    return value


def _string_tuple(
    value: object,
    *,
    context: str,
) -> tuple[str, ...]:
    items = _require_list(
        value,
        context=context,
    )

    return tuple(
        _require_string(
            item,
            context=f"{context} item",
        )
        for item
        in items
    )


def _parse_decimal_or_int(
    value: object,
    *,
    context: str,
) -> int | Decimal:
    if isinstance(
        value,
        bool,
    ):
        raise ProfileDefinitionError(
            f"{context} must be numeric."
        )

    if isinstance(
        value,
        int,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        try:
            return Decimal(
                value
            )
        except InvalidOperation as exc:
            raise ProfileDefinitionError(
                f"{context} must be an integer "
                "or decimal string."
            ) from exc

    raise ProfileDefinitionError(
        f"{context} must be an integer "
        "or decimal string."
    )


def _build_profile(
    document: dict[
        str,
        Any,
    ],
) -> ProfileDefinition:
    descriptor_version = _require_string(
        document.get(
            "descriptor_schema_version"
        ),
        context="descriptor_schema_version",
    )

    if descriptor_version != (
        _DESCRIPTOR_SCHEMA_VERSION
    ):
        raise ProfileDefinitionError(
            "Unsupported descriptor schema version: "
            f"{descriptor_version!r}."
        )

    field_documents = _require_list(
        document.get(
            "fields"
        ),
        context="fields",
    )

    fields: list[
        FieldDefinition
    ] = []

    for index, item in enumerate(
        field_documents
    ):
        field_document = _require_mapping(
            item,
            context=f"fields[{index}]",
        )

        policy_document = _require_mapping(
            field_document.get(
                "missing_value_policy"
            ),
            context=(
                f"fields[{index}]."
                "missing_value_policy"
            ),
        )

        logical_type_text = _require_string(
            field_document.get(
                "logical_type"
            ),
            context=(
                f"fields[{index}].logical_type"
            ),
        )

        try:
            logical_type = LogicalType(
                logical_type_text
            )
        except ValueError as exc:
            raise ProfileDefinitionError(
                "Unsupported logical type: "
                f"{logical_type_text!r}."
            ) from exc

        fields.append(
            FieldDefinition(
                name=_require_string(
                    field_document.get(
                        "name"
                    ),
                    context=(
                        f"fields[{index}].name"
                    ),
                ),
                title=_require_string(
                    field_document.get(
                        "title"
                    ),
                    context=(
                        f"fields[{index}].title"
                    ),
                ),
                description=_require_string(
                    field_document.get(
                        "description"
                    ),
                    context=(
                        f"fields[{index}].description"
                    ),
                ),
                logical_type=logical_type,
                required=_require_bool(
                    field_document.get(
                        "required"
                    ),
                    context=(
                        f"fields[{index}].required"
                    ),
                ),
                missing_value_policy=(
                    MissingValuePolicy(
                        blank_is_missing=_require_bool(
                            policy_document.get(
                                "blank_is_missing"
                            ),
                            context=(
                                f"fields[{index}]."
                                "missing_value_policy."
                                "blank_is_missing"
                            ),
                        ),
                        whitespace_only_is_missing=(
                            _require_bool(
                                policy_document.get(
                                    "whitespace_only_is_missing"
                                ),
                                context=(
                                    f"fields[{index}]."
                                    "missing_value_policy."
                                    "whitespace_only_is_missing"
                                ),
                            )
                        ),
                        missing_tokens=_string_tuple(
                            policy_document.get(
                                "missing_tokens",
                                [],
                            ),
                            context=(
                                f"fields[{index}]."
                                "missing_value_policy."
                                "missing_tokens"
                            ),
                        ),
                        tokens_case_sensitive=(
                            _require_bool(
                                policy_document.get(
                                    "tokens_case_sensitive",
                                    True,
                                ),
                                context=(
                                    f"fields[{index}]."
                                    "missing_value_policy."
                                    "tokens_case_sensitive"
                                ),
                            )
                        ),
                    )
                ),
            )
        )

    metric_documents = _require_list(
        document.get(
            "metrics"
        ),
        context="metrics",
    )

    metrics: list[
        MetricDefinition
    ] = []

    for index, item in enumerate(
        metric_documents
    ):
        metric_document = _require_mapping(
            item,
            context=f"metrics[{index}]",
        )

        aggregation_value = (
            metric_document.get(
                "aggregation"
            )
        )

        if aggregation_value is not None:
            aggregation = _require_string(
                aggregation_value,
                context=(
                    f"metrics[{index}].aggregation"
                ),
            )
        else:
            aggregation = None

        metrics.append(
            MetricDefinition(
                field_name=_require_string(
                    metric_document.get(
                        "field_name"
                    ),
                    context=(
                        f"metrics[{index}].field_name"
                    ),
                ),
                metric_id=_require_string(
                    metric_document.get(
                        "metric_id"
                    ),
                    context=(
                        f"metrics[{index}].metric_id"
                    ),
                ),
                unit=_require_string(
                    metric_document.get(
                        "unit"
                    ),
                    context=(
                        f"metrics[{index}].unit"
                    ),
                ),
                scale=_require_string(
                    metric_document.get(
                        "scale"
                    ),
                    context=(
                        f"metrics[{index}].scale"
                    ),
                ),
                minimum=_parse_decimal_or_int(
                    metric_document.get(
                        "minimum"
                    ),
                    context=(
                        f"metrics[{index}].minimum"
                    ),
                ),
                value_origin=_require_string(
                    metric_document.get(
                        "value_origin"
                    ),
                    context=(
                        f"metrics[{index}].value_origin"
                    ),
                ),
                normalization_state=_require_string(
                    metric_document.get(
                        "normalization_state"
                    ),
                    context=(
                        f"metrics[{index}].normalization_state"
                    ),
                ),
                aggregation=aggregation,
            )
        )

    dialect_document = _require_mapping(
        document.get(
            "csv_dialect"
        ),
        context="csv_dialect",
    )

    try:
        return ProfileDefinition(
            descriptor_schema_version=(
                descriptor_version
            ),
            profile_id=_require_string(
                document.get(
                    "profile_id"
                ),
                context="profile_id",
            ),
            profile_version=_require_string(
                document.get(
                    "profile_version"
                ),
                context="profile_version",
            ),
            entity_type=_require_string(
                document.get(
                    "entity_type"
                ),
                context="entity_type",
            ),
            title=_require_string(
                document.get(
                    "title"
                ),
                context="title",
            ),
            description=_require_string(
                document.get(
                    "description"
                ),
                context="description",
            ),
            record_grain=_require_string(
                document.get(
                    "record_grain"
                ),
                context="record_grain",
            ),
            file_grain=_require_string(
                document.get(
                    "file_grain"
                ),
                context="file_grain",
            ),
            fields=tuple(
                fields
            ),
            key_fields=_string_tuple(
                document.get(
                    "key_fields"
                ),
                context="key_fields",
            ),
            factor_fields=_string_tuple(
                document.get(
                    "factor_fields"
                ),
                context="factor_fields",
            ),
            batch_fields=_string_tuple(
                document.get(
                    "batch_fields"
                ),
                context="batch_fields",
            ),
            metrics=tuple(
                metrics
            ),
            csv_dialect=(
                CsvDialectDefinition(
                    encoding=_require_string(
                        dialect_document.get(
                            "encoding"
                        ),
                        context=(
                            "csv_dialect.encoding"
                        ),
                    ),
                    delimiter=_require_string(
                        dialect_document.get(
                            "delimiter"
                        ),
                        context=(
                            "csv_dialect.delimiter"
                        ),
                    ),
                    quote_character=_require_string(
                        dialect_document.get(
                            "quote_character"
                        ),
                        context=(
                            "csv_dialect."
                            "quote_character"
                        ),
                    ),
                    header_required=_require_bool(
                        dialect_document.get(
                            "header_required"
                        ),
                        context=(
                            "csv_dialect."
                            "header_required"
                        ),
                    ),
                    allow_utf8_bom=_require_bool(
                        dialect_document.get(
                            "allow_utf8_bom"
                        ),
                        context=(
                            "csv_dialect."
                            "allow_utf8_bom"
                        ),
                    ),
                    allow_blank_records=_require_bool(
                        dialect_document.get(
                            "allow_blank_records"
                        ),
                        context=(
                            "csv_dialect."
                            "allow_blank_records"
                        ),
                    ),
                    allow_embedded_newlines=_require_bool(
                        dialect_document.get(
                            "allow_embedded_newlines"
                        ),
                        context=(
                            "csv_dialect."
                            "allow_embedded_newlines"
                        ),
                    ),
                    decimal_separator=_require_string(
                        dialect_document.get(
                            "decimal_separator"
                        ),
                        context=(
                            "csv_dialect."
                            "decimal_separator"
                        ),
                    ),
                )
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ProfileDefinitionError(
            "Profile cross-reference validation failed: "
            f"{exc}"
        ) from exc


def load_profile(
    profile_id: str,
    profile_version: str,
) -> ProfileDefinition:
    """Load one registry-controlled built-in profile."""

    if not isinstance(
        profile_id,
        str,
    ):
        raise TypeError(
            "profile_id must be a string."
        )

    if not isinstance(
        profile_version,
        str,
    ):
        raise TypeError(
            "profile_version must be a string."
        )

    filename = _PROFILE_REGISTRY.get(
        (
            profile_id,
            profile_version,
        )
    )

    if filename is None:
        raise ProfileNotFoundError(
            "No registered profile matches "
            f"{profile_id!r} version "
            f"{profile_version!r}."
        )

    resource = (
        resources.files(
            "proteomics_csv_validation.profiles"
        )
        .joinpath(
            "data"
        )
        .joinpath(
            filename
        )
    )

    try:
        text = resource.read_text(
            encoding="utf-8"
        )
    except (
        FileNotFoundError,
        OSError,
    ) as exc:
        raise ProfileNotFoundError(
            "Registered profile resource could "
            f"not be read: {filename!r}."
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
        UnicodeError,
        ValueError,
    ) as exc:
        raise ProfileDefinitionError(
            "Profile resource is not valid strict JSON: "
            f"{filename!r}."
        ) from exc

    document = _require_mapping(
        loaded,
        context="profile document",
    )

    profile = _build_profile(
        document
    )

    if (
        profile.profile_id
        != profile_id
        or profile.profile_version
        != profile_version
    ):
        raise ProfileDefinitionError(
            "Profile resource identity does not "
            "match its registry entry."
        )

    return profile


def load_default_profile() -> ProfileDefinition:
    """Load the current built-in profile for version 0.2.0."""

    return load_profile(
        _DEFAULT_PROFILE_ID,
        _DEFAULT_PROFILE_VERSION,
    )
