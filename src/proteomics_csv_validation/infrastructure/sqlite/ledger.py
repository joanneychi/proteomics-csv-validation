"""SQLite ledger schema initialization and integrity operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib import resources
from pathlib import Path
import sqlite3

from proteomics_csv_validation.infrastructure.sqlite.connection import (
    _connect,
    _ensure_wal,
    _immediate_transaction,
)
from proteomics_csv_validation.infrastructure.sqlite.errors import (
    LedgerIntegrityError,
    LedgerSchemaError,
)


SCHEMA_VERSION = 1

MIGRATION_V1_NAME = (
    "initial-ledger-lifecycle-spine"
)

MIGRATION_V1_SHA256 = (
    "ff3e6b1bd24db0204b5d3318c767c481"
    "086796fbe69ac2dae725e4d7f998eaf5"
)

_MIGRATION_FILE = (
    "001_initial_ledger.sql"
)

_STATEMENT_BOUNDARY = (
    "\n\n-- statement boundary --\n\n"
)

_EXPECTED_STATEMENT_COUNT = 42
_EXPECTED_SCHEMA_OBJECT_COUNT = 42

_EXPECTED_TABLES = {
    "analysis_run",
    "execution_event",
    "export_attempt",
    "review_draft",
    "run_artifact",
    "run_configuration",
    "schema_migration",
    "workspace",
}


@dataclass(
    frozen=True,
    slots=True,
)
class LedgerState:
    """Verified ledger initialization state."""

    schema_version: int
    migration_sha256: str
    created: bool


def _utc_now() -> str:
    """Return the canonical UTC timestamp representation."""

    return (
        datetime.now(
            timezone.utc
        )
        .isoformat(
            timespec="microseconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )


def _migration_bytes() -> bytes:
    """Load and authenticate the frozen version-1 migration."""

    resource = (
        resources.files(
            "proteomics_csv_validation.infrastructure.sqlite"
        )
        .joinpath(
            "migrations"
        )
        .joinpath(
            _MIGRATION_FILE
        )
    )

    raw = resource.read_bytes()

    observed = sha256(
        raw
    ).hexdigest()

    if observed != MIGRATION_V1_SHA256:
        raise LedgerSchemaError(
            "Ledger migration resource identity mismatch."
        )

    if raw.startswith(
        b"\xef\xbb\xbf"
    ):
        raise LedgerSchemaError(
            "Ledger migration resource must not contain a UTF-8 BOM."
        )

    if not raw.endswith(
        b"\n"
    ):
        raise LedgerSchemaError(
            "Ledger migration resource must end with LF."
        )

    if b"\r\n" in raw:
        raise LedgerSchemaError(
            "Ledger migration resource must use LF line endings."
        )

    return raw


def _migration_statements() -> tuple[str, ...]:
    """Return the authenticated migration as individual statements."""

    text = _migration_bytes().decode(
        "utf-8"
    )

    statements = tuple(
        statement.strip()
        for statement in text.split(
            _STATEMENT_BOUNDARY
        )
        if statement.strip()
    )

    if len(
        statements
    ) != _EXPECTED_STATEMENT_COUNT:
        raise LedgerSchemaError(
            "Ledger migration statement count mismatch."
        )

    return statements


def _user_version(
    connection: sqlite3.Connection,
) -> int:
    return int(
        connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
    )


def _schema_definitions(
    connection: sqlite3.Connection,
) -> tuple[
    tuple[
        str,
        str,
        str,
        str | None,
    ],
    ...,
]:
    """Return the application-defined SQLite schema."""

    rows = connection.execute(
        """
        SELECT
            type,
            name,
            tbl_name,
            sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()

    return tuple(
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            (
                None
                if row[3] is None
                else str(row[3])
            ),
        )
        for row in rows
    )


def _expected_schema_definitions() -> tuple[
    tuple[
        str,
        str,
        str,
        str | None,
    ],
    ...,
]:
    """Build the expected schema from the authenticated migration."""

    connection = _connect(
        Path(":memory:")
    )

    try:
        with _immediate_transaction(
            connection
        ):
            for statement in _migration_statements():
                connection.execute(
                    statement
                )

        return _schema_definitions(
            connection
        )

    finally:
        connection.close()


def _schema_objects(
    connection: sqlite3.Connection,
) -> tuple[
    tuple[str, str],
    ...,
]:
    return tuple(
        (
            object_type,
            name,
        )
        for (
            object_type,
            name,
            _table_name,
            _sql,
        ) in _schema_definitions(
            connection
        )
    )


def _verify_migration_identity(
    connection: sqlite3.Connection,
) -> None:
    try:
        rows = connection.execute(
            """
            SELECT
                version,
                name,
                migration_sha256
            FROM schema_migration
            ORDER BY version
            """
        ).fetchall()

    except sqlite3.DatabaseError as exc:
        raise LedgerSchemaError(
            "Ledger migration history is unavailable."
        ) from exc

    expected = [
        (
            SCHEMA_VERSION,
            MIGRATION_V1_NAME,
            MIGRATION_V1_SHA256,
        )
    ]

    if rows != expected:
        raise LedgerSchemaError(
            "Ledger migration history identity mismatch."
        )


