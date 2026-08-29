"""Tests for deterministic result-bundle serialization."""

from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from proteomics_csv_validation.adapters.core_validation import (
    LegacyCoreValidationAdapter,
)
from proteomics_csv_validation.adapters.result_bundle import (
    ValidationResultBundleSerializer,
    result_bundle_schema,
)
from proteomics_csv_validation.application.result_publication import (
    ResultBundleSerializer,
)
from proteomics_csv_validation.application.structural_review import (
    StructuralReviewRequest,
)
from proteomics_csv_validation.domain.result_artifact import (
    RESULT_BUNDLE_JSON_SCHEMA_DIALECT,
    RESULT_BUNDLE_SCHEMA_ID,
    RESULT_BUNDLE_SCHEMA_VERSION,
    ResultBundleConfiguration,
    ResultBundleSerializationError,
    SourceFileEvidence,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    AnalysisRunRecord,
    RunState,
)
from proteomics_csv_validation.models import (
    CategoryCount,
    CodeCount,
    Finding,
    FindingCategory,
    FindingSummary,
    RuleReference,
    Scope,
    ScopeCount,
    Severity,
    SeverityCount,
)


_ROOT = Path(
    __file__
).resolve().parents[1]

_BASELINE = (
    _ROOT
    / "data"
    / "synthetic"
    / "baseline_valid.csv"
)


def _validation():
    return LegacyCoreValidationAdapter().validate(
        StructuralReviewRequest(
            input_path=_BASELINE,
            profile_version="0.2.0",
        )
    )


def _run(
    status: RunState = (
        RunState.SUCCEEDED
    ),
) -> AnalysisRunRecord:
    return AnalysisRunRecord(
        run_id=(
            "0123456789abcdef"
            "0123456789abcdef"
        ),
        workspace_id="local-default",
        configuration_id=(
            "fedcba9876543210"
            "fedcba9876543210"
        ),
        status=status,
        created_at=(
            "2026-08-29T01:00:00Z"
        ),
        queued_at=(
            "2026-08-29T01:00:01Z"
        ),
        started_at=(
            "2026-08-29T01:00:02Z"
        ),
        finished_at=(
            "2026-08-29T01:00:03Z"
        ),
        cancel_requested_at=None,
    )


def _source() -> SourceFileEvidence:
    data = _BASELINE.read_bytes()

    return SourceFileEvidence(
        display_name=(
            _BASELINE.name
        ),
        sha256=hashlib.sha256(
            data
        ).hexdigest(),
        byte_count=len(
            data
        ),
    )


def _configuration(
    validation=None,
) -> ResultBundleConfiguration:
    if validation is None:
        validation = (
            _validation()
        )

    return ResultBundleConfiguration(
        profile_version=(
            validation.profile_version
        ),
        mapping_mode=(
            validation
            .column_mapping
            .mode
            .value
        ),
        source=_source(),
    )


def _imports(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )

    modules: set[str] = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias
                in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(
                node.module
            )

    return modules


def test_result_bundle_schema_contract() -> None:
    schema = result_bundle_schema()

    assert schema[
        "$schema"
    ] == (
        RESULT_BUNDLE_JSON_SCHEMA_DIALECT
    )

    assert schema[
        "$id"
    ] == (
        "urn:proteomics-csv-validation:"
        "result-bundle:1.0.0"
    )

    assert schema[
        "properties"
    ][
        "schema_id"
    ][
        "const"
    ] == RESULT_BUNDLE_SCHEMA_ID

    assert schema[
        "properties"
    ][
        "schema_version"
    ][
        "const"
    ] == RESULT_BUNDLE_SCHEMA_VERSION

    assert schema[
        "$defs"
    ][
        "run"
    ][
        "properties"
    ][
        "status"
    ][
        "const"
    ] == "SUCCEEDED"

    assert schema[
        "$defs"
    ][
        "run"
    ][
        "properties"
    ][
        "run_id"
    ][
        "pattern"
    ] == "^[0-9a-f]{32}$"

    assert schema[
        "$defs"
    ][
        "validation"
    ][
        "additionalProperties"
    ] is False


