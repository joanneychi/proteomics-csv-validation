CREATE TABLE schema_migration (
    version INTEGER PRIMARY KEY
        CHECK (version >= 1),
    name TEXT NOT NULL
        CHECK (length(name) > 0),
    migration_sha256 TEXT NOT NULL
        CHECK (
            length(migration_sha256) = 64
            AND migration_sha256 =
                lower(migration_sha256)
            AND migration_sha256
                NOT GLOB '*[^0-9a-f]*'
        ),
    applied_at TEXT NOT NULL
        CHECK (length(applied_at) > 0)
)

-- statement boundary --

CREATE TABLE workspace (
        workspace_id TEXT PRIMARY KEY
            CHECK (length(workspace_id) > 0),
        created_at TEXT NOT NULL
            CHECK (length(created_at) > 0)
    )

-- statement boundary --

CREATE TABLE review_draft (
    draft_id TEXT PRIMARY KEY
        CHECK (length(draft_id) > 0),
    workspace_id TEXT NOT NULL
        REFERENCES workspace(workspace_id)
        ON DELETE CASCADE,
    revision INTEGER NOT NULL
        CHECK (revision >= 1),
    configuration_json TEXT NOT NULL,
    configuration_sha256 TEXT NOT NULL
        CHECK (
            length(configuration_sha256) = 64
            AND configuration_sha256 =
                lower(configuration_sha256)
            AND configuration_sha256
                NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)

-- statement boundary --

CREATE TABLE run_configuration (
    configuration_id TEXT PRIMARY KEY
        CHECK (length(configuration_id) > 0),
    workspace_id TEXT NOT NULL
        REFERENCES workspace(workspace_id)
        ON DELETE RESTRICT,
    source_draft_id TEXT
        REFERENCES review_draft(draft_id)
        ON DELETE RESTRICT,
    source_draft_revision INTEGER
        CHECK (
            source_draft_revision IS NULL
            OR source_draft_revision >= 1
        ),
    canonical_json TEXT NOT NULL,
    sha256 TEXT NOT NULL
        CHECK (
            length(sha256) = 64
            AND sha256 = lower(sha256)
            AND sha256
                NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL,
    CHECK (
        (
            source_draft_id IS NULL
            AND source_draft_revision IS NULL
        )
        OR
        (
            source_draft_id IS NOT NULL
            AND source_draft_revision IS NOT NULL
        )
    )
)

-- statement boundary --

CREATE TABLE analysis_run (
        run_id TEXT PRIMARY KEY
            CHECK (length(run_id) > 0),
        workspace_id TEXT NOT NULL
            REFERENCES workspace(workspace_id)
            ON DELETE RESTRICT,
        configuration_id TEXT NOT NULL UNIQUE
            REFERENCES run_configuration(configuration_id)
            ON DELETE RESTRICT,
        status TEXT NOT NULL
            CHECK (
                status IN (
                    'QUEUED',
                    'RUNNING',
                    'SUCCEEDED',
                    'FAILED',
                    'CANCELLED',
                    'INTERRUPTED'
                )
            ),
        created_at TEXT NOT NULL,
        queued_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        cancel_requested_at TEXT
    )

-- statement boundary --

CREATE TABLE execution_event (
        run_id TEXT NOT NULL
            REFERENCES analysis_run(run_id)
            ON DELETE RESTRICT,
        sequence INTEGER NOT NULL
            CHECK (sequence >= 1),
        event_type TEXT NOT NULL
            CHECK (length(event_type) > 0),
        occurred_at TEXT NOT NULL,
        detail_json TEXT,
        PRIMARY KEY (run_id, sequence)
    )

-- statement boundary --

CREATE TABLE export_attempt (
    export_attempt_id TEXT PRIMARY KEY
        CHECK (length(export_attempt_id) > 0),
    run_id TEXT NOT NULL
        REFERENCES analysis_run(run_id)
        ON DELETE RESTRICT,
    artifact_kind TEXT NOT NULL
        CHECK (length(artifact_kind) > 0),
    target_relative_path TEXT NOT NULL
        CHECK (length(target_relative_path) > 0),
    status TEXT NOT NULL
        CHECK (
            status IN (
                'STARTED',
                'SUCCEEDED',
                'FAILED'
            )
        ),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT,
    UNIQUE (
        export_attempt_id,
        run_id,
        artifact_kind,
        target_relative_path
    )
)

-- statement boundary --

CREATE TABLE run_artifact (
    artifact_id TEXT PRIMARY KEY
        CHECK (length(artifact_id) > 0),
    run_id TEXT NOT NULL
        REFERENCES analysis_run(run_id)
        ON DELETE RESTRICT,
    export_attempt_id TEXT,
    kind TEXT NOT NULL
        CHECK (length(kind) > 0),
    schema_id TEXT,
    schema_version TEXT,
    relative_path TEXT NOT NULL
        CHECK (length(relative_path) > 0),
    sha256 TEXT NOT NULL
        CHECK (
            length(sha256) = 64
            AND sha256 = lower(sha256)
            AND sha256
                NOT GLOB '*[^0-9a-f]*'
        ),
    byte_count INTEGER NOT NULL
        CHECK (byte_count >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (
        export_attempt_id,
        run_id,
        kind,
        relative_path
    )
    REFERENCES export_attempt(
        export_attempt_id,
        run_id,
        artifact_kind,
        target_relative_path
    )
    ON DELETE RESTRICT
)

-- statement boundary --

CREATE INDEX analysis_run_workspace_status_idx
    ON analysis_run(workspace_id, status)

-- statement boundary --

CREATE INDEX execution_event_run_idx
    ON execution_event(run_id, sequence)

-- statement boundary --

CREATE INDEX run_artifact_run_kind_idx
    ON run_artifact(run_id, kind)

-- statement boundary --

CREATE TRIGGER review_draft_revision_guard
    BEFORE UPDATE ON review_draft
    BEGIN
        SELECT CASE
            WHEN NEW.draft_id IS NOT OLD.draft_id
              OR NEW.workspace_id IS NOT OLD.workspace_id
              OR NEW.created_at IS NOT OLD.created_at
            THEN RAISE(
                ABORT,
                'immutable review_draft identity'
            )
        END;

        SELECT CASE
            WHEN NEW.revision <> OLD.revision + 1
            THEN RAISE(
                ABORT,
                'review_draft revision must increment by one'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER run_configuration_workspace_guard
    BEFORE INSERT ON run_configuration
    WHEN NEW.source_draft_id IS NOT NULL
    BEGIN
        SELECT CASE
            WHEN (
                SELECT workspace_id
                FROM review_draft
                WHERE draft_id = NEW.source_draft_id
            ) IS NOT NEW.workspace_id
            THEN RAISE(
                ABORT,
                'draft/configuration workspace mismatch'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER run_configuration_no_update
    BEFORE UPDATE ON run_configuration
    BEGIN
        SELECT RAISE(
            ABORT,
            'run configuration is immutable'
        );
    END

-- statement boundary --

CREATE TRIGGER run_configuration_no_delete
    BEFORE DELETE ON run_configuration
    BEGIN
        SELECT RAISE(
            ABORT,
            'run configuration is immutable'
        );
    END

-- statement boundary --

CREATE TRIGGER analysis_run_initial_state
    BEFORE INSERT ON analysis_run
    WHEN NEW.status <> 'QUEUED'
    BEGIN
        SELECT RAISE(
            ABORT,
            'analysis run must begin QUEUED'
        );
    END

-- statement boundary --

CREATE TRIGGER analysis_run_configuration_workspace_guard
    BEFORE INSERT ON analysis_run
    BEGIN
        SELECT CASE
            WHEN (
                SELECT workspace_id
                FROM run_configuration
                WHERE configuration_id =
                    NEW.configuration_id
            ) IS NOT NEW.workspace_id
            THEN RAISE(
                ABORT,
                'run/configuration workspace mismatch'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER analysis_run_immutable_identity
    BEFORE UPDATE ON analysis_run
    WHEN
        NEW.run_id IS NOT OLD.run_id
        OR NEW.workspace_id IS NOT OLD.workspace_id
        OR NEW.configuration_id IS NOT OLD.configuration_id
        OR NEW.created_at IS NOT OLD.created_at
        OR NEW.queued_at IS NOT OLD.queued_at
    BEGIN
        SELECT RAISE(
            ABORT,
            'immutable analysis_run identity'
        );
    END

-- statement boundary --

CREATE TRIGGER analysis_run_state_transition
BEFORE UPDATE OF status ON analysis_run
WHEN NOT (
    NEW.status = OLD.status

    OR (
        OLD.status = 'QUEUED'
        AND NEW.status IN (
            'RUNNING',
            'FAILED',
            'CANCELLED'
        )
    )

    OR (
        OLD.status = 'RUNNING'
        AND NEW.status IN (
            'SUCCEEDED',
            'FAILED',
            'CANCELLED',
            'INTERRUPTED'
        )
    )
)
BEGIN
    SELECT RAISE(
        ABORT,
        'invalid analysis_run state transition'
    );
END

-- statement boundary --

CREATE TRIGGER analysis_run_timestamp_guard
    BEFORE UPDATE ON analysis_run
    BEGIN
        SELECT CASE
            WHEN NEW.status = 'QUEUED'
                 AND NEW.started_at IS NOT NULL
            THEN RAISE(
                ABORT,
                'QUEUED cannot have started_at'
            )
        END;

        SELECT CASE
            WHEN NEW.status = 'RUNNING'
                 AND NEW.started_at IS NULL
            THEN RAISE(
                ABORT,
                'RUNNING requires started_at'
            )
        END;

        SELECT CASE
            WHEN NEW.status IN (
                    'SUCCEEDED',
                    'FAILED',
                    'CANCELLED',
                    'INTERRUPTED'
                 )
                 AND NEW.finished_at IS NULL
            THEN RAISE(
                ABORT,
                'terminal state requires finished_at'
            )
        END;

        SELECT CASE
            WHEN NEW.status IN (
                    'QUEUED',
                    'RUNNING'
                 )
                 AND NEW.finished_at IS NOT NULL
            THEN RAISE(
                ABORT,
                'nonterminal run cannot have finished_at'
            )
        END;

        SELECT CASE
            WHEN NEW.status = 'SUCCEEDED'
                 AND NEW.started_at IS NULL
            THEN RAISE(
                ABORT,
                'SUCCEEDED requires started_at'
            )
        END;

        SELECT CASE
            WHEN OLD.started_at IS NOT NULL
                 AND NEW.started_at IS NOT OLD.started_at
            THEN RAISE(
                ABORT,
                'started_at is immutable once set'
            )
        END;

        SELECT CASE
            WHEN OLD.finished_at IS NOT NULL
                 AND NEW.finished_at IS NOT OLD.finished_at
            THEN RAISE(
                ABORT,
                'finished_at is immutable once set'
            )
        END;

        SELECT CASE
            WHEN OLD.cancel_requested_at IS NOT NULL
                 AND NEW.cancel_requested_at
                     IS NOT OLD.cancel_requested_at
            THEN RAISE(
                ABORT,
                'cancel request is immutable once set'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER execution_event_contiguous_sequence
    BEFORE INSERT ON execution_event
    BEGIN
        SELECT CASE
            WHEN NEW.sequence <> COALESCE(
                (
                    SELECT MAX(sequence) + 1
                    FROM execution_event
                    WHERE run_id = NEW.run_id
                ),
                1
            )
            THEN RAISE(
                ABORT,
                'execution event sequence is not contiguous'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER execution_event_no_update
    BEFORE UPDATE ON execution_event
    BEGIN
        SELECT RAISE(
            ABORT,
            'execution events are append-only'
        );
    END

-- statement boundary --

CREATE TRIGGER execution_event_no_delete
    BEFORE DELETE ON execution_event
    BEGIN
        SELECT RAISE(
            ABORT,
            'execution events are append-only'
        );
    END

-- statement boundary --

CREATE TRIGGER run_artifact_result_gate
    BEFORE INSERT ON run_artifact
    WHEN NEW.kind = 'RESULT_BUNDLE'
    BEGIN
        SELECT CASE
            WHEN (
                SELECT status
                FROM analysis_run
                WHERE run_id = NEW.run_id
            ) <> 'SUCCEEDED'
            THEN RAISE(
                ABORT,
                'result bundle requires SUCCEEDED run'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER run_artifact_no_update
    BEFORE UPDATE ON run_artifact
    BEGIN
        SELECT RAISE(
            ABORT,
            'run artifacts are immutable'
        );
    END

-- statement boundary --

CREATE TRIGGER run_artifact_no_delete
    BEFORE DELETE ON run_artifact
    BEGIN
        SELECT RAISE(
            ABORT,
            'run artifacts are immutable'
        );
    END

-- statement boundary --

CREATE TRIGGER export_attempt_initial_state
    BEFORE INSERT ON export_attempt
    WHEN NEW.status <> 'STARTED'
    BEGIN
        SELECT RAISE(
            ABORT,
            'export attempt must begin STARTED'
        );
    END

-- statement boundary --

CREATE TRIGGER export_attempt_transition
    BEFORE UPDATE OF status ON export_attempt
    WHEN NOT (
        NEW.status = OLD.status
        OR (
            OLD.status = 'STARTED'
            AND NEW.status IN (
                'SUCCEEDED',
                'FAILED'
            )
        )
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'invalid export attempt transition'
        );
    END

-- statement boundary --

CREATE TRIGGER export_attempt_identity_guard
    BEFORE UPDATE ON export_attempt
    WHEN
        NEW.export_attempt_id
            IS NOT OLD.export_attempt_id
        OR NEW.run_id IS NOT OLD.run_id
        OR NEW.artifact_kind
            IS NOT OLD.artifact_kind
        OR NEW.target_relative_path
            IS NOT OLD.target_relative_path
        OR NEW.started_at IS NOT OLD.started_at
    BEGIN
        SELECT RAISE(
            ABORT,
            'immutable export attempt identity'
        );
    END

-- statement boundary --

CREATE TRIGGER export_attempt_terminal_guard
    BEFORE UPDATE ON export_attempt
    BEGIN
        SELECT CASE
            WHEN NEW.status = 'STARTED'
                 AND (
                     NEW.finished_at IS NOT NULL
                     OR NEW.error_code IS NOT NULL
                     OR NEW.error_message IS NOT NULL
                 )
            THEN RAISE(
                ABORT,
                'STARTED export cannot contain terminal state'
            )
        END;

        SELECT CASE
            WHEN NEW.status IN (
                    'SUCCEEDED',
                    'FAILED'
                 )
                 AND NEW.finished_at IS NULL
            THEN RAISE(
                ABORT,
                'terminal export attempt requires finished_at'
            )
        END;

        SELECT CASE
            WHEN NEW.status = 'SUCCEEDED'
                 AND (
                     NEW.error_code IS NOT NULL
                     OR NEW.error_message IS NOT NULL
                 )
            THEN RAISE(
                ABORT,
                'SUCCEEDED export cannot contain error state'
            )
        END;
    END

-- statement boundary --

CREATE TRIGGER schema_migration_no_update
    BEFORE UPDATE ON schema_migration
    BEGIN
        SELECT RAISE(
            ABORT,
            'schema migration history is immutable'
        );
    END

-- statement boundary --

CREATE TRIGGER schema_migration_no_delete
    BEFORE DELETE ON schema_migration
    BEGIN
        SELECT RAISE(
            ABORT,
            'schema migration history is immutable'
        );
    END

-- statement boundary --

CREATE TRIGGER review_draft_initial_revision
BEFORE INSERT ON review_draft
WHEN NEW.revision <> 1
BEGIN
    SELECT RAISE(
        ABORT,
        'review_draft must begin at revision 1'
    );
END

-- statement boundary --

CREATE TRIGGER run_configuration_source_revision_guard
BEFORE INSERT ON run_configuration
WHEN NEW.source_draft_id IS NOT NULL
BEGIN
    SELECT CASE
        WHEN (
            SELECT revision
            FROM review_draft
            WHERE draft_id =
                NEW.source_draft_id
        ) IS NOT NEW.source_draft_revision
        THEN RAISE(
            ABORT,
            'draft/configuration revision mismatch'
        )
    END;
END

-- statement boundary --

CREATE TRIGGER analysis_run_initial_timestamp_guard
BEFORE INSERT ON analysis_run
WHEN
    NEW.started_at IS NOT NULL
    OR NEW.finished_at IS NOT NULL
    OR NEW.cancel_requested_at IS NOT NULL
BEGIN
    SELECT RAISE(
        ABORT,
        'QUEUED run must begin without lifecycle timestamps'
    );
END

-- statement boundary --

CREATE TRIGGER analysis_run_terminal_no_update
BEFORE UPDATE ON analysis_run
WHEN OLD.status IN (
    'SUCCEEDED',
    'FAILED',
    'CANCELLED',
    'INTERRUPTED'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'terminal analysis run is immutable'
    );
END

-- statement boundary --

CREATE TRIGGER analysis_run_no_delete
BEFORE DELETE ON analysis_run
BEGIN
    SELECT RAISE(
        ABORT,
        'analysis run history is immutable'
    );
END

-- statement boundary --

CREATE TRIGGER export_attempt_initial_shape
BEFORE INSERT ON export_attempt
WHEN
    NEW.finished_at IS NOT NULL
    OR NEW.error_code IS NOT NULL
    OR NEW.error_message IS NOT NULL
BEGIN
    SELECT RAISE(
        ABORT,
        'STARTED export cannot contain terminal state'
    );
END

-- statement boundary --

CREATE TRIGGER export_attempt_terminal_no_update
BEFORE UPDATE ON export_attempt
WHEN OLD.status IN (
    'SUCCEEDED',
    'FAILED'
)
BEGIN
    SELECT RAISE(
        ABORT,
        'terminal export attempt is immutable'
    );
END

-- statement boundary --

CREATE TRIGGER export_attempt_no_delete
BEFORE DELETE ON export_attempt
BEGIN
    SELECT RAISE(
        ABORT,
        'export attempt history is immutable'
    );
END

-- statement boundary --

CREATE TRIGGER run_artifact_export_success_gate
BEFORE INSERT ON run_artifact
WHEN NEW.export_attempt_id IS NOT NULL
BEGIN
    SELECT CASE
        WHEN (
            SELECT status
            FROM export_attempt
            WHERE export_attempt_id =
                NEW.export_attempt_id
        ) IS NOT 'SUCCEEDED'
        THEN RAISE(
            ABORT,
            'linked artifact requires SUCCEEDED export'
        )
    END;
END

-- statement boundary --

CREATE TRIGGER schema_migration_contiguous_insert
BEFORE INSERT ON schema_migration
WHEN NEW.version <> COALESCE(
    (
        SELECT MAX(version) + 1
        FROM schema_migration
    ),
    1
)
BEGIN
    SELECT RAISE(
        ABORT,
        'schema migration version is not contiguous'
    );
END
