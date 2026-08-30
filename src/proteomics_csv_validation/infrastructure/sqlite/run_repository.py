"""SQLite persistence adapter for the application run lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import NoReturn

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

from .connection import (
    _connect,
    _immediate_transaction,
)
from .ledger import verify_ledger


_ALLOWED_SOURCES = {
    RunState.SUCCEEDED: frozenset(
        {
            RunState.RUNNING,
        }
    ),
    RunState.FAILED: frozenset(
        {
            RunState.QUEUED,
            RunState.RUNNING,
        }
    ),
    RunState.CANCELLED: frozenset(
        {
            RunState.QUEUED,
            RunState.RUNNING,
        }
    ),
    RunState.INTERRUPTED: frozenset(
        {
            RunState.RUNNING,
        }
    ),
}


def _text_sha256(
    value: str,
) -> str:
    return sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def _raise_integrity(
    operation: str,
    error: sqlite3.IntegrityError,
) -> NoReturn:
    raise LedgerOperationError(
        operation
        + " violated the ledger contract."
    ) from error


def _draft_from_row(
    row: tuple[object, ...],
) -> ReviewDraftRecord:
    return ReviewDraftRecord(
        draft_id=str(row[0]),
        workspace_id=str(row[1]),
        revision=int(row[2]),
        configuration_json=str(row[3]),
        configuration_sha256=str(row[4]),
        created_at=str(row[5]),
        updated_at=str(row[6]),
    )


def _configuration_from_row(
    row: tuple[object, ...],
) -> RunConfigurationRecord:
    return RunConfigurationRecord(
        configuration_id=str(row[0]),
        workspace_id=str(row[1]),
        source_draft_id=(
            None
            if row[2] is None
            else str(row[2])
        ),
        source_draft_revision=(
            None
            if row[3] is None
            else int(row[3])
        ),
        canonical_json=str(row[4]),
        sha256=str(row[5]),
        created_at=str(row[6]),
    )


def _run_from_row(
    row: tuple[object, ...],
) -> AnalysisRunRecord:
    return AnalysisRunRecord(
        run_id=str(row[0]),
        workspace_id=str(row[1]),
        configuration_id=str(row[2]),
        status=RunState(
            str(row[3])
        ),
        created_at=str(row[4]),
        queued_at=str(row[5]),
        started_at=(
            None
            if row[6] is None
            else str(row[6])
        ),
        finished_at=(
            None
            if row[7] is None
            else str(row[7])
        ),
        cancel_requested_at=(
            None
            if row[8] is None
            else str(row[8])
        ),
    )


def _event_from_row(
    row: tuple[object, ...],
) -> ExecutionEventRecord:
    return ExecutionEventRecord(
        run_id=str(row[0]),
        sequence=int(row[1]),
        event_type=str(row[2]),
        occurred_at=str(row[3]),
        detail_json=(
            None
            if row[4] is None
            else str(row[4])
        ),
    )


def _select_draft(
    connection: sqlite3.Connection,
    draft_id: str,
) -> ReviewDraftRecord | None:
    row = connection.execute(
        """
        SELECT
            draft_id,
            workspace_id,
            revision,
            configuration_json,
            configuration_sha256,
            created_at,
            updated_at
        FROM review_draft
        WHERE draft_id = ?
        """,
        (
            draft_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return _draft_from_row(
        row
    )


def _select_configuration(
    connection: sqlite3.Connection,
    configuration_id: str,
) -> RunConfigurationRecord | None:
    row = connection.execute(
        """
        SELECT
            configuration_id,
            workspace_id,
            source_draft_id,
            source_draft_revision,
            canonical_json,
            sha256,
            created_at
        FROM run_configuration
        WHERE configuration_id = ?
        """,
        (
            configuration_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return _configuration_from_row(
        row
    )


def _select_run(
    connection: sqlite3.Connection,
    run_id: str,
) -> AnalysisRunRecord | None:
    row = connection.execute(
        """
        SELECT
            run_id,
            workspace_id,
            configuration_id,
            status,
            created_at,
            queued_at,
            started_at,
            finished_at,
            cancel_requested_at
        FROM analysis_run
        WHERE run_id = ?
        """,
        (
            run_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return _run_from_row(
        row
    )


def _require_run(
    connection: sqlite3.Connection,
    run_id: str,
) -> AnalysisRunRecord:
    record = _select_run(
        connection,
        run_id,
    )

    if record is None:
        raise LedgerRecordNotFoundError(
            "Analysis run does not exist: "
            + run_id
        )

    return record


def _next_event_sequence(
    connection: sqlite3.Connection,
    run_id: str,
) -> int:
    row = connection.execute(
        """
        SELECT
            COALESCE(
                MAX(sequence),
                0
            ) + 1
        FROM execution_event
        WHERE run_id = ?
        """,
        (
            run_id,
        ),
    ).fetchone()

    assert row is not None

    return int(
        row[0]
    )


def _append_event(
    connection: sqlite3.Connection,
    run_id: str,
    event_type: str,
    occurred_at: str,
    *,
    detail_json: str | None = None,
) -> ExecutionEventRecord:
    sequence = _next_event_sequence(
        connection,
        run_id,
    )

    connection.execute(
        """
        INSERT INTO execution_event(
            run_id,
            sequence,
            event_type,
            occurred_at,
            detail_json
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            run_id,
            sequence,
            event_type,
            occurred_at,
            detail_json,
        ),
    )

    return ExecutionEventRecord(
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        occurred_at=occurred_at,
        detail_json=detail_json,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SQLiteRunRepository:
    """SQLite implementation of the run repository port."""

    database_path: Path

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.database_path,
            Path,
        ):
            raise TypeError(
                "database_path must be a pathlib.Path."
            )

        verify_ledger(
            self.database_path
        )

    def ensure_workspace(
        self,
        workspace_id: str,
        *,
        created_at: str,
    ) -> None:
        connection = _connect(
            self.database_path
        )

        try:
            with _immediate_transaction(
                connection
            ):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO workspace(
                        workspace_id,
                        created_at
                    )
                    VALUES (?, ?)
                    """,
                    (
                        workspace_id,
                        created_at,
                    ),
                )

        finally:
            connection.close()

    def create_review_draft(
        self,
        draft_id: str,
        workspace_id: str,
        canonical_json: str,
        *,
        created_at: str,
    ) -> ReviewDraftRecord:
        digest = _text_sha256(
            canonical_json
        )

        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    connection.execute(
                        """
                        INSERT INTO review_draft(
                            draft_id,
                            workspace_id,
                            revision,
                            configuration_json,
                            configuration_sha256,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, 1, ?, ?, ?, ?)
                        """,
                        (
                            draft_id,
                            workspace_id,
                            canonical_json,
                            digest,
                            created_at,
                            created_at,
                        ),
                    )

                    record = _select_draft(
                        connection,
                        draft_id,
                    )

                    assert record is not None

                    return record

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Create review draft",
                    error,
                )

        finally:
            connection.close()

    def revise_review_draft(
        self,
        draft_id: str,
        canonical_json: str,
        *,
        expected_revision: int,
        updated_at: str,
    ) -> ReviewDraftRecord:
        if (
            isinstance(
                expected_revision,
                bool,
            )
            or not isinstance(
                expected_revision,
                int,
            )
            or expected_revision < 1
        ):
            raise ValueError(
                "expected_revision must be a positive integer."
            )

        digest = _text_sha256(
            canonical_json
        )

        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    cursor = connection.execute(
                        """
                        UPDATE review_draft
                        SET
                            revision = revision + 1,
                            configuration_json = ?,
                            configuration_sha256 = ?,
                            updated_at = ?
                        WHERE draft_id = ?
                          AND revision = ?
                        """,
                        (
                            canonical_json,
                            digest,
                            updated_at,
                            draft_id,
                            expected_revision,
                        ),
                    )

                    if cursor.rowcount != 1:
                        current = _select_draft(
                            connection,
                            draft_id,
                        )

                        if current is None:
                            raise LedgerRecordNotFoundError(
                                "Review draft does not exist: "
                                + draft_id
                            )

                        raise ReviewDraftRevisionConflictError(
                            "Review draft revision conflict: "
                            + "expected "
                            + str(expected_revision)
                            + ", current "
                            + str(current.revision)
                            + "."
                        )

                    record = _select_draft(
                        connection,
                        draft_id,
                    )

                    assert record is not None

                    return record

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Revise review draft",
                    error,
                )

        finally:
            connection.close()

    def snapshot_configuration(
        self,
        configuration_id: str,
        workspace_id: str,
        canonical_json: str,
        *,
        created_at: str,
        source_draft_id: str | None = None,
    ) -> RunConfigurationRecord:
        digest = _text_sha256(
            canonical_json
        )

        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    source_revision: int | None = None

                    if source_draft_id is not None:
                        source = _select_draft(
                            connection,
                            source_draft_id,
                        )

                        if source is None:
                            raise LedgerRecordNotFoundError(
                                "Review draft does not exist: "
                                + source_draft_id
                            )

                        if source.workspace_id != workspace_id:
                            raise LedgerOperationError(
                                "Review draft and configuration "
                                "must belong to the same workspace."
                            )

                        if (
                            source.configuration_json
                            != canonical_json
                        ):
                            raise LedgerOperationError(
                                "Run configuration must match "
                                "the current review draft revision."
                            )

                        source_revision = (
                            source.revision
                        )

                    connection.execute(
                        """
                        INSERT INTO run_configuration(
                            configuration_id,
                            workspace_id,
                            source_draft_id,
                            source_draft_revision,
                            canonical_json,
                            sha256,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            configuration_id,
                            workspace_id,
                            source_draft_id,
                            source_revision,
                            canonical_json,
                            digest,
                            created_at,
                        ),
                    )

                    record = _select_configuration(
                        connection,
                        configuration_id,
                    )

                    assert record is not None

                    return record

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Snapshot run configuration",
                    error,
                )

        finally:
            connection.close()

    def queue_run(
        self,
        run_id: str,
        workspace_id: str,
        configuration_id: str,
        *,
        created_at: str,
        queued_at: str,
    ) -> AnalysisRunRecord:
        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    configuration = (
                        _select_configuration(
                            connection,
                            configuration_id,
                        )
                    )

                    if configuration is None:
                        raise LedgerRecordNotFoundError(
                            "Run configuration does not exist: "
                            + configuration_id
                        )

                    if (
                        configuration.workspace_id
                        != workspace_id
                    ):
                        raise LedgerOperationError(
                            "Run and configuration must "
                            "belong to the same workspace."
                        )

                    connection.execute(
                        """
                        INSERT INTO analysis_run(
                            run_id,
                            workspace_id,
                            configuration_id,
                            status,
                            created_at,
                            queued_at
                        )
                        VALUES (?, ?, ?, 'QUEUED', ?, ?)
                        """,
                        (
                            run_id,
                            workspace_id,
                            configuration_id,
                            created_at,
                            queued_at,
                        ),
                    )

                    _append_event(
                        connection,
                        run_id,
                        RunState.QUEUED.value,
                        queued_at,
                    )

                    return _require_run(
                        connection,
                        run_id,
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Queue analysis run",
                    error,
                )

        finally:
            connection.close()

    def start_run(
        self,
        run_id: str,
        *,
        started_at: str,
    ) -> AnalysisRunRecord:
        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    current = _require_run(
                        connection,
                        run_id,
                    )

                    if (
                        current.status
                        is not RunState.QUEUED
                    ):
                        raise RunStateConflictError(
                            "Only a QUEUED run may start."
                        )

                    if (
                        current.cancel_requested_at
                        is not None
                    ):
                        raise RunStateConflictError(
                            "A run with a cancellation "
                            "request cannot start."
                        )

                    cursor = connection.execute(
                        """
                        UPDATE analysis_run
                        SET
                            status = 'RUNNING',
                            started_at = ?
                        WHERE run_id = ?
                          AND status = 'QUEUED'
                          AND cancel_requested_at IS NULL
                        """,
                        (
                            started_at,
                            run_id,
                        ),
                    )

                    if cursor.rowcount != 1:
                        raise RunStateConflictError(
                            "Run is no longer eligible to start."
                        )

                    _append_event(
                        connection,
                        run_id,
                        RunState.RUNNING.value,
                        started_at,
                    )

                    return _require_run(
                        connection,
                        run_id,
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Start analysis run",
                    error,
                )

        finally:
            connection.close()

    def request_cancel(
        self,
        run_id: str,
        *,
        requested_at: str,
    ) -> AnalysisRunRecord:
        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    current = _require_run(
                        connection,
                        run_id,
                    )

                    if (
                        current.status
                        in TERMINAL_RUN_STATES
                    ):
                        raise RunStateConflictError(
                            "A terminal run cannot accept "
                            "a cancellation request."
                        )

                    if (
                        current.cancel_requested_at
                        is not None
                    ):
                        return current

                    connection.execute(
                        """
                        UPDATE analysis_run
                        SET cancel_requested_at = ?
                        WHERE run_id = ?
                          AND status IN (
                              'QUEUED',
                              'RUNNING'
                          )
                          AND cancel_requested_at IS NULL
                        """,
                        (
                            requested_at,
                            run_id,
                        ),
                    )

                    _append_event(
                        connection,
                        run_id,
                        "CANCEL_REQUESTED",
                        requested_at,
                    )

                    return _require_run(
                        connection,
                        run_id,
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Request analysis-run cancellation",
                    error,
                )

        finally:
            connection.close()

    def complete_run(
        self,
        run_id: str,
        status: RunState,
        *,
        finished_at: str,
    ) -> AnalysisRunRecord:
        if status not in TERMINAL_RUN_STATES:
            raise ValueError(
                "Completion requires a terminal run state."
            )

        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    current = _require_run(
                        connection,
                        run_id,
                    )

                    allowed_sources = (
                        _ALLOWED_SOURCES[
                            status
                        ]
                    )

                    if (
                        current.status
                        not in allowed_sources
                    ):
                        raise RunStateConflictError(
                            "Transition "
                            + current.status.value
                            + " -> "
                            + status.value
                            + " is not permitted."
                        )

                    connection.execute(
                        """
                        UPDATE analysis_run
                        SET
                            status = ?,
                            finished_at = ?
                        WHERE run_id = ?
                          AND status = ?
                        """,
                        (
                            status.value,
                            finished_at,
                            run_id,
                            current.status.value,
                        ),
                    )

                    _append_event(
                        connection,
                        run_id,
                        status.value,
                        finished_at,
                    )

                    return _require_run(
                        connection,
                        run_id,
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Complete analysis run",
                    error,
                )

        finally:
            connection.close()

    def recover_interrupted_runs(
        self,
        *,
        interrupted_at: str,
    ) -> tuple[
        AnalysisRunRecord,
        ...,
    ]:
        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    run_ids = [
                        str(row[0])
                        for row
                        in connection.execute(
                            """
                            SELECT run_id
                            FROM analysis_run
                            WHERE status = 'RUNNING'
                            ORDER BY run_id
                            """
                        ).fetchall()
                    ]

                    recovered = []

                    for run_id in run_ids:
                        connection.execute(
                            """
                            UPDATE analysis_run
                            SET
                                status = 'INTERRUPTED',
                                finished_at = ?
                            WHERE run_id = ?
                              AND status = 'RUNNING'
                            """,
                            (
                                interrupted_at,
                                run_id,
                            ),
                        )

                        _append_event(
                            connection,
                            run_id,
                            "RECOVERY_INTERRUPTED",
                            interrupted_at,
                        )

                        recovered.append(
                            _require_run(
                                connection,
                                run_id,
                            )
                        )

                    return tuple(
                        recovered
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Recover interrupted analysis runs",
                    error,
                )

        finally:
            connection.close()

    def get_configuration(
        self,
        configuration_id: str,
    ) -> RunConfigurationRecord:
        connection = _connect(
            self.database_path
        )

        try:
            record = _select_configuration(
                connection,
                configuration_id,
            )

            if record is None:
                raise LedgerRecordNotFoundError(
                    "Run configuration does not exist: "
                    + configuration_id
                )

            return record

        finally:
            connection.close()

    def list_runs(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> tuple[AnalysisRunRecord, ...]:
        if (
            isinstance(
                limit,
                bool,
            )
            or not isinstance(
                limit,
                int,
            )
        ):
            raise TypeError(
                "limit must be an integer."
            )

        if limit <= 0:
            raise ValueError(
                "limit must be positive."
            )

        connection = _connect(
            self.database_path
        )

        try:
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    workspace_id,
                    configuration_id,
                    status,
                    created_at,
                    queued_at,
                    started_at,
                    finished_at,
                    cancel_requested_at
                FROM analysis_run
                WHERE workspace_id = ?
                ORDER BY
                    created_at DESC,
                    run_id DESC
                LIMIT ?
                """,
                (
                    workspace_id,
                    limit,
                ),
            ).fetchall()

            return tuple(
                _run_from_row(
                    row
                )
                for row in rows
            )

        finally:
            connection.close()



    def get_run(
        self,
        run_id: str,
    ) -> AnalysisRunRecord:
        connection = _connect(
            self.database_path
        )

        try:
            return _require_run(
                connection,
                run_id,
            )

        finally:
            connection.close()

    def list_events(
        self,
        run_id: str,
    ) -> tuple[
        ExecutionEventRecord,
        ...,
    ]:
        connection = _connect(
            self.database_path
        )

        try:
            if (
                _select_run(
                    connection,
                    run_id,
                )
                is None
            ):
                raise LedgerRecordNotFoundError(
                    "Analysis run does not exist: "
                    + run_id
                )

            rows = connection.execute(
                """
                SELECT
                    run_id,
                    sequence,
                    event_type,
                    occurred_at,
                    detail_json
                FROM execution_event
                WHERE run_id = ?
                ORDER BY sequence
                """,
                (
                    run_id,
                ),
            ).fetchall()

            return tuple(
                _event_from_row(
                    row
                )
                for row in rows
            )

        finally:
            connection.close()