def test_result_bundle_serialization_is_deterministic_and_complete() -> None:
    validation = _validation()

    serializer = (
        ValidationResultBundleSerializer()
    )

    payload_one = serializer.serialize(
        run=_run(),
        configuration=_configuration(
            validation
        ),
        validation=validation,
    )

    payload_two = serializer.serialize(
        run=_run(),
        configuration=_configuration(
            validation
        ),
        validation=validation,
    )

    assert payload_one == payload_two

    assert payload_one.endswith(
        b"\n"
    )

    assert not payload_one.endswith(
        b"\n\n"
    )

    document = json.loads(
        payload_one.decode(
            "utf-8"
        )
    )

    assert set(
        document
    ) == {
        "schema_id",
        "schema_version",
        "run",
        "configuration",
        "validation",
    }

    assert document[
        "schema_id"
    ] == RESULT_BUNDLE_SCHEMA_ID

    assert document[
        "schema_version"
    ] == (
        RESULT_BUNDLE_SCHEMA_VERSION
    )

    assert document[
        "run"
    ][
        "status"
    ] == "SUCCEEDED"

    assert document[
        "configuration"
    ][
        "source"
    ][
        "display_name"
    ] == "baseline_valid.csv"

    assert document[
        "configuration"
    ][
        "mapping_mode"
    ] == "strict"

    assert document[
        "validation"
    ][
        "status"
    ] == "completed"

    assert document[
        "validation"
    ][
        "rows"
    ] == validation.rows

    assert document[
        "validation"
    ][
        "findings"
    ] == []

    assert document[
        "validation"
    ][
        "column_mapping"
    ][
        "mode"
    ] == "strict"

    assert (
        str(
            _BASELINE.resolve()
        )
        not in payload_one.decode(
            "utf-8"
        )
    )


def test_result_bundle_requires_succeeded_run() -> None:
    serializer = (
        ValidationResultBundleSerializer()
    )

    validation = _validation()

    for status in (
        RunState.QUEUED,
        RunState.RUNNING,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.INTERRUPTED,
    ):
        with pytest.raises(
            ResultBundleSerializationError,
        ):
            serializer.serialize(
                run=_run(
                    status
                ),
                configuration=(
                    _configuration(
                        validation
                    )
                ),
                validation=validation,
            )


def test_result_bundle_rejects_profile_mismatch() -> None:
    validation = _validation()

    configuration = (
        ResultBundleConfiguration(
            profile_version="0.3.0",
            mapping_mode="strict",
            source=_source(),
        )
    )

    with pytest.raises(
        ResultBundleSerializationError,
    ):
        ValidationResultBundleSerializer().serialize(
            run=_run(),
            configuration=configuration,
            validation=validation,
        )


def test_result_bundle_rejects_mapping_mode_mismatch() -> None:
    validation = _validation()

    configuration = (
        ResultBundleConfiguration(
            profile_version="0.2.0",
            mapping_mode="automatic",
            source=_source(),
        )
    )

    with pytest.raises(
        ResultBundleSerializationError,
    ):
        ValidationResultBundleSerializer().serialize(
            run=_run(),
            configuration=configuration,
            validation=validation,
        )


