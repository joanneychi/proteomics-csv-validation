from __future__ import annotations

import ast
from pathlib import Path

import pytest

import proteomics_csv_validation.application.publication as application_module
import proteomics_csv_validation.domain.publication as domain_module

from proteomics_csv_validation.application.publication import (
    PublicationRepository,
    PublicationService,
)

from proteomics_csv_validation.domain.publication import (
    ExportAttemptStateConflictError,
    ExportState,
    RESULT_BUNDLE_KIND,
)

from proteomics_csv_validation.domain.run_lifecycle import (
    LedgerOperationError,
    LedgerRecordNotFoundError,
    RunState,
)

from proteomics_csv_validation.infrastructure.sqlite import (
    initialize_ledger,
)

from proteomics_csv_validation.infrastructure.sqlite.publication_repository import (
    SQLitePublicationRepository,
)

from proteomics_csv_validation.infrastructure.sqlite.run_repository import (
    SQLiteRunRepository,
)


T0 = "2026-08-28T00:00:00.000000Z"
T1 = "2026-08-28T00:00:01.000000Z"
T2 = "2026-08-28T00:00:02.000000Z"
T3 = "2026-08-28T00:00:03.000000Z"
T4 = "2026-08-28T00:00:04.000000Z"
T5 = "2026-08-28T00:00:05.000000Z"
T6 = "2026-08-28T00:00:06.000000Z"

SHA_A = "a" * 64
SHA_B = "b" * 64


def _repositories(
    tmp_path: Path,
):
    database = tmp_path / "ledger.sqlite"

    initialize_ledger(
        database
    )

    return (
        SQLiteRunRepository(
            database
        ),
        SQLitePublicationRepository(
            database
        ),
    )


def _queued_run(
    lifecycle: SQLiteRunRepository,
    *,
    run_id: str = "run",
    configuration_id: str = "configuration",
) -> None:
    lifecycle.ensure_workspace(
        "workspace",
        created_at=T0,
    )

    lifecycle.snapshot_configuration(
        configuration_id,
        "workspace",
        "{}",
        created_at=T0,
    )

    lifecycle.queue_run(
        run_id,
        "workspace",
        configuration_id,
        created_at=T0,
        queued_at=T0,
    )


def _succeeded_run(
    lifecycle: SQLiteRunRepository,
    *,
    run_id: str = "run",
    configuration_id: str = "configuration",
) -> None:
    _queued_run(
        lifecycle,
        run_id=run_id,
        configuration_id=configuration_id,
    )

    lifecycle.start_run(
        run_id,
        started_at=T1,
    )

    lifecycle.complete_run(
        run_id,
        RunState.SUCCEEDED,
        finished_at=T2,
    )


