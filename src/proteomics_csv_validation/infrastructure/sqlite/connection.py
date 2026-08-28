"""SQLite connection and transaction policy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from proteomics_csv_validation.infrastructure.sqlite.errors import (
    LedgerIntegrityError,
)


_DEFAULT_TIMEOUT_SECONDS = 5.0
_BUSY_TIMEOUT_MS = 5000


def _connect(
    path: Path,
) -> sqlite3.Connection:
    """Open one connection using the frozen transaction policy."""

    if not isinstance(
        path,
        Path,
    ):
        raise TypeError(
            "path must be a pathlib.Path."
        )

    if hasattr(
        sqlite3.Connection,
        "autocommit",
    ):
        connection = sqlite3.connect(
            path,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            autocommit=True,
        )

        if connection.autocommit is not True:
            connection.close()
            raise LedgerIntegrityError(
                "SQLite native autocommit was not enabled."
            )

    else:
        connection = sqlite3.connect(
            path,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            isolation_level=None,
        )

        if connection.isolation_level is not None:
            connection.close()
            raise LedgerIntegrityError(
                "SQLite native autocommit was not enabled."
            )

    try:
        if connection.in_transaction:
            raise LedgerIntegrityError(
                "Connection unexpectedly opened in a transaction."
            )

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        if (
            connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]
            != 1
        ):
            raise LedgerIntegrityError(
                "Foreign-key enforcement is unavailable."
            )

        connection.execute(
            "PRAGMA trusted_schema = OFF"
        )

        if (
            connection.execute(
                "PRAGMA trusted_schema"
            ).fetchone()[0]
            != 0
        ):
            raise LedgerIntegrityError(
                "trusted_schema could not be disabled."
            )

        connection.execute(
            "PRAGMA synchronous = FULL"
        )

        if (
            connection.execute(
                "PRAGMA synchronous"
            ).fetchone()[0]
            != 2
        ):
            raise LedgerIntegrityError(
                "SQLite synchronous mode is not FULL."
            )

        connection.execute(
            f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}"
        )

        if (
            connection.execute(
                "PRAGMA busy_timeout"
            ).fetchone()[0]
            != _BUSY_TIMEOUT_MS
        ):
            raise LedgerIntegrityError(
                "SQLite busy timeout is not configured."
            )

    except BaseException:
        connection.close()
        raise

    return connection


def _ensure_wal(
    connection: sqlite3.Connection,
) -> None:
    """Enable and verify WAL outside a transaction."""

    if connection.in_transaction:
        raise LedgerIntegrityError(
            "WAL mode cannot be configured inside a transaction."
        )

    mode = connection.execute(
        "PRAGMA journal_mode = WAL"
    ).fetchone()[0]

    if str(mode).lower() != "wal":
        raise LedgerIntegrityError(
            "SQLite journal mode is not WAL."
        )

    connection.execute(
        "PRAGMA synchronous = FULL"
    )

    if (
        connection.execute(
            "PRAGMA synchronous"
        ).fetchone()[0]
        != 2
    ):
        raise LedgerIntegrityError(
            "SQLite synchronous mode changed from FULL."
        )


@contextmanager
def _immediate_transaction(
    connection: sqlite3.Connection,
) -> Iterator[None]:
    """Run one explicit BEGIN IMMEDIATE transaction."""

    if connection.in_transaction:
        raise LedgerIntegrityError(
            "Nested ledger write transactions are not supported."
        )

    connection.execute(
        "BEGIN IMMEDIATE"
    )

    try:
        yield

    except BaseException:
        if connection.in_transaction:
            connection.execute(
                "ROLLBACK"
            )

        raise

    try:
        connection.execute(
            "COMMIT"
        )

    except BaseException:
        if connection.in_transaction:
            connection.execute(
                "ROLLBACK"
            )

        raise