def test_result_bundle_preserves_decimal_and_string_types() -> None:
    baseline = _validation()

    rule = RuleReference(
        rule_id="test.value_identity",
        rule_version="1.0.0",
    )

    finding = Finding(
        code="VALUE_IDENTITY",
        category=(
            FindingCategory.SCHEMA
        ),
        severity=Severity.WARNING,
        scope=Scope.FILE,
        rule=rule,
        location=None,
        entity=None,
        observed_value=Decimal(
            "1.2500"
        ),
        expected_value="1.2500",
        message=(
            "Exact value identity test."
        ),
    )

    result = replace(
        baseline,
        configured_rules=(
            rule,
        ),
        findings=(
            finding,
        ),
        summary=FindingSummary(
            total_findings=1,
            category_counts=(
                CategoryCount(
                    category=(
                        FindingCategory.SCHEMA
                    ),
                    count=1,
                ),
            ),
            code_counts=(
                CodeCount(
                    code="VALUE_IDENTITY",
                    count=1,
                ),
            ),
            severity_counts=(
                SeverityCount(
                    severity=(
                        Severity.WARNING
                    ),
                    count=1,
                ),
            ),
            scope_counts=(
                ScopeCount(
                    scope=Scope.FILE,
                    count=1,
                ),
            ),
        ),
    )

    payload = (
        ValidationResultBundleSerializer()
        .serialize(
            run=_run(),
            configuration=(
                _configuration(
                    result
                )
            ),
            validation=result,
        )
    )

    finding_document = json.loads(
        payload
    )[
        "validation"
    ][
        "findings"
    ][
        0
    ]

    assert finding_document[
        "observed_value"
    ] == {
        "type": "decimal",
        "value": "1.2500",
    }

    assert finding_document[
        "expected_value"
    ] == {
        "type": "string",
        "value": "1.2500",
    }


def test_result_bundle_rejects_nonfinite_decimal() -> None:
    baseline = _validation()

    rule = RuleReference(
        rule_id="test.nonfinite",
        rule_version="1.0.0",
    )

    finding = Finding(
        code="NONFINITE",
        category=(
            FindingCategory.SCHEMA
        ),
        severity=Severity.WARNING,
        scope=Scope.FILE,
        rule=rule,
        location=None,
        entity=None,
        observed_value=Decimal(
            "NaN"
        ),
        expected_value=None,
        message=(
            "Non-finite decimal test."
        ),
    )

    result = replace(
        baseline,
        configured_rules=(
            rule,
        ),
        findings=(
            finding,
        ),
        summary=FindingSummary(
            total_findings=1,
            category_counts=(),
            code_counts=(),
            severity_counts=(),
            scope_counts=(),
        ),
    )

    with pytest.raises(
        ResultBundleSerializationError,
    ):
        ValidationResultBundleSerializer().serialize(
            run=_run(),
            configuration=(
                _configuration(
                    result
                )
            ),
            validation=result,
        )


def test_source_file_evidence_rejects_pathish_display_name() -> None:
    for display_name in (
        "",
        ".",
        "..",
        "../input.csv",
        "folder/input.csv",
        r"C:\fakepath\input.csv",
        "bad\x00name.csv",
    ):
        with pytest.raises(
            ValueError
        ):
            SourceFileEvidence(
                display_name=display_name,
                sha256=(
                    "a"
                    * 64
                ),
                byte_count=1,
            )


def test_source_file_evidence_rejects_invalid_sha() -> None:
    for digest in (
        "",
        "a" * 63,
        "A" * 64,
        "g" * 64,
    ):
        with pytest.raises(
            ValueError
        ):
            SourceFileEvidence(
                display_name="input.csv",
                sha256=digest,
                byte_count=1,
            )


def test_source_file_evidence_rejects_negative_byte_count() -> None:
    with pytest.raises(
        ValueError
    ):
        SourceFileEvidence(
            display_name="input.csv",
            sha256=(
                "a"
                * 64
            ),
            byte_count=-1,
        )