def _successful_export(
    publication: SQLitePublicationRepository,
    *,
    run_id: str = "run",
    export_attempt_id: str = "export",
    kind: str = "REVIEW_REPORT",
    path: str = "exports/review.md",
) -> None:
    publication.start_export_attempt(
        export_attempt_id,
        run_id,
        kind,
        path,
        started_at=T3,
    )

    publication.complete_export_attempt(
        export_attempt_id,
        ExportState.SUCCEEDED,
        finished_at=T4,
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

    result = set()

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.Import,
        ):
            result.update(
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
            result.add(
                node.module
            )

    return result


def test_publication_domain_has_no_outer_layer_dependency() -> None:
    imports = _imports(
        Path(
            domain_module.__file__
        )
    )

    assert not any(
        name.startswith(
            (
                "proteomics_csv_validation.application",
                "proteomics_csv_validation.infrastructure",
                "proteomics_csv_validation.web",
            )
        )
        for name in imports
    )


def test_publication_application_has_no_infrastructure_dependency() -> None:
    imports = _imports(
        Path(
            application_module.__file__
        )
    )

    assert not any(
        name.startswith(
            "proteomics_csv_validation.infrastructure"
        )
        for name in imports
    )


def test_sqlite_publication_repository_satisfies_port(
    tmp_path: Path,
) -> None:
    _, publication = _repositories(
        tmp_path
    )

    assert isinstance(
        publication,
        PublicationRepository,
    )


def test_start_export_attempt(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _queued_run(
        lifecycle
    )

    record = publication.start_export_attempt(
        "export",
        "run",
        "REVIEW_REPORT",
        "exports/review.md",
        started_at=T1,
    )

    assert record.status is ExportState.STARTED
    assert record.finished_at is None
    assert record.error_code is None
    assert record.error_message is None


def test_succeed_export_attempt(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _queued_run(
        lifecycle
    )

    publication.start_export_attempt(
        "export",
        "run",
        "REVIEW_REPORT",
        "exports/review.md",
        started_at=T1,
    )

    record = publication.complete_export_attempt(
        "export",
        ExportState.SUCCEEDED,
        finished_at=T2,
    )

    assert record.status is ExportState.SUCCEEDED
    assert record.finished_at == T2
    assert record.error_code is None
    assert record.error_message is None


def test_fail_export_attempt_with_error_evidence(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _queued_run(
        lifecycle
    )

    publication.start_export_attempt(
        "export",
        "run",
        "REVIEW_REPORT",
        "exports/review.md",
        started_at=T1,
    )

    record = publication.complete_export_attempt(
        "export",
        ExportState.FAILED,
        finished_at=T2,
        error_code="WRITE_FAILED",
        error_message="Publication failed.",
    )

    assert record.status is ExportState.FAILED
    assert record.error_code == "WRITE_FAILED"
    assert record.error_message == "Publication failed."


def test_terminal_export_cannot_complete_again(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _queued_run(
        lifecycle
    )

    _successful_export(
        publication
    )

    with pytest.raises(
        ExportAttemptStateConflictError,
    ):
        publication.complete_export_attempt(
            "export",
            ExportState.FAILED,
            finished_at=T5,
        )


def test_missing_export_attempt_raises(
    tmp_path: Path,
) -> None:
    _, publication = _repositories(
        tmp_path
    )

    with pytest.raises(
        LedgerRecordNotFoundError,
    ):
        publication.get_export_attempt(
            "missing"
        )


def test_result_bundle_after_succeeded_run(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    artifact = publication.record_result_artifact(
        "result",
        "run",
        schema_id="result-bundle",
        schema_version="1.0",
        relative_path="results/result-bundle.json",
        sha256=SHA_A,
        byte_count=100,
        created_at=T3,
    )

    assert artifact.kind == RESULT_BUNDLE_KIND
    assert artifact.export_attempt_id is None


def test_result_bundle_before_succeeded_run_is_rejected(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _queued_run(
        lifecycle
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_result_artifact(
            "result",
            "run",
            schema_id="result-bundle",
            schema_version="1.0",
            relative_path="results/result-bundle.json",
            sha256=SHA_A,
            byte_count=100,
            created_at=T1,
        )


def test_export_artifact_after_success(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    _successful_export(
        publication
    )

    artifact = publication.record_export_artifact(
        "report",
        "run",
        "export",
        kind="REVIEW_REPORT",
        schema_id="review-report",
        schema_version="2.0",
        relative_path="exports/review.md",
        sha256=SHA_B,
        byte_count=200,
        created_at=T5,
    )

    assert artifact.export_attempt_id == "export"
    assert artifact.kind == "REVIEW_REPORT"


def test_export_artifact_before_success_is_rejected(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _queued_run(
        lifecycle
    )

    publication.start_export_attempt(
        "export",
        "run",
        "REVIEW_REPORT",
        "exports/review.md",
        started_at=T1,
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_export_artifact(
            "report",
            "run",
            "export",
            kind="REVIEW_REPORT",
            schema_id="review-report",
            schema_version="2.0",
            relative_path="exports/review.md",
            sha256=SHA_A,
            byte_count=10,
            created_at=T2,
        )


def test_export_artifact_cross_run_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle,
        run_id="run-one",
        configuration_id="config-one",
    )

    _succeeded_run(
        lifecycle,
        run_id="run-two",
        configuration_id="config-two",
    )

    _successful_export(
        publication,
        run_id="run-one",
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_export_artifact(
            "report",
            "run-two",
            "export",
            kind="REVIEW_REPORT",
            schema_id=None,
            schema_version=None,
            relative_path="exports/review.md",
            sha256=SHA_A,
            byte_count=10,
            created_at=T5,
        )


def test_export_artifact_kind_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    _successful_export(
        publication
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_export_artifact(
            "artifact",
            "run",
            "export",
            kind="SAFE_CSV",
            schema_id=None,
            schema_version=None,
            relative_path="exports/review.md",
            sha256=SHA_A,
            byte_count=10,
            created_at=T5,
        )


def test_export_artifact_path_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    _successful_export(
        publication
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_export_artifact(
            "artifact",
            "run",
            "export",
            kind="REVIEW_REPORT",
            schema_id=None,
            schema_version=None,
            relative_path="exports/different.md",
            sha256=SHA_A,
            byte_count=10,
            created_at=T5,
        )


def test_duplicate_artifact_identity_is_rejected(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    publication.record_result_artifact(
        "artifact",
        "run",
        schema_id="result-bundle",
        schema_version="1.0",
        relative_path="results/result.json",
        sha256=SHA_A,
        byte_count=10,
        created_at=T3,
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_result_artifact(
            "artifact",
            "run",
            schema_id="result-bundle",
            schema_version="1.0",
            relative_path="results/other.json",
            sha256=SHA_B,
            byte_count=20,
            created_at=T4,
        )


def test_publication_service_clock_and_artifact_listing(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    times = iter(
        [
            T3,
            T4,
            T5,
        ]
    )

    service = PublicationService(
        repository=publication,
        clock=lambda: next(
            times
        ),
    )

    started = service.start_export_attempt(
        "export",
        "run",
        "REVIEW_REPORT",
        "exports/review.md",
    )

    succeeded = service.succeed_export_attempt(
        "export"
    )

    artifact = service.record_export_artifact(
        "report",
        "run",
        "export",
        kind="REVIEW_REPORT",
        schema_id="review-report",
        schema_version="2.0",
        relative_path="exports/review.md",
        sha256=SHA_A,
        byte_count=10,
    )

    assert started.started_at == T3
    assert succeeded.finished_at == T4
    assert artifact.created_at == T5

    assert service.list_artifacts(
        "run"
    ) == (
        artifact,
    )

def test_only_one_result_bundle_is_allowed_per_run(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    publication.record_result_artifact(
        "result-one",
        "run",
        schema_id="result-bundle",
        schema_version="1.0",
        relative_path="results/result-one.json",
        sha256=SHA_A,
        byte_count=10,
        created_at=T3,
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_result_artifact(
            "result-two",
            "run",
            schema_id="result-bundle",
            schema_version="1.0",
            relative_path="results/result-two.json",
            sha256=SHA_B,
            byte_count=20,
            created_at=T4,
        )

    assert [
        artifact.artifact_id
        for artifact in publication.list_artifacts(
            "run"
        )
    ] == [
        "result-one",
    ]


def test_only_one_artifact_is_allowed_per_export_attempt(
    tmp_path: Path,
) -> None:
    lifecycle, publication = _repositories(
        tmp_path
    )

    _succeeded_run(
        lifecycle
    )

    _successful_export(
        publication
    )

    publication.record_export_artifact(
        "report-one",
        "run",
        "export",
        kind="REVIEW_REPORT",
        schema_id="review-report",
        schema_version="2.0",
        relative_path="exports/review.md",
        sha256=SHA_A,
        byte_count=10,
        created_at=T5,
    )

    with pytest.raises(
        LedgerOperationError,
    ):
        publication.record_export_artifact(
            "report-two",
            "run",
            "export",
            kind="REVIEW_REPORT",
            schema_id="review-report",
            schema_version="2.0",
            relative_path="exports/review.md",
            sha256=SHA_B,
            byte_count=20,
            created_at=T6,
        )

    assert [
        artifact.artifact_id
        for artifact in publication.list_artifacts(
            "run"
        )
    ] == [
        "report-one",
    ]
