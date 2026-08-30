"""Application-level run lifecycle contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from proteomics_csv_validation.domain.run_lifecycle import (
    AnalysisRunRecord,
    ExecutionEventRecord,
    LedgerOperationError,
    LedgerRecordNotFoundError,
    ReviewDraftRecord,
    ReviewDraftRevisionConflictError,
    RunConfigurationRecord,
    RunState,
    RunStateConflictError,
    TERMINAL_RUN_STATES,
)


__all__ = [
    "AnalysisRunRecord",
    "ExecutionEventRecord",
    "LedgerOperationError",
    "LedgerRecordNotFoundError",
    "ReviewDraftRecord",
    "ReviewDraftRevisionConflictError",
    "RunConfigurationRecord",
    "RunLifecycleService",
    "RunRepository",
    "RunState",
    "RunStateConflictError",
    "TERMINAL_RUN_STATES",
]


@runtime_checkable
class RunRepository(Protocol):
    """Persistence port required by run-lifecycle orchestration."""

    def ensure_workspace(
        self,
        workspace_id: str,
        *,
        created_at: str,
    ) -> None:
        """Ensure a workspace ledger identity exists."""

    def create_review_draft(
        self,
        draft_id: str,
        workspace_id: str,
        canonical_json: str,
        *,
        created_at: str,
    ) -> ReviewDraftRecord:
        """Create revision one of a review draft."""

    def revise_review_draft(
        self,
        draft_id: str,
        canonical_json: str,
        *,
        expected_revision: int,
        updated_at: str,
    ) -> ReviewDraftRecord:
        """Advance a draft when the expected revision is current."""

    def snapshot_configuration(
        self,
        configuration_id: str,
        workspace_id: str,
        canonical_json: str,
        *,
        created_at: str,
        source_draft_id: str | None = None,
    ) -> RunConfigurationRecord:
        """Create one immutable run-configuration snapshot."""

    def queue_run(
        self,
        run_id: str,
        workspace_id: str,
        configuration_id: str,
        *,
        created_at: str,
        queued_at: str,
    ) -> AnalysisRunRecord:
        """Persist a queued run and its first execution event."""

    def start_run(
        self,
        run_id: str,
        *,
        started_at: str,
    ) -> AnalysisRunRecord:
        """Transition a queued run into running state."""

    def request_cancel(
        self,
        run_id: str,
        *,
        requested_at: str,
    ) -> AnalysisRunRecord:
        """Record the first cancellation request for active work."""

    def complete_run(
        self,
        run_id: str,
        status: RunState,
        *,
        finished_at: str,
    ) -> AnalysisRunRecord:
        """Transition a run into a permitted terminal state."""

    def recover_interrupted_runs(
        self,
        *,
        interrupted_at: str,
    ) -> tuple[AnalysisRunRecord, ...]:
        """Atomically recover all persisted RUNNING rows."""

    def get_configuration(
        self,
        configuration_id: str,
    ) -> RunConfigurationRecord:
        """Return one persisted run-configuration snapshot."""



    def get_run(
        self,
        run_id: str,
    ) -> AnalysisRunRecord:
        """Return one persisted run."""

    def list_events(
        self,
        run_id: str,
    ) -> tuple[ExecutionEventRecord, ...]:
        """Return execution events in sequence order."""


@dataclass(
    frozen=True,
    slots=True,
)
class RunLifecycleService:
    """Application orchestration over the run repository port."""

    repository: RunRepository
    clock: Callable[[], str]

    def ensure_workspace(
        self,
        workspace_id: str,
    ) -> None:
        now = self.clock()

        self.repository.ensure_workspace(
            workspace_id,
            created_at=now,
        )

    def create_review_draft(
        self,
        draft_id: str,
        workspace_id: str,
        canonical_json: str,
    ) -> ReviewDraftRecord:
        return self.repository.create_review_draft(
            draft_id,
            workspace_id,
            canonical_json,
            created_at=self.clock(),
        )

    def revise_review_draft(
        self,
        draft_id: str,
        canonical_json: str,
        *,
        expected_revision: int,
    ) -> ReviewDraftRecord:
        return self.repository.revise_review_draft(
            draft_id,
            canonical_json,
            expected_revision=expected_revision,
            updated_at=self.clock(),
        )

    def snapshot_configuration(
        self,
        configuration_id: str,
        workspace_id: str,
        canonical_json: str,
        *,
        source_draft_id: str | None = None,
    ) -> RunConfigurationRecord:
        return self.repository.snapshot_configuration(
            configuration_id,
            workspace_id,
            canonical_json,
            created_at=self.clock(),
            source_draft_id=source_draft_id,
        )

    def queue_run(
        self,
        run_id: str,
        workspace_id: str,
        configuration_id: str,
    ) -> AnalysisRunRecord:
        now = self.clock()

        return self.repository.queue_run(
            run_id,
            workspace_id,
            configuration_id,
            created_at=now,
            queued_at=now,
        )

    def start_run(
        self,
        run_id: str,
    ) -> AnalysisRunRecord:
        return self.repository.start_run(
            run_id,
            started_at=self.clock(),
        )

    def request_cancel(
        self,
        run_id: str,
    ) -> AnalysisRunRecord:
        return self.repository.request_cancel(
            run_id,
            requested_at=self.clock(),
        )

    def complete_run(
        self,
        run_id: str,
        status: RunState,
    ) -> AnalysisRunRecord:
        if status not in TERMINAL_RUN_STATES:
            raise ValueError(
                "Run completion requires a terminal state."
            )

        return self.repository.complete_run(
            run_id,
            status,
            finished_at=self.clock(),
        )

    def recover_interrupted_runs(
        self,
    ) -> tuple[AnalysisRunRecord, ...]:
        return self.repository.recover_interrupted_runs(
            interrupted_at=self.clock(),
        )

    def get_configuration(
        self,
        configuration_id: str,
    ) -> RunConfigurationRecord:
        return self.repository.get_configuration(
            configuration_id
        )



    def get_run(
        self,
        run_id: str,
    ) -> AnalysisRunRecord:
        return self.repository.get_run(
            run_id
        )

    def list_events(
        self,
        run_id: str,
    ) -> tuple[ExecutionEventRecord, ...]:
        return self.repository.list_events(
            run_id
        )
