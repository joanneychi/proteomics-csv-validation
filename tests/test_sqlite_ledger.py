"""Tests for the SQLite lifecycle-ledger infrastructure."""

from __future__ import annotations

import ast
from hashlib import sha256
from importlib import resources
from pathlib import Path
import sqlite3

import pytest

from proteomics_csv_validation.infrastructure.sqlite import (
    MIGRATION_V1_SHA256,
    SCHEMA_VERSION,
    LedgerSchemaError,
    backup_ledger,
    initialize_ledger,
    verify_ledger,
)
from proteomics_csv_validation.infrastructure.sqlite.connection import (
    _connect,
    _immediate_transaction,
)


UTC = "2026-08-28T00:00:00.000000Z"


def _workspace(
    connection: sqlite3.Connection,
    workspace_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO workspace(
            workspace_id,
            created_at
        )
        VALUES (?, ?)
        """,
        (
            workspace_id,
            UTC,
        ),
    )


def _configuration(
    connection: sqlite3.Connection,
    configuration_id: str,
    workspace_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO run_configuration(
            configuration_id,
            workspace_id,
            canonical_json,
            sha256,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            configuration_id,
            workspace_id,
            "{}",
            "a" * 64,
            UTC,
        ),
    )


def _run(
    connection: sqlite3.Connection,
    run_id: str,
    workspace_id: str,
    configuration_id: str,
) -> None:
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
            UTC,
            UTC,
        ),
    )


def _succeed(
    connection: sqlite3.Connection,
    run_id: str,
) -> None:
    connection.execute(
        """
        UPDATE analysis_run
        SET
            status = 'RUNNING',
            started_at = ?
        WHERE run_id = ?
        """,
        (
            UTC,
            run_id,
        ),
    )

    connection.execute(
        """
        UPDATE analysis_run
        SET
            status = 'SUCCEEDED',
            finished_at = ?
        WHERE run_id = ?
        """,
        (
            UTC,
            run_id,
        ),
    )


def test_migration_resource_matches_frozen_schema() -> None:
    """The packaged SQL bytes remain the frozen hardened schema."""

    raw = (
        resources.files(
            "proteomics_csv_validation.infrastructure.sqlite"
        )
        .joinpath(
            "migrations"
        )
        .joinpath(
            "001_initial_ledger.sql"
        )
        .read_bytes()
    )

    assert sha256(
        raw
    ).hexdigest() == MIGRATION_V1_SHA256

    assert MIGRATION_V1_SHA256 == (
        "ff3e6b1bd24db0204b5d3318c767c481"
        "086796fbe69ac2dae725e4d7f998eaf5"
    )


def test_connection_policy_uses_native_autocommit(
    tmp_path: Path,
) -> None:
    """Connections apply the frozen SQLite policy."""

    connection = _connect(
        tmp_path / "policy.sqlite"
    )

    try:
        assert not connection.in_transaction

        if hasattr(
            sqlite3.Connection,
            "autocommit",
        ):
            assert connection.autocommit is True
        else:
            assert connection.isolation_level is None

        assert connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0] == 1

        assert connection.execute(
            "PRAGMA trusted_schema"
        ).fetchone()[0] == 0

        assert connection.execute(
            "PRAGMA synchronous"
        ).fetchone()[0] == 2

        assert connection.execute(
            "PRAGMA busy_timeout"
        ).fetchone()[0] == 5000

    finally:
        connection.close()


def test_initialize_fresh_ledger(
    tmp_path: Path,
) -> None:
    """Fresh initialization installs and verifies schema version 1."""

    path = tmp_path / "workspace.sqlite"

    state = initialize_ledger(
        path
    )

    assert state.created is True
    assert state.schema_version == SCHEMA_VERSION
    assert state.migration_sha256 == MIGRATION_V1_SHA256

    verified = verify_ledger(
        path
    )

    assert verified.created is False

    connection = _connect(
        path
    )

    try:
        objects = connection.execute(
            """
            SELECT type, name
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

        tables = {
            row[1]
            for row in objects
            if row[0] == "table"
        }

        assert len(
            objects
        ) == 42

        assert tables == {
            "analysis_run",
            "execution_event",
            "export_attempt",
            "review_draft",
            "run_artifact",
            "run_configuration",
            "schema_migration",
            "workspace",
        }

        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 1

        assert connection.execute(
            "PRAGMA journal_mode"
        ).fetchone()[0].lower() == "wal"

    finally:
        connection.close()


def test_initialize_is_idempotent(
    tmp_path: Path,
) -> None:
    """Reopening schema version 1 verifies rather than remigrates."""

    path = tmp_path / "workspace.sqlite"

    first = initialize_ledger(
        path
    )

    second = initialize_ledger(
        path
    )

    assert first.created is True
    assert second.created is False

    connection = _connect(
        path
    )

    try:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM schema_migration
            """
        ).fetchone()[0] == 1

    finally:
        connection.close()


def test_initialize_rejects_unversioned_nonempty_database(
    tmp_path: Path,
) -> None:
    """Unknown preexisting schema is never claimed as ledger version 1."""

    path = tmp_path / "unknown.sqlite"

    connection = sqlite3.connect(
        path
    )

    try:
        connection.execute(
            "CREATE TABLE unrelated(id INTEGER PRIMARY KEY)"
        )
        connection.commit()

    finally:
        connection.close()

    with pytest.raises(
        LedgerSchemaError,
    ):
        initialize_ledger(
            path
        )


def test_initialize_rejects_newer_schema(
    tmp_path: Path,
) -> None:
    """A database newer than the implemented migration is refused."""

    path = tmp_path / "newer.sqlite"

    connection = sqlite3.connect(
        path
    )

    try:
        connection.execute(
            "PRAGMA user_version = 2"
        )
        connection.commit()

    finally:
        connection.close()

    with pytest.raises(
        LedgerSchemaError,
    ):
        initialize_ledger(
            path
        )


def test_immediate_transaction_rolls_back(
    tmp_path: Path,
) -> None:
    """Failed infrastructure writes roll back explicitly."""

    path = tmp_path / "workspace.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        with pytest.raises(
            RuntimeError,
        ):
            with _immediate_transaction(
                connection
            ):
                _workspace(
                    connection,
                    "workspace-rollback",
                )

                raise RuntimeError(
                    "intentional rollback"
                )

        assert not connection.in_transaction

        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM workspace
            WHERE workspace_id = 'workspace-rollback'
            """
        ).fetchone()[0] == 0

    finally:
        connection.close()


