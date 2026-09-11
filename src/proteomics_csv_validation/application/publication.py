"""Application contract for persisted result and export publication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from proteomics_csv_validation.domain.publication import (
    ExportAttemptRecord,
    ExportState,
    RunArtifactRecord,
)


@runtime_checkable
class PublicationRepository(Protocol):
    """Persistence port for result and export publication."""

    def start_export_attempt(
        self,
        export_attempt_id: str,
        run_id: str,
        artifact_kind: str,
        target_relative_path: str,
        *,
        started_at: str,
    ) -> ExportAttemptRecord:
        """Persist a STARTED export attempt."""

    def complete_export_attempt(
        self,
        export_attempt_id: str,
        status: ExportState,
        *,
        finished_at: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ExportAttemptRecord:
        """Complete a STARTED export attempt."""

    def record_result_artifact(
        self,
        artifact_id: str,
        run_id: str,
        *,
        schema_id: str | None,
        schema_version: str | None,
        relative_path: str,
        sha256: str,
        byte_count: int,
        created_at: str,
    ) -> RunArtifactRecord:
        """Persist the result bundle for the run."""

    def record_export_artifact(
        self,
        artifact_id: str,
        run_id: str,
        export_attempt_id: str,
        *,
        kind: str,
        schema_id: str | None,
        schema_version: str | None,
        relative_path: str,
        sha256: str,
        byte_count: int,
        created_at: str,
    ) -> RunArtifactRecord:
        """Persist an artifact published by a successful export."""

    def get_export_attempt(
        self,
        export_attempt_id: str,
    ) -> ExportAttemptRecord:
        """Return one export attempt."""

    def list_artifacts(
        self,
        run_id: str,
    ) -> tuple[RunArtifactRecord, ...]:
        """Return immutable run artifacts."""


@dataclass(
    frozen=True,
    slots=True,
)
class PublicationService:
    """Application orchestration for persisted publication state."""

    repository: PublicationRepository
    clock: Callable[[], str]

    def start_export_attempt(
        self,
        export_attempt_id: str,
        run_id: str,
        artifact_kind: str,
        target_relative_path: str,
    ) -> ExportAttemptRecord:
        return self.repository.start_export_attempt(
            export_attempt_id,
            run_id,
            artifact_kind,
            target_relative_path,
            started_at=self.clock(),
        )

    def succeed_export_attempt(
        self,
        export_attempt_id: str,
    ) -> ExportAttemptRecord:
        return self.repository.complete_export_attempt(
            export_attempt_id,
            ExportState.SUCCEEDED,
            finished_at=self.clock(),
        )

    def fail_export_attempt(
        self,
        export_attempt_id: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ExportAttemptRecord:
        return self.repository.complete_export_attempt(
            export_attempt_id,
            ExportState.FAILED,
            finished_at=self.clock(),
            error_code=error_code,
            error_message=error_message,
        )

    def record_result_artifact(
        self,
        artifact_id: str,
        run_id: str,
        *,
        schema_id: str | None,
        schema_version: str | None,
        relative_path: str,
        sha256: str,
        byte_count: int,
    ) -> RunArtifactRecord:
        return self.repository.record_result_artifact(
            artifact_id,
            run_id,
            schema_id=schema_id,
            schema_version=schema_version,
            relative_path=relative_path,
            sha256=sha256,
            byte_count=byte_count,
            created_at=self.clock(),
        )

    def record_export_artifact(
        self,
        artifact_id: str,
        run_id: str,
        export_attempt_id: str,
        *,
        kind: str,
        schema_id: str | None,
        schema_version: str | None,
        relative_path: str,
        sha256: str,
        byte_count: int,
    ) -> RunArtifactRecord:
        return self.repository.record_export_artifact(
            artifact_id,
            run_id,
            export_attempt_id,
            kind=kind,
            schema_id=schema_id,
            schema_version=schema_version,
            relative_path=relative_path,
            sha256=sha256,
            byte_count=byte_count,
            created_at=self.clock(),
        )

    def get_export_attempt(
        self,
        export_attempt_id: str,
    ) -> ExportAttemptRecord:
        return self.repository.get_export_attempt(
            export_attempt_id
        )

    def list_artifacts(
        self,
        run_id: str,
    ) -> tuple[RunArtifactRecord, ...]:
        return self.repository.list_artifacts(
            run_id
        )
