"""Tests for queued structural-review execution orchestration."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from proteomics_csv_validation.adapters.core_validation import (
    LegacyCoreValidationAdapter,
)
from proteomics_csv_validation.adapters.result_bundle import (
    ValidationResultBundleSerializer,
)
from proteomics_csv_validation.application.publication import (
    PublicationService,
)
from proteomics_csv_validation.application.review_execution import (
    QueuedReviewExecution,
    ResultPublicationError,
    ReviewExecutionContractError,
    ReviewExecutionService,
)
from proteomics_csv_validation.application.run_lifecycle import (
    RunLifecycleService,
)
from proteomics_csv_validation.application.structural_review import (
    StructuralReviewRequest,
    StructuralReviewService,
)
from proteomics_csv_validation.domain.result_artifact import (
    RESULT_BUNDLE_SCHEMA_ID,
    RESULT_BUNDLE_SCHEMA_VERSION,
    ResultBundleConfiguration,
    SourceFileEvidence,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    RunState,
    RunStateConflictError,
)
from proteomics_csv_validation.infrastructure.filesystem.result_store import (
    FilesystemResultStore,
)
from proteomics_csv_validation.infrastructure.sqlite.ledger import (
    initialize_ledger,
)
from proteomics_csv_validation.infrastructure.sqlite.publication_repository import (
    SQLitePublicationRepository,
)
from proteomics_csv_validation.infrastructure.sqlite.run_repository import (
    SQLiteRunRepository,
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

_SEEDED = (
    _ROOT
    / "data"
    / "synthetic"
    / "seeded_errors.csv"
)

_WORKSPACE_ID = "local-default"

_RUN_ID = (
    "1111111111111111"
    "1111111111111111"
)

_ARTIFACT_ID = (
    "2222222222222222"
    "2222222222222222"
)

_CONFIGURATION_ID = (
    "configuration-review-1"
)


class _Clock:
    def __init__(
        self,
    ) -> None:
        self._index = 0

    def __call__(
        self,
    ) -> str:
        self._index += 1

        return (
            "2026-08-29T03:00:"
            + f"{self._index:02d}"
            + "Z"
        )


class _FailingEngine:
    def validate(
        self,
        request: StructuralReviewRequest,
    ):
        raise RuntimeError(
            "review failed"
        )


class _CountingEngine:
    def __init__(
        self,
    ) -> None:
        self.calls = 0

    def validate(
        self,
        request: StructuralReviewRequest,
    ):
        self.calls += 1

        return (
            LegacyCoreValidationAdapter()
            .validate(
                request
            )
        )


class _FailingSerializer:
    def serialize(
        self,
        **kwargs,
    ) -> bytes:
        raise RuntimeError(
            "serialization failed"
        )


class _FailingStore:
    def publish(
        self,
        run_id: str,
        payload: bytes,
    ):
        raise RuntimeError(
            "store failed"
        )

    def read_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bytes:
        raise AssertionError(
            "read_verified must not be called"
        )


class _FailingPublication:
    def record_result_artifact(
        self,
        *args,
        **kwargs,
    ):
        raise RuntimeError(
            "ledger publication failed"
        )

    def list_artifacts(
        self,
        run_id: str,
    ):
        return ()


def _source_evidence(
    input_path: Path,
) -> SourceFileEvidence:
    raw = input_path.read_bytes()

    return SourceFileEvidence(
        display_name=(
            input_path.name
        ),
        sha256=hashlib.sha256(
            raw
        ).hexdigest(),
        byte_count=len(
            raw
        ),
    )


def _request(
    input_path: Path = _BASELINE,
) -> StructuralReviewRequest:
    return StructuralReviewRequest(
        input_path=input_path,
        profile_version="0.2.0",
    )


def _configuration(
    input_path: Path = _BASELINE,
) -> ResultBundleConfiguration:
    return ResultBundleConfiguration(
        profile_version="0.2.0",
        mapping_mode="strict",
        source=_source_evidence(
            input_path
        ),
    )


def _command(
    input_path: Path = _BASELINE,
    *,
    run_id: str = _RUN_ID,
    artifact_id: str = _ARTIFACT_ID,
    workspace_id: str = _WORKSPACE_ID,
    configuration_id: str = _CONFIGURATION_ID,
) -> QueuedReviewExecution:
    return QueuedReviewExecution(
        run_id=run_id,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        configuration_id=(
            configuration_id
        ),
        review_request=_request(
            input_path
        ),
        result_configuration=(
            _configuration(
                input_path
            )
        ),
    )


def _queued_services(
    tmp_path: Path,
    *,
    run_id: str = _RUN_ID,
    engine=None,
):
    database = (
        tmp_path
        / "ledger.sqlite3"
    )

    initialize_ledger(
        database
    )

    clock = _Clock()

    lifecycle = (
        RunLifecycleService(
            SQLiteRunRepository(
                database
            ),
            clock,
        )
    )

    lifecycle.ensure_workspace(
        _WORKSPACE_ID
    )

    lifecycle.snapshot_configuration(
        _CONFIGURATION_ID,
        _WORKSPACE_ID,
        json.dumps(
            {
                "profile_version": "0.2.0",
                "mapping_mode": "strict",
            },
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )

    lifecycle.queue_run(
        run_id,
        _WORKSPACE_ID,
        _CONFIGURATION_ID,
    )

    publication = (
        PublicationService(
            SQLitePublicationRepository(
                database
            ),
            clock,
        )
    )

    structural_review = (
        StructuralReviewService(
            (
                LegacyCoreValidationAdapter()
                if engine is None
                else engine
            )
        )
    )

    store = FilesystemResultStore(
        tmp_path
        / "artifacts"
    )

    service = ReviewExecutionService(
        lifecycle=lifecycle,
        structural_review=(
            structural_review
        ),
        serializer=(
            ValidationResultBundleSerializer()
        ),
        result_store=store,
        publication=publication,
    )

    return (
        service,
        lifecycle,
        publication,
        store,
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
                for alias in node.names
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


def test_execution_command_validates_identity_and_configuration_contract() -> None:
    with pytest.raises(
        ValueError
    ):
        _command(
            run_id="bad",
        )

    with pytest.raises(
        ValueError
    ):
        _command(
            artifact_id="BAD",
        )

    with pytest.raises(
        ValueError
    ):
        _command(
            workspace_id="",
        )

    with pytest.raises(
        ValueError
    ):
        _command(
            configuration_id="",
        )

    with pytest.raises(
        ValueError
    ):
        QueuedReviewExecution(
            run_id=_RUN_ID,
            artifact_id=_ARTIFACT_ID,
            workspace_id=(
                _WORKSPACE_ID
            ),
            configuration_id=(
                _CONFIGURATION_ID
            ),
            review_request=(
                StructuralReviewRequest(
                    input_path=_BASELINE,
                    profile_version=None,
                )
            ),
            result_configuration=(
                _configuration()
            ),
        )

    with pytest.raises(
        ValueError
    ):
        QueuedReviewExecution(
            run_id=_RUN_ID,
            artifact_id=_ARTIFACT_ID,
            workspace_id=(
                _WORKSPACE_ID
            ),
            configuration_id=(
                _CONFIGURATION_ID
            ),
            review_request=(
                StructuralReviewRequest(
                    input_path=_BASELINE,
                    profile_version="0.3.0",
                )
            ),
            result_configuration=(
                _configuration()
            ),
        )

    with pytest.raises(
        ValueError
    ):
        QueuedReviewExecution(
            run_id=_RUN_ID,
            artifact_id=_ARTIFACT_ID,
            workspace_id=(
                _WORKSPACE_ID
            ),
            configuration_id=(
                _CONFIGURATION_ID
            ),
            review_request=(
                StructuralReviewRequest(
                    input_path=_BASELINE,
                    profile_version="0.2.0",
                    auto_map=True,
                )
            ),
            result_configuration=(
                _configuration()
            ),
        )


def test_successful_execution_records_succeeded_run_and_result_artifact(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    outcome = service.execute(
        _command()
    )

    assert outcome.run.status is (
        RunState.SUCCEEDED
    )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    artifacts = (
        publication.list_artifacts(
            _RUN_ID
        )
    )

    assert artifacts == (
        outcome.artifact,
    )

    assert outcome.artifact.kind == (
        "RESULT_BUNDLE"
    )

    assert outcome.artifact.schema_id == (
        RESULT_BUNDLE_SCHEMA_ID
    )

    assert (
        outcome.artifact.schema_version
        == RESULT_BUNDLE_SCHEMA_VERSION
    )

    payload = store.read_verified(
        outcome.artifact.relative_path,
        expected_sha256=(
            outcome.artifact.sha256
        ),
        expected_byte_count=(
            outcome.artifact.byte_count
        ),
    )

    document = json.loads(
        payload
    )

    assert document[
        "run"
    ][
        "status"
    ] == "SUCCEEDED"

    assert document[
        "validation"
    ][
        "summary"
    ][
        "total_findings"
    ] == 0


def test_seeded_execution_publishes_four_findings(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    outcome = service.execute(
        _command(
            _SEEDED
        )
    )

    payload = store.read_verified(
        outcome.artifact.relative_path,
        expected_sha256=(
            outcome.artifact.sha256
        ),
        expected_byte_count=(
            outcome.artifact.byte_count
        ),
    )

    document = json.loads(
        payload
    )

    assert document[
        "validation"
    ][
        "summary"
    ][
        "total_findings"
    ] == 4

    assert len(
        document[
            "validation"
        ][
            "findings"
        ]
    ) == 4

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert len(
        publication.list_artifacts(
            _RUN_ID
        )
    ) == 1


def test_queued_run_identity_mismatch_is_rejected_before_start(
    tmp_path: Path,
) -> None:
    counter = (
        _CountingEngine()
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path,
        engine=counter,
    )

    command = _command(
        configuration_id=(
            "different-configuration"
        )
    )

    with pytest.raises(
        ReviewExecutionContractError
    ):
        service.execute(
            command
        )

    assert counter.calls == 0

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.QUEUED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_review_failure_marks_running_run_failed_and_reraises_original(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path,
        engine=_FailingEngine(),
    )

    with pytest.raises(
        RuntimeError,
        match="review failed",
    ):
        service.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.FAILED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_cancel_requested_queued_run_does_not_execute_review(
    tmp_path: Path,
) -> None:
    counter = (
        _CountingEngine()
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path,
        engine=counter,
    )

    lifecycle.request_cancel(
        _RUN_ID
    )

    with pytest.raises(
        RunStateConflictError
    ):
        service.execute(
            _command()
        )

    record = lifecycle.get_run(
        _RUN_ID
    )

    assert record.status is (
        RunState.QUEUED
    )

    assert (
        record.cancel_requested_at
        is not None
    )

    assert counter.calls == 0

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_serializer_failure_does_not_downgrade_successful_analysis(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    service = ReviewExecutionService(
        lifecycle=(
            service.lifecycle
        ),
        structural_review=(
            service.structural_review
        ),
        serializer=_FailingSerializer(),
        result_store=(
            service.result_store
        ),
        publication=(
            service.publication
        ),
    )

    with pytest.raises(
        ResultPublicationError
    ) as captured:
        service.execute(
            _command()
        )

    assert captured.value.run_id == (
        _RUN_ID
    )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_store_failure_does_not_downgrade_successful_analysis(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    service = ReviewExecutionService(
        lifecycle=(
            service.lifecycle
        ),
        structural_review=(
            service.structural_review
        ),
        serializer=(
            service.serializer
        ),
        result_store=_FailingStore(),
        publication=(
            service.publication
        ),
    )

    with pytest.raises(
        ResultPublicationError
    ):
        service.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_ledger_publication_failure_keeps_analysis_success_separate(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    service = ReviewExecutionService(
        lifecycle=(
            service.lifecycle
        ),
        structural_review=(
            service.structural_review
        ),
        serializer=(
            service.serializer
        ),
        result_store=(
            service.result_store
        ),
        publication=_FailingPublication(),  # type: ignore[arg-type]
    )

    with pytest.raises(
        ResultPublicationError
    ):
        service.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_review_execution_application_has_no_outer_layer_dependency() -> None:
    path = (
        _ROOT
        / "src"
        / "proteomics_csv_validation"
        / "application"
        / "review_execution.py"
    )

    forbidden = (
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.infrastructure",
        "proteomics_csv_validation.web",
        "proteomics_csv_validation.models",
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


class _MutatingEngine:
    def validate(
        self,
        request: StructuralReviewRequest,
    ):
        result = (
            LegacyCoreValidationAdapter()
            .validate(
                request
            )
        )

        request.input_path.write_bytes(
            request.input_path.read_bytes()
            + b"\n"
        )

        return result


class _CommitThenRaisePublication:
    def __init__(
        self,
        delegate,
    ) -> None:
        self.delegate = delegate

    def record_result_artifact(
        self,
        *args,
        **kwargs,
    ):
        self.delegate.record_result_artifact(
            *args,
            **kwargs,
        )

        raise RuntimeError(
            "raised after durable registration"
        )

    def list_artifacts(
        self,
        run_id: str,
    ):
        return self.delegate.list_artifacts(
            run_id
        )


class _UncertainPublication:
    def record_result_artifact(
        self,
        *args,
        **kwargs,
    ):
        raise RuntimeError(
            "registration state unknown"
        )

    def list_artifacts(
        self,
        run_id: str,
    ):
        raise RuntimeError(
            "ledger state unavailable"
        )


class _CleanupFailingStore:
    def __init__(
        self,
        delegate,
    ) -> None:
        self.delegate = delegate

    def publish(
        self,
        run_id: str,
        payload: bytes,
    ):
        return self.delegate.publish(
            run_id,
            payload,
        )

    def read_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bytes:
        return self.delegate.read_verified(
            relative_path,
            expected_sha256=(
                expected_sha256
            ),
            expected_byte_count=(
                expected_byte_count
            ),
        )

    def discard_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bool:
        raise RuntimeError(
            "cleanup failed"
        )


def test_source_evidence_mismatch_fails_before_validation_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.structural_review import (
        StructuralReviewFailure,
    )

    counter = (
        _CountingEngine()
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path,
        engine=counter,
    )

    command = QueuedReviewExecution(
        run_id=_RUN_ID,
        artifact_id=_ARTIFACT_ID,
        workspace_id=_WORKSPACE_ID,
        configuration_id=(
            _CONFIGURATION_ID
        ),
        review_request=_request(
            _SEEDED
        ),
        result_configuration=(
            _configuration(
                _BASELINE
            )
        ),
    )

    with pytest.raises(
        StructuralReviewFailure
    ) as captured:
        service.execute(
            command
        )

    assert captured.value.code == (
        "SOURCE_EVIDENCE_MISMATCH"
    )

    assert counter.calls == 0

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.FAILED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()

    assert not (
        tmp_path
        / "artifacts"
        / "results"
        / (
            _RUN_ID
            + ".json"
        )
    ).exists()


def test_source_mutation_during_review_fails_before_success_publication(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.structural_review import (
        StructuralReviewFailure,
    )

    staged = (
        tmp_path
        / "staged.csv"
    )

    staged.write_bytes(
        _BASELINE.read_bytes()
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path,
        engine=_MutatingEngine(),
    )

    with pytest.raises(
        StructuralReviewFailure
    ) as captured:
        service.execute(
            _command(
                staged
            )
        )

    assert captured.value.code == (
        "SOURCE_EVIDENCE_MISMATCH"
    )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.FAILED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_explicit_mapping_evidence_mismatch_fails_before_validation(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.structural_review import (
        StructuralReviewFailure,
    )

    mapping = (
        tmp_path
        / "mapping.json"
    )

    mapping.write_text(
        '{"mapping_specification_version":"1.0.0","columns":{}}\n',
        encoding="utf-8",
    )

    other = (
        tmp_path
        / "other-mapping.json"
    )

    other.write_text(
        '{"different":true}\n',
        encoding="utf-8",
    )

    counter = (
        _CountingEngine()
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path,
        engine=counter,
    )

    command = QueuedReviewExecution(
        run_id=_RUN_ID,
        artifact_id=_ARTIFACT_ID,
        workspace_id=_WORKSPACE_ID,
        configuration_id=(
            _CONFIGURATION_ID
        ),
        review_request=(
            StructuralReviewRequest(
                input_path=_BASELINE,
                profile_version="0.2.0",
                column_map=mapping,
            )
        ),
        result_configuration=(
            ResultBundleConfiguration(
                profile_version="0.2.0",
                mapping_mode="explicit",
                source=(
                    _source_evidence(
                        _BASELINE
                    )
                ),
                column_mapping_source=(
                    _source_evidence(
                        other
                    )
                ),
            )
        ),
    )

    with pytest.raises(
        StructuralReviewFailure
    ) as captured:
        service.execute(
            command
        )

    assert captured.value.code == (
        "MAPPING_EVIDENCE_MISMATCH"
    )

    assert counter.calls == 0

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.FAILED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()


def test_ledger_publication_failure_discards_unregistered_result(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    failing = ReviewExecutionService(
        lifecycle=(
            service.lifecycle
        ),
        structural_review=(
            service.structural_review
        ),
        serializer=(
            service.serializer
        ),
        result_store=(
            service.result_store
        ),
        publication=_FailingPublication(),  # type: ignore[arg-type]
    )

    with pytest.raises(
        ResultPublicationError
    ):
        failing.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()

    assert not (
        tmp_path
        / "artifacts"
        / "results"
        / (
            _RUN_ID
            + ".json"
        )
    ).exists()


def test_commit_then_raise_reconciles_exact_registered_artifact(
    tmp_path: Path,
) -> None:
    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    recovering = (
        ReviewExecutionService(
            lifecycle=(
                service.lifecycle
            ),
            structural_review=(
                service.structural_review
            ),
            serializer=(
                service.serializer
            ),
            result_store=(
                service.result_store
            ),
            publication=(
                _CommitThenRaisePublication(
                    publication
                )
            ),  # type: ignore[arg-type]
        )
    )

    outcome = recovering.execute(
        _command()
    )

    assert outcome.run.status is (
        RunState.SUCCEEDED
    )

    assert publication.list_artifacts(
        _RUN_ID
    ) == (
        outcome.artifact,
    )

    assert (
        tmp_path
        / "artifacts"
        / outcome.artifact.relative_path
    ).is_file()


def test_publication_reconciliation_failure_preserves_filesystem_result(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.review_execution import (
        ResultPublicationRecoveryError,
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    uncertain = (
        ReviewExecutionService(
            lifecycle=(
                service.lifecycle
            ),
            structural_review=(
                service.structural_review
            ),
            serializer=(
                service.serializer
            ),
            result_store=(
                service.result_store
            ),
            publication=_UncertainPublication(),  # type: ignore[arg-type]
        )
    )

    with pytest.raises(
        ResultPublicationRecoveryError
    ):
        uncertain.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert (
        tmp_path
        / "artifacts"
        / "results"
        / (
            _RUN_ID
            + ".json"
        )
    ).is_file()


def test_cleanup_failure_preserves_filesystem_result_and_reports_recovery_error(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.review_execution import (
        ResultPublicationRecoveryError,
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    cleanup_failing = (
        ReviewExecutionService(
            lifecycle=(
                service.lifecycle
            ),
            structural_review=(
                service.structural_review
            ),
            serializer=(
                service.serializer
            ),
            result_store=(
                _CleanupFailingStore(
                    store
                )
            ),  # type: ignore[arg-type]
            publication=_FailingPublication(),  # type: ignore[arg-type]
        )
    )

    with pytest.raises(
        ResultPublicationRecoveryError
    ):
        cleanup_failing.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    assert publication.list_artifacts(
        _RUN_ID
    ) == ()

    assert (
        tmp_path
        / "artifacts"
        / "results"
        / (
            _RUN_ID
            + ".json"
        )
    ).is_file()


def _tamper_same_size(
    target: Path,
) -> None:
    raw = bytearray(
        target.read_bytes()
    )

    assert raw

    raw[0] ^= 1

    target.write_bytes(
        bytes(
            raw
        )
    )


class _TamperAfterRecordPublication:
    def __init__(
        self,
        delegate,
        store_root: Path,
    ) -> None:
        self.delegate = delegate
        self.store_root = store_root

    def record_result_artifact(
        self,
        *args,
        **kwargs,
    ):
        artifact = (
            self.delegate
            .record_result_artifact(
                *args,
                **kwargs,
            )
        )

        _tamper_same_size(
            self.store_root
            / artifact.relative_path
        )

        return artifact

    def list_artifacts(
        self,
        run_id: str,
    ):
        return self.delegate.list_artifacts(
            run_id
        )


class _TamperAfterRecordThenRaisePublication:
    def __init__(
        self,
        delegate,
        store_root: Path,
    ) -> None:
        self.delegate = delegate
        self.store_root = store_root

    def record_result_artifact(
        self,
        *args,
        **kwargs,
    ):
        artifact = (
            self.delegate
            .record_result_artifact(
                *args,
                **kwargs,
            )
        )

        _tamper_same_size(
            self.store_root
            / artifact.relative_path
        )

        raise RuntimeError(
            "raised after durable registration and tampering"
        )

    def list_artifacts(
        self,
        run_id: str,
    ):
        return self.delegate.list_artifacts(
            run_id
        )


def test_registered_corrupt_result_never_returns_successful_outcome(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.review_execution import (
        ResultPublicationRecoveryError,
    )
    from proteomics_csv_validation.domain.result_artifact import (
        ResultStoreError,
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    store_root = (
        tmp_path
        / "artifacts"
    )

    tampering = ReviewExecutionService(
        lifecycle=(
            service.lifecycle
        ),
        structural_review=(
            service.structural_review
        ),
        serializer=(
            service.serializer
        ),
        result_store=(
            service.result_store
        ),
        publication=(
            _TamperAfterRecordPublication(
                publication,
                store_root,
            )
        ),  # type: ignore[arg-type]
    )

    with pytest.raises(
        ResultPublicationRecoveryError
    ):
        tampering.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    artifacts = publication.list_artifacts(
        _RUN_ID
    )

    assert len(
        artifacts
    ) == 1

    artifact = artifacts[
        0
    ]

    target = (
        store_root
        / artifact.relative_path
    )

    assert target.is_file()

    with pytest.raises(
        ResultStoreError
    ):
        store.read_verified(
            artifact.relative_path,
            expected_sha256=(
                artifact.sha256
            ),
            expected_byte_count=(
                artifact.byte_count
            ),
        )


def test_reconciled_registered_corrupt_result_never_returns_successful_outcome(
    tmp_path: Path,
) -> None:
    from proteomics_csv_validation.application.review_execution import (
        ResultPublicationRecoveryError,
    )
    from proteomics_csv_validation.domain.result_artifact import (
        ResultStoreError,
    )

    (
        service,
        lifecycle,
        publication,
        store,
    ) = _queued_services(
        tmp_path
    )

    store_root = (
        tmp_path
        / "artifacts"
    )

    tampering = ReviewExecutionService(
        lifecycle=(
            service.lifecycle
        ),
        structural_review=(
            service.structural_review
        ),
        serializer=(
            service.serializer
        ),
        result_store=(
            service.result_store
        ),
        publication=(
            _TamperAfterRecordThenRaisePublication(
                publication,
                store_root,
            )
        ),  # type: ignore[arg-type]
    )

    with pytest.raises(
        ResultPublicationRecoveryError
    ):
        tampering.execute(
            _command()
        )

    assert lifecycle.get_run(
        _RUN_ID
    ).status is RunState.SUCCEEDED

    artifacts = publication.list_artifacts(
        _RUN_ID
    )

    assert len(
        artifacts
    ) == 1

    artifact = artifacts[
        0
    ]

    target = (
        store_root
        / artifact.relative_path
    )

    assert target.is_file()

    with pytest.raises(
        ResultStoreError
    ):
        store.read_verified(
            artifact.relative_path,
            expected_sha256=(
                artifact.sha256
            ),
            expected_byte_count=(
                artifact.byte_count
            ),
        )