def test_backup_preserves_verified_ledger(
    tmp_path: Path,
) -> None:
    """SQLite backup preserves committed ledger state and schema identity."""

    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backup.sqlite"

    initialize_ledger(
        source
    )

    connection = _connect(
        source
    )

    try:
        with _immediate_transaction(
            connection
        ):
            _workspace(
                connection,
                "workspace-1",
            )

    finally:
        connection.close()

    state = backup_ledger(
        source,
        destination,
    )

    assert state.schema_version == 1
    assert state.migration_sha256 == MIGRATION_V1_SHA256

    backup_connection = _connect(
        destination
    )

    try:
        assert backup_connection.execute(
            """
            SELECT COUNT(*)
            FROM workspace
            WHERE workspace_id = 'workspace-1'
            """
        ).fetchone()[0] == 1

        assert backup_connection.execute(
            "PRAGMA integrity_check"
        ).fetchall() == [
            ("ok",)
        ]

        assert backup_connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

    finally:
        backup_connection.close()


def test_draft_revision_and_snapshot_guards(
    tmp_path: Path,
) -> None:
    """Draft and immutable configuration revision linkage is enforced."""

    path = tmp_path / "workspace.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        _workspace(
            connection,
            "workspace-1",
        )

        with pytest.raises(
            sqlite3.IntegrityError,
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
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "draft-invalid",
                    "workspace-1",
                    2,
                    "{}",
                    "a" * 64,
                    UTC,
                    UTC,
                ),
            )

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
                "draft-1",
                "workspace-1",
                "{}",
                "a" * 64,
                UTC,
                UTC,
            ),
        )

        connection.execute(
            """
            UPDATE review_draft
            SET
                revision = 2,
                configuration_sha256 = ?,
                updated_at = ?
            WHERE draft_id = 'draft-1'
            """,
            (
                "b" * 64,
                UTC,
            ),
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
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
                    "config-stale",
                    "workspace-1",
                    "draft-1",
                    1,
                    "{}",
                    "c" * 64,
                    UTC,
                ),
            )

    finally:
        connection.close()


