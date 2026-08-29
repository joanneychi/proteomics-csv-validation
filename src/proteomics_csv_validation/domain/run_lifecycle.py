"""Domain records and states for persisted analysis-run lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunState(str, Enum):
    """Persisted analysis-run lifecycle state."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL_RUN_STATES = frozenset(
    {
        RunState.SUCCEEDED,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.INTERRUPTED,
    }
)


class LedgerOperationError(RuntimeError):
    """Base error for persisted lifecycle operations."""


class LedgerRecordNotFoundError(LedgerOperationError):
    """Raised when a requested lifecycle record does not exist."""


class ReviewDraftRevisionConflictError(LedgerOperationError):
    """Raised when a review-draft revision token is stale."""


class RunStateConflictError(LedgerOperationError):
    """Raised when an operation conflicts with persisted run state."""


@dataclass(
    frozen=True,
    slots=True,
)
class ReviewDraftRecord:
    """Current mutable review-draft revision."""

    draft_id: str
    workspace_id: str
    revision: int
    configuration_json: str
    configuration_sha256: str
    created_at: str
    updated_at: str


@dataclass(
    frozen=True,
    slots=True,
)
class RunConfigurationRecord:
    """Immutable queued-run configuration snapshot."""

    configuration_id: str
    workspace_id: str
    source_draft_id: str | None
    source_draft_revision: int | None
    canonical_json: str
    sha256: str
    created_at: str


@dataclass(
    frozen=True,
    slots=True,
)
class AnalysisRunRecord:
    """Persisted analysis-run state."""

    run_id: str
    workspace_id: str
    configuration_id: str
    status: RunState
    created_at: str
    queued_at: str
    started_at: str | None
    finished_at: str | None
    cancel_requested_at: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class ExecutionEventRecord:
    """Ordered immutable run execution event."""

    run_id: str
    sequence: int
    event_type: str
    occurred_at: str
    detail_json: str | None
