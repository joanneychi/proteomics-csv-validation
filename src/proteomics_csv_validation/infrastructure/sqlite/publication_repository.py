"""SQLite persistence adapter for result and export publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import NoReturn

from proteomics_csv_validation.domain.publication import (
    ExportAttemptRecord,
    ExportAttemptStateConflictError,
    ExportState,
    RESULT_BUNDLE_KIND,
    RunArtifactRecord,
    TERMINAL_EXPORT_STATES,
)

from proteomics_csv_validation.domain.run_lifecycle import (
    LedgerOperationError,
    LedgerRecordNotFoundError,
)

from .connection import (
    _connect,
    _immediate_transaction,
)

from .ledger import verify_ledger


def _raise_integrity(
    operation: str,
    error: sqlite3.IntegrityError,
) -> NoReturn:
    raise LedgerOperationError(
        operation
        + " violated the ledger contract."
    ) from error


def _export_from_row(
    row: tuple[object, ...],
) -> ExportAttemptRecord:
    return ExportAttemptRecord(
        export_attempt_id=str(row[0]),
        run_id=str(row[1]),
        artifact_kind=str(row[2]),
        target_relative_path=str(row[3]),
        status=ExportState(
            str(row[4])
        ),
        started_at=str(row[5]),
        finished_at=(
            None
            if row[6] is None
            else str(row[6])
        ),
        error_code=(
            None
            if row[7] is None
            else str(row[7])
        ),
        error_message=(
            None
            if row[8] is None
            else str(row[8])
        ),
    )


def _artifact_from_row(
    row: tuple[object, ...],
) -> RunArtifactRecord:
    return RunArtifactRecord(
        artifact_id=str(row[0]),
        run_id=str(row[1]),
        export_attempt_id=(
            None
            if row[2] is None
            else str(row[2])
        ),
        kind=str(row[3]),
        schema_id=(
            None
            if row[4] is None
            else str(row[4])
        ),
        schema_version=(
            None
            if row[5] is None
            else str(row[5])
        ),
        relative_path=str(row[6]),
        sha256=str(row[7]),
        byte_count=int(row[8]),
        created_at=str(row[9]),
    )


def _select_export_attempt(
    connection: sqlite3.Connection,
    export_attempt_id: str,
) -> ExportAttemptRecord | None:
    row = connection.execute(
        """
        SELECT
            export_attempt_id,
            run_id,
            artifact_kind,
            target_relative_path,
            status,
            started_at,
            finished_at,
            error_code,
            error_message
        FROM export_attempt
        WHERE export_attempt_id = ?
        """,
        (
            export_attempt_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return _export_from_row(
        row
    )


def _require_export_attempt(
    connection: sqlite3.Connection,
    export_attempt_id: str,
) -> ExportAttemptRecord:
    record = _select_export_attempt(
        connection,
        export_attempt_id,
    )

    if record is None:
        raise LedgerRecordNotFoundError(
            "Export attempt does not exist: "
            + export_attempt_id
        )

    return record


def _run_exists(
    connection: sqlite3.Connection,
    run_id: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM analysis_run
            WHERE run_id = ?
            """,
            (
                run_id,
            ),
        ).fetchone()
        is not None
    )