def test_run_lifecycle_guards(
    tmp_path: Path,
) -> None:
    """Run insertion, transition, terminal, and deletion guards hold."""

    path = tmp_path / "workspace.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        _workspace(
            connection,
            "workspace-1",
        )

        _configuration(
            connection,
            "config-1",
            "workspace-1",
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO analysis_run(
                    run_id,
                    workspace_id,
                    configuration_id,
                    status,
                    created_at,
                    queued_at,
                    started_at
                )
                VALUES (?, ?, ?, 'QUEUED', ?, ?, ?)
                """,
                (
                    "run-invalid",
                    "workspace-1",
                    "config-1",
                    UTC,
                    UTC,
                    UTC,
                ),
            )

        _run(
            connection,
            "run-1",
            "workspace-1",
            "config-1",
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE analysis_run
                SET
                    status = 'INTERRUPTED',
                    finished_at = ?
                WHERE run_id = 'run-1'
                """,
                (
                    UTC,
                ),
            )

        _succeed(
            connection,
            "run-1",
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE analysis_run
                SET cancel_requested_at = ?
                WHERE run_id = 'run-1'
                """,
                (
                    UTC,
                ),
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                DELETE FROM analysis_run
                WHERE run_id = 'run-1'
                """
            )

    finally:
        connection.close()


