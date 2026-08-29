"""Domain records and states for persisted publication activity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .run_lifecycle import LedgerOperationError


RESULT_BUNDLE_KIND = "RESULT_BUNDLE"


class ExportState(str, Enum):
    """Persisted export-attempt lifecycle state."""

    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


TERMINAL_EXPORT_STATES = frozenset(
    {
        ExportState.SUCCEEDED,
        ExportState.FAILED,
    }
)


class ExportAttemptStateConflictError(
    LedgerOperationError
):
    """Raised when an export operation conflicts with persisted state."""


@dataclass(
    frozen=True,
    slots=True,
)
class ExportAttemptRecord:
    """Persisted export publication attempt."""

    export_attempt_id: str
    run_id: str
    artifact_kind: str
    target_relative_path: str
    status: ExportState
    started_at: str
    finished_at: str | None
    error_code: str | None
    error_message: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class RunArtifactRecord:
    """Immutable artifact associated with an analysis run."""

    artifact_id: str
    run_id: str
    export_attempt_id: str | None
    kind: str
    schema_id: str | None
    schema_version: str | None
    relative_path: str
    sha256: str
    byte_count: int
    created_at: str