def _select_artifact(
    connection: sqlite3.Connection,
    artifact_id: str,
) -> RunArtifactRecord | None:
    row = connection.execute(
        """
        SELECT
            artifact_id,
            run_id,
            export_attempt_id,
            kind,
            schema_id,
            schema_version,
            relative_path,
            sha256,
            byte_count,
            created_at
        FROM run_artifact
        WHERE artifact_id = ?
        """,
        (
            artifact_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return _artifact_from_row(
        row
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SQLitePublicationRepository:
    """SQLite implementation of the publication repository port."""

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

    def start_export_attempt(
        self,
        export_attempt_id: str,
        run_id: str,
        artifact_kind: str,
        target_relative_path: str,
        *,
        started_at: str,
    ) -> ExportAttemptRecord:
        connection = _connect(
            self.database_path
        )

        try:
            if not _run_exists(
                connection,
                run_id,
            ):
                raise LedgerRecordNotFoundError(
                    "Analysis run does not exist: "
                    + run_id
                )

            try:
                with _immediate_transaction(
                    connection
                ):
                    connection.execute(
                        """
                        INSERT INTO export_attempt(
                            export_attempt_id,
                            run_id,
                            artifact_kind,
                            target_relative_path,
                            status,
                            started_at
                        )
                        VALUES (?, ?, ?, ?, 'STARTED', ?)
                        """,
                        (
                            export_attempt_id,
                            run_id,
                            artifact_kind,
                            target_relative_path,
                            started_at,
                        ),
                    )

                    return _require_export_attempt(
                        connection,
                        export_attempt_id,
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Start export attempt",
                    error,
                )

        finally:
            connection.close()

    def complete_export_attempt(
        self,
        export_attempt_id: str,
        status: ExportState,
        *,
        finished_at: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ExportAttemptRecord:
        if status not in TERMINAL_EXPORT_STATES:
            raise ValueError(
                "Export completion requires a terminal state."
            )

        if (
            status is ExportState.SUCCEEDED
            and (
                error_code is not None
                or error_message is not None
            )
        ):
            raise ValueError(
                "A successful export cannot contain error state."
            )

        connection = _connect(
            self.database_path
        )

        try:
            try:
                with _immediate_transaction(
                    connection
                ):
                    current = _require_export_attempt(
                        connection,
                        export_attempt_id,
                    )

                    if (
                        current.status
                        is not ExportState.STARTED
                    ):
                        raise ExportAttemptStateConflictError(
                            "Only a STARTED export attempt "
                            "may complete."
                        )

                    cursor = connection.execute(
                        """
                        UPDATE export_attempt
                        SET
                            status = ?,
                            finished_at = ?,
                            error_code = ?,
                            error_message = ?
                        WHERE export_attempt_id = ?
                          AND status = 'STARTED'
                        """,
                        (
                            status.value,
                            finished_at,
                            error_code,
                            error_message,
                            export_attempt_id,
                        ),
                    )

                    if cursor.rowcount != 1:
                        raise ExportAttemptStateConflictError(
                            "Export attempt is no longer STARTED."
                        )

                    return _require_export_attempt(
                        connection,
                        export_attempt_id,
                    )

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Complete export attempt",
                    error,
                )

        finally:
            connection.close()

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
        connection = _connect(
            self.database_path
        )

        try:
            if not _run_exists(
                connection,
                run_id,
            ):
                raise LedgerRecordNotFoundError(
                    "Analysis run does not exist: "
                    + run_id
                )

            try:
                with _immediate_transaction(
                    connection
                ):
                    connection.execute(
                        """
                        INSERT INTO run_artifact(
                            artifact_id,
                            run_id,
                            export_attempt_id,
                            kind,
                            schema_id,
                            schema_version,
                            relative_path,
                            sha256,
                            byte_count,
                            created_at
                        )
                        VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            artifact_id,
                            run_id,
                            RESULT_BUNDLE_KIND,
                            schema_id,
                            schema_version,
                            relative_path,
                            sha256,
                            byte_count,
                            created_at,
                        ),
                    )

                    record = _select_artifact(
                        connection,
                        artifact_id,
                    )

                    assert record is not None

                    return record

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Record result artifact",
                    error,
                )

        finally:
            connection.close()

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
        connection = _connect(
            self.database_path
        )

        try:
            if not _run_exists(
                connection,
                run_id,
            ):
                raise LedgerRecordNotFoundError(
                    "Analysis run does not exist: "
                    + run_id
                )

            if (
                _select_export_attempt(
                    connection,
                    export_attempt_id,
                )
                is None
            ):
                raise LedgerRecordNotFoundError(
                    "Export attempt does not exist: "
                    + export_attempt_id
                )

            try:
                with _immediate_transaction(
                    connection
                ):
                    connection.execute(
                        """
                        INSERT INTO run_artifact(
                            artifact_id,
                            run_id,
                            export_attempt_id,
                            kind,
                            schema_id,
                            schema_version,
                            relative_path,
                            sha256,
                            byte_count,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            artifact_id,
                            run_id,
                            export_attempt_id,
                            kind,
                            schema_id,
                            schema_version,
                            relative_path,
                            sha256,
                            byte_count,
                            created_at,
                        ),
                    )

                    record = _select_artifact(
                        connection,
                        artifact_id,
                    )

                    assert record is not None

                    return record

            except sqlite3.IntegrityError as error:
                _raise_integrity(
                    "Record export artifact",
                    error,
                )

        finally:
            connection.close()

    def get_export_attempt(
        self,
        export_attempt_id: str,
    ) -> ExportAttemptRecord:
        connection = _connect(
            self.database_path
        )

        try:
            return _require_export_attempt(
                connection,
                export_attempt_id,
            )

        finally:
            connection.close()

    def list_artifacts(
        self,
        run_id: str,
    ) -> tuple[
        RunArtifactRecord,
        ...,
    ]:
        connection = _connect(
            self.database_path
        )

        try:
            if not _run_exists(
                connection,
                run_id,
            ):
                raise LedgerRecordNotFoundError(
                    "Analysis run does not exist: "
                    + run_id
                )

            rows = connection.execute(
                """
                SELECT
                    artifact_id,
                    run_id,
                    export_attempt_id,
                    kind,
                    schema_id,
                    schema_version,
                    relative_path,
                    sha256,
                    byte_count,
                    created_at
                FROM run_artifact
                WHERE run_id = ?
                ORDER BY created_at, artifact_id
                """,
                (
                    run_id,
                ),
            ).fetchall()

            return tuple(
                _artifact_from_row(
                    row
                )
                for row in rows
            )

        finally:
            connection.close()