def _verify_connection(
    connection: sqlite3.Connection,
) -> None:
    if _user_version(
        connection
    ) != SCHEMA_VERSION:
        raise LedgerSchemaError(
            "Ledger user_version does not match the supported schema."
        )

    _verify_migration_identity(
        connection
    )

    observed_schema = _schema_definitions(
        connection
    )

    expected_schema = _expected_schema_definitions()

    if observed_schema != expected_schema:
        raise LedgerSchemaError(
            "Ledger schema definition identity mismatch."
        )

    objects = tuple(
        (
            object_type,
            name,
        )
        for (
            object_type,
            name,
            _table_name,
            _sql,
        ) in observed_schema
    )

    if len(
        objects
    ) != _EXPECTED_SCHEMA_OBJECT_COUNT:
        raise LedgerSchemaError(
            "Ledger schema object count mismatch."
        )

    tables = {
        name
        for object_type, name
        in objects
        if object_type == "table"
    }

    if tables != _EXPECTED_TABLES:
        raise LedgerSchemaError(
            "Ledger table set mismatch."
        )

    journal_mode = connection.execute(
        "PRAGMA journal_mode"
    ).fetchone()[0]

    if str(
        journal_mode
    ).lower() != "wal":
        raise LedgerIntegrityError(
            "Ledger journal mode is not WAL."
        )

    if (
        connection.execute(
            "PRAGMA integrity_check"
        ).fetchall()
        != [
            ("ok",)
        ]
    ):
        raise LedgerIntegrityError(
            "Ledger integrity_check failed."
        )

    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if foreign_key_errors:
        raise LedgerIntegrityError(
            "Ledger foreign_key_check failed."
        )


def _apply_schema_v1(
    connection: sqlite3.Connection,
) -> None:
    statements = _migration_statements()

    with _immediate_transaction(
        connection
    ):
        for statement in statements:
            connection.execute(
                statement
            )

        connection.execute(
            """
            INSERT INTO schema_migration(
                version,
                name,
                migration_sha256,
                applied_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                SCHEMA_VERSION,
                MIGRATION_V1_NAME,
                MIGRATION_V1_SHA256,
                _utc_now(),
            ),
        )

        connection.execute(
            "PRAGMA user_version = 1"
        )


def initialize_ledger(
    path: Path,
) -> LedgerState:
    """Create or verify the supported local ledger schema."""

    if not isinstance(
        path,
        Path,
    ):
        raise TypeError(
            "path must be a pathlib.Path."
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = _connect(
        path
    )

    created = False

    try:
        version = _user_version(
            connection
        )

        objects = _schema_objects(
            connection
        )

        if version == 0:
            if objects:
                raise LedgerSchemaError(
                    "Refusing to initialize a nonempty unversioned database."
                )

            _ensure_wal(
                connection
            )

            _apply_schema_v1(
                connection
            )

            created = True

        elif version == SCHEMA_VERSION:
            _verify_migration_identity(
                connection
            )

            _ensure_wal(
                connection
            )

        else:
            raise LedgerSchemaError(
                "Ledger schema version is unsupported."
            )

        _verify_connection(
            connection
        )

    finally:
        connection.close()

    return LedgerState(
        schema_version=SCHEMA_VERSION,
        migration_sha256=MIGRATION_V1_SHA256,
        created=created,
    )


def verify_ledger(
    path: Path,
) -> LedgerState:
    """Verify one existing supported ledger without migrating it."""

    if not isinstance(
        path,
        Path,
    ):
        raise TypeError(
            "path must be a pathlib.Path."
        )

    if not path.is_file():
        raise LedgerSchemaError(
            "Ledger database does not exist."
        )

    connection = _connect(
        path
    )

    try:
        _verify_connection(
            connection
        )

    finally:
        connection.close()

    return LedgerState(
        schema_version=SCHEMA_VERSION,
        migration_sha256=MIGRATION_V1_SHA256,
        created=False,
    )


def _remove_database_files(
    path: Path,
) -> None:
    for suffix in (
        "",
        "-wal",
        "-shm",
    ):
        candidate = Path(
            str(path) + suffix
        )

        if candidate.exists():
            candidate.unlink()


def backup_ledger(
    source: Path,
    destination: Path,
) -> LedgerState:
    """Create and verify one SQLite-consistent ledger backup."""

    if not isinstance(
        source,
        Path,
    ):
        raise TypeError(
            "source must be a pathlib.Path."
        )

    if not isinstance(
        destination,
        Path,
    ):
        raise TypeError(
            "destination must be a pathlib.Path."
        )

    if source == destination:
        raise ValueError(
            "source and destination must be distinct."
        )

    verify_ledger(
        source
    )

    for suffix in (
        "",
        "-wal",
        "-shm",
    ):
        if Path(
            str(destination) + suffix
        ).exists():
            raise FileExistsError(
                "Ledger backup destination already exists."
            )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_connection = _connect(
        source
    )

    destination_connection = _connect(
        destination
    )

    try:
        source_connection.backup(
            destination_connection
        )

        _ensure_wal(
            destination_connection
        )

    except BaseException:
        destination_connection.close()
        source_connection.close()

        _remove_database_files(
            destination
        )

        raise

    destination_connection.close()
    source_connection.close()

    return verify_ledger(
        destination
    )