def test_export_artifact_relationship_guards(
    tmp_path: Path,
) -> None:
    """Export-linked artifacts require matching successful publication."""

    path = tmp_path / "workspace.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        _workspace(
            connection,
            "workspace-1",
        )

        for number in (
            1,
            2,
        ):
            _configuration(
                connection,
                f"config-{number}",
                "workspace-1",
            )

            _run(
                connection,
                f"run-{number}",
                "workspace-1",
                f"config-{number}",
            )

            _succeed(
                connection,
                f"run-{number}",
            )

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
                "export-1",
                "run-1",
                "REVIEW_HTML",
                "exports/review.html",
                UTC,
            ),
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO run_artifact(
                    artifact_id,
                    run_id,
                    export_attempt_id,
                    kind,
                    relative_path,
                    sha256,
                    byte_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "artifact-too-early",
                    "run-1",
                    "export-1",
                    "REVIEW_HTML",
                    "exports/review.html",
                    "d" * 64,
                    10,
                    UTC,
                ),
            )

        connection.execute(
            """
            UPDATE export_attempt
            SET
                status = 'SUCCEEDED',
                finished_at = ?
            WHERE export_attempt_id = 'export-1'
            """,
            (
                UTC,
            ),
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO run_artifact(
                    artifact_id,
                    run_id,
                    export_attempt_id,
                    kind,
                    relative_path,
                    sha256,
                    byte_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "artifact-cross-run",
                    "run-2",
                    "export-1",
                    "REVIEW_HTML",
                    "exports/review.html",
                    "e" * 64,
                    10,
                    UTC,
                ),
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO run_artifact(
                    artifact_id,
                    run_id,
                    export_attempt_id,
                    kind,
                    relative_path,
                    sha256,
                    byte_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "artifact-kind-mismatch",
                    "run-1",
                    "export-1",
                    "REVIEW_PDF",
                    "exports/review.html",
                    "e" * 64,
                    10,
                    UTC,
                ),
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO run_artifact(
                    artifact_id,
                    run_id,
                    export_attempt_id,
                    kind,
                    relative_path,
                    sha256,
                    byte_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "artifact-path-mismatch",
                    "run-1",
                    "export-1",
                    "REVIEW_HTML",
                    "exports/wrong.html",
                    "e" * 64,
                    10,
                    UTC,
                ),
            )

        connection.execute(
            """
            INSERT INTO run_artifact(
                artifact_id,
                run_id,
                export_attempt_id,
                kind,
                relative_path,
                sha256,
                byte_count,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "artifact-valid",
                "run-1",
                "export-1",
                "REVIEW_HTML",
                "exports/review.html",
                "f" * 64,
                10,
                UTC,
            ),
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE export_attempt
                SET finished_at = ?
                WHERE export_attempt_id = 'export-1'
                """,
                (
                    "2026-08-28T00:00:01.000000Z",
                ),
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                DELETE FROM export_attempt
                WHERE export_attempt_id = 'export-1'
                """
            )

    finally:
        connection.close()


def test_sha_and_migration_contiguity_guards(
    tmp_path: Path,
) -> None:
    """Frozen SHA domain and migration-sequence constraints remain active."""

    path = tmp_path / "workspace.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        _workspace(
            connection,
            "workspace-1",
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO run_configuration(
                    configuration_id,
                    workspace_id,
                    canonical_json,
                    sha256,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "bad-sha",
                    "workspace-1",
                    "{}",
                    "z" * 64,
                    UTC,
                ),
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
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
                    3,
                    "skip-version-2",
                    "a" * 64,
                    UTC,
                ),
            )

    finally:
        connection.close()


def test_persistent_run_and_export_state_guards(
    tmp_path: Path,
) -> None:
    """Lifecycle status and timestamp/error state remain consistent."""

    path = tmp_path / "persistent-state.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        _workspace(
            connection,
            "workspace-state",
        )

        _configuration(
            connection,
            "config-queued",
            "workspace-state",
        )

        _run(
            connection,
            "run-queued",
            "workspace-state",
            "config-queued",
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE analysis_run
                SET started_at = ?
                WHERE run_id = 'run-queued'
                """,
                (
                    UTC,
                ),
            )

        _configuration(
            connection,
            "config-export",
            "workspace-state",
        )

        _run(
            connection,
            "run-export",
            "workspace-state",
            "config-export",
        )

        _succeed(
            connection,
            "run-export",
        )

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
                "export-state",
                "run-export",
                "REVIEW_HTML",
                "exports/state.html",
                UTC,
            ),
        )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE export_attempt
                SET finished_at = ?
                WHERE export_attempt_id = 'export-state'
                """,
                (
                    UTC,
                ),
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE export_attempt
                SET
                    error_code = 'WRITE_FAILED',
                    error_message = 'probe'
                WHERE export_attempt_id = 'export-state'
                """
            )

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                UPDATE export_attempt
                SET
                    status = 'SUCCEEDED',
                    finished_at = ?,
                    error_code = 'SHOULD_NOT_EXIST'
                WHERE export_attempt_id = 'export-state'
                """,
                (
                    UTC,
                ),
            )

        connection.execute(
            """
            UPDATE export_attempt
            SET
                status = 'SUCCEEDED',
                finished_at = ?
            WHERE export_attempt_id = 'export-state'
            """,
            (
                UTC,
            ),
        )

        row = connection.execute(
            """
            SELECT
                status,
                finished_at,
                error_code,
                error_message
            FROM export_attempt
            WHERE export_attempt_id = 'export-state'
            """
        ).fetchone()

        assert row == (
            "SUCCEEDED",
            UTC,
            None,
            None,
        )

    finally:
        connection.close()


def test_verify_rejects_same_name_schema_definition_tamper(
    tmp_path: Path,
) -> None:
    """Verification rejects a same-name replacement schema object."""

    path = tmp_path / "tampered.sqlite"

    initialize_ledger(
        path
    )

    connection = _connect(
        path
    )

    try:
        connection.execute(
            """
            DROP TRIGGER analysis_run_no_delete
            """
        )

        connection.execute(
            """
            CREATE TRIGGER analysis_run_no_delete
            BEFORE DELETE ON analysis_run
            BEGIN
                SELECT 1;
            END
            """
        )

        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0] == 42

        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchall() == [
            ("ok",)
        ]

        assert connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

    finally:
        connection.close()

    with pytest.raises(
        LedgerSchemaError,
        match="schema definition identity",
    ):
        verify_ledger(
            path
        )


def test_infrastructure_import_boundaries() -> None:
    """SQLite infrastructure remains isolated from higher application layers."""

    root = Path(
        __file__
    ).resolve().parents[1]

    package = (
        root
        / "src"
        / "proteomics_csv_validation"
    )

    infrastructure = (
        package
        / "infrastructure"
    )

    forbidden_from_infrastructure = (
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.application",
        "proteomics_csv_validation.cli",
        "proteomics_csv_validation.pipeline",
        "proteomics_csv_validation.profiles",
        "proteomics_csv_validation.validators",
        "proteomics_csv_validation.web",
    )

    for path in infrastructure.rglob(
        "*.py"
    ):
        tree = ast.parse(
            path.read_text(
                encoding="utf-8"
            ),
            filename=str(path),
        )

        modules = set()

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

        for module in modules:
            assert not module.startswith(
                forbidden_from_infrastructure
            ), (
                path,
                module,
            )

    for path in package.rglob(
        "*.py"
    ):
        if "infrastructure" in path.parts:
            continue

        tree = ast.parse(
            path.read_text(
                encoding="utf-8"
            ),
            filename=str(path),
        )

        for node in ast.walk(
            tree
        ):
            if isinstance(
                node,
                ast.ImportFrom,
            ) and node.module:
                assert not node.module.startswith(
                    "proteomics_csv_validation.infrastructure"
                ), (
                    path,
                    node.module,
                )

            if isinstance(
                node,
                ast.Import,
            ):
                for alias in node.names:
                    assert not alias.name.startswith(
                        "proteomics_csv_validation.infrastructure"
                    ), (
                        path,
                        alias.name,
                    )