def test_explicit_mapping_requires_mapping_source() -> None:
    with pytest.raises(
        ValueError
    ):
        ResultBundleConfiguration(
            profile_version="0.2.0",
            mapping_mode="explicit",
            source=_source(),
        )

    mapping = SourceFileEvidence(
        display_name="mapping.json",
        sha256=(
            "b"
            * 64
        ),
        byte_count=10,
    )

    configuration = (
        ResultBundleConfiguration(
            profile_version="0.2.0",
            mapping_mode="explicit",
            source=_source(),
            column_mapping_source=(
                mapping
            ),
        )
    )

    assert (
        configuration
        .column_mapping_source
        == mapping
    )

    with pytest.raises(
        TypeError
    ):
        ResultBundleConfiguration(
            profile_version="0.2.0",
            mapping_mode="strict",
            source=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError
    ):
        ResultBundleConfiguration(
            profile_version="0.2.0",
            mapping_mode="explicit",
            source=_source(),
            column_mapping_source=object(),  # type: ignore[arg-type]
        )


def test_result_artifact_domain_has_no_outer_dependencies() -> None:
    path = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "domain"
        / "result_artifact.py"
    )

    forbidden = (
        "proteomics_csv_validation.application",
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.infrastructure",
        "proteomics_csv_validation.web",
        "proteomics_csv_validation.pipeline",
        "proteomics_csv_validation.profiles",
        "proteomics_csv_validation.validators",
    )

    for module in _imports(
        path
    ):
        assert not module.startswith(
            forbidden
        ), (
            module,
            path,
        )


def test_result_publication_application_has_no_outer_dependency() -> None:
    path = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "application"
        / "result_publication.py"
    )

    forbidden = (
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.infrastructure",
        "proteomics_csv_validation.web",
        "proteomics_csv_validation.pipeline",
        "proteomics_csv_validation.profiles",
        "proteomics_csv_validation.validators",
        "proteomics_csv_validation.models",
    )

    for module in _imports(
        path
    ):
        assert not module.startswith(
            forbidden
        ), (
            module,
            path,
        )


def test_serializer_structurally_satisfies_application_port() -> None:
    serializer: ResultBundleSerializer = (
        ValidationResultBundleSerializer()
    )

    payload = serializer.serialize(
        run=_run(),
        configuration=(
            _configuration()
        ),
        validation=_validation(),
    )

    assert isinstance(
        payload,
        bytes,
    )



def test_result_bundle_schema_rejects_pathish_file_evidence() -> None:
    import re

    schema = result_bundle_schema()

    display_name = (
        schema[
            "$defs"
        ][
            "fileEvidence"
        ][
            "properties"
        ][
            "display_name"
        ]
    )

    pattern = display_name[
        "pattern"
    ]

    assert re.fullmatch(
        pattern,
        "input.csv",
    )

    assert re.fullmatch(
        pattern,
        "../input.csv",
    ) is None

    assert re.fullmatch(
        pattern,
        r"C:\input.csv",
    ) is None

    assert display_name[
        "not"
    ][
        "enum"
    ] == [
        ".",
        "..",
    ]


def test_result_bundle_schema_enforces_mapping_source_relationship() -> None:
    schema = result_bundle_schema()

    configuration = schema[
        "$defs"
    ][
        "configuration"
    ]

    rules = configuration[
        "allOf"
    ]

    assert len(
        rules
    ) == 1

    rule = rules[
        0
    ]

    assert rule[
        "if"
    ][
        "properties"
    ][
        "mapping_mode"
    ][
        "const"
    ] == "explicit"

    assert rule[
        "if"
    ][
        "required"
    ] == [
        "mapping_mode",
    ]

    assert rule[
        "then"
    ][
        "properties"
    ][
        "column_mapping_source"
    ][
        "$ref"
    ] == "#/$defs/fileEvidence"

    assert rule[
        "else"
    ][
        "properties"
    ][
        "column_mapping_source"
    ][
        "type"
    ] == "null"

def test_result_bundle_serializer_rejects_schema_invalid_run_id() -> None:
    validation = _validation()

    run = replace(
        _run(),
        run_id="not-a-32-hex-run-id",
    )

    with pytest.raises(
        ResultBundleSerializationError,
    ):
        ValidationResultBundleSerializer().serialize(
            run=run,
            configuration=(
                _configuration(
                    validation
                )
            ),
            validation=validation,
        )
