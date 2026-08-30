from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path

import pytest

import proteomics_csv_validation.application.run_lifecycle as application_module
import proteomics_csv_validation.domain.run_lifecycle as domain_module
import proteomics_csv_validation.infrastructure.sqlite.run_repository as repository_module

from proteomics_csv_validation.application.run_lifecycle import (
    LedgerOperationError,
    LedgerRecordNotFoundError,
    ReviewDraftRevisionConflictError,
    RunLifecycleService,
    RunRepository,
    RunState,
    RunStateConflictError,
)

from proteomics_csv_validation.infrastructure.sqlite import (
    LedgerSchemaError,
    initialize_ledger,
)

from proteomics_csv_validation.infrastructure.sqlite.run_repository import (
    SQLiteRunRepository,
)


T0 = "2026-08-28T00:00:00.000000Z"
T1 = "2026-08-28T00:00:01.000000Z"
T2 = "2026-08-28T00:00:02.000000Z"
T3 = "2026-08-28T00:00:03.000000Z"
T4 = "2026-08-28T00:00:04.000000Z"


def _repository(
    tmp_path: Path,
) -> SQLiteRunRepository:
    path = tmp_path / "ledger.sqlite"

    initialize_ledger(
        path
    )

    return SQLiteRunRepository(
        path
    )


def _configuration(
    repository: SQLiteRunRepository,
    *,
    workspace_id: str = "workspace",
    configuration_id: str = "configuration",
) -> None:
    repository.ensure_workspace(
        workspace_id,
        created_at=T0,
    )

    repository.snapshot_configuration(
        configuration_id,
        workspace_id,
        "{}",
        created_at=T0,
    )


def _queued_run(
    repository: SQLiteRunRepository,
    *,
    workspace_id: str = "workspace",
    configuration_id: str = "configuration",
    run_id: str = "run",
):
    _configuration(
        repository,
        workspace_id=workspace_id,
        configuration_id=configuration_id,
    )

    return repository.queue_run(
        run_id,
        workspace_id,
        configuration_id,
        created_at=T0,
        queued_at=T0,
    )


def test_lifecycle_domain_has_no_outer_layer_dependency() -> None:
    path = Path(
        domain_module.__file__
    )

    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )

    imports = []

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            imports.extend(
                alias.name
                for alias in node.names
            )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if node.module is not None:
                imports.append(
                    node.module
                )

    forbidden = (
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.application",
        "proteomics_csv_validation.infrastructure",
        "proteomics_csv_validation.web",
    )

    assert not any(
        name.startswith(
            forbidden
        )
        for name in imports
    )


def test_sqlite_repository_structurally_satisfies_application_port(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    assert isinstance(
        repository,
        RunRepository,
    )


def test_application_lifecycle_has_no_infrastructure_dependency() -> None:
    path = Path(
        application_module.__file__
    )

    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )

    imports = []

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            imports.extend(
                alias.name
                for alias in node.names
            )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if node.module is not None:
                imports.append(
                    node.module
                )

    assert not any(
        name.startswith(
            "proteomics_csv_validation.infrastructure"
        )
        for name in imports
    )


def test_repository_requires_verified_ledger(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        LedgerSchemaError,
    ):
        SQLiteRunRepository(
            tmp_path / "missing.sqlite"
        )


def test_draft_revision_and_snapshot(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    repository.ensure_workspace(
        "workspace",
        created_at=T0,
    )

    first_json = '{"revision":1}'

    draft = repository.create_review_draft(
        "draft",
        "workspace",
        first_json,
        created_at=T0,
    )

    assert draft.revision == 1
    assert (
        draft.configuration_sha256
        == sha256(
            first_json.encode(
                "utf-8"
            )
        ).hexdigest()
    )

    second_json = '{"revision":2}'

    revised = repository.revise_review_draft(
        "draft",
        second_json,
        expected_revision=1,
        updated_at=T1,
    )

    assert revised.revision == 2
    assert revised.created_at == T0
    assert revised.updated_at == T1

    configuration = repository.snapshot_configuration(
        "configuration",
        "workspace",
        second_json,
        created_at=T2,
        source_draft_id="draft",
    )

    assert (
        configuration.source_draft_id
        == "draft"
    )

    assert (
        configuration.source_draft_revision
        == 2
    )

    assert (
        configuration.sha256
        == sha256(
            second_json.encode(
                "utf-8"
            )
        ).hexdigest()
    )


def test_snapshot_rejects_payload_that_differs_from_source_draft(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    repository.ensure_workspace(
        "workspace",
        created_at=T0,
    )

    repository.create_review_draft(
        "draft",
        "workspace",
        '{"declared":"draft"}',
        created_at=T0,
    )

    with pytest.raises(
        LedgerOperationError,
        match="must match",
    ):
        repository.snapshot_configuration(
            "configuration",
            "workspace",
            '{"different":"payload"}',
            created_at=T1,
            source_draft_id="draft",
        )


def test_queue_start_success_records_ordered_events(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    queued = _queued_run(
        repository
    )

    assert queued.status is RunState.QUEUED

    running = repository.start_run(
        "run",
        started_at=T1,
    )

    assert running.status is RunState.RUNNING
    assert running.started_at == T1

    succeeded = repository.complete_run(
        "run",
        RunState.SUCCEEDED,
        finished_at=T2,
    )

    assert (
        succeeded.status
        is RunState.SUCCEEDED
    )

    assert succeeded.finished_at == T2

    events = repository.list_events(
        "run"
    )

    assert [
        (
            event.sequence,
            event.event_type,
        )
        for event in events
    ] == [
        (
            1,
            "QUEUED",
        ),
        (
            2,
            "RUNNING",
        ),
        (
            3,
            "SUCCEEDED",
        ),
    ]


def test_queued_failure_is_supported(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    failed = repository.complete_run(
        "run",
        RunState.FAILED,
        finished_at=T1,
    )

    assert failed.status is RunState.FAILED
    assert failed.started_at is None

    assert [
        event.event_type
        for event in repository.list_events(
            "run"
        )
    ] == [
        "QUEUED",
        "FAILED",
    ]


def test_queued_cancellation_is_supported(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    cancelled = repository.complete_run(
        "run",
        RunState.CANCELLED,
        finished_at=T1,
    )

    assert (
        cancelled.status
        is RunState.CANCELLED
    )

    assert cancelled.started_at is None


def test_queued_interruption_is_rejected(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    with pytest.raises(
        RunStateConflictError,
    ):
        repository.complete_run(
            "run",
            RunState.INTERRUPTED,
            finished_at=T1,
        )

    assert (
        repository.get_run(
            "run"
        ).status
        is RunState.QUEUED
    )


@pytest.mark.parametrize(
    "status",
    [
        RunState.SUCCEEDED,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.INTERRUPTED,
    ],
)
def test_running_terminal_transitions(
    tmp_path: Path,
    status: RunState,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository,
        run_id=(
            "run-"
            + status.value.lower()
        ),
    )

    run_id = (
        "run-"
        + status.value.lower()
    )

    repository.start_run(
        run_id,
        started_at=T1,
    )

    terminal = repository.complete_run(
        run_id,
        status,
        finished_at=T2,
    )

    assert terminal.status is status
    assert terminal.started_at == T1
    assert terminal.finished_at == T2


def test_cancel_request_on_queued_run(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    record = repository.request_cancel(
        "run",
        requested_at=T1,
    )

    assert record.status is RunState.QUEUED
    assert record.cancel_requested_at == T1

    assert [
        event.event_type
        for event in repository.list_events(
            "run"
        )
    ] == [
        "QUEUED",
        "CANCEL_REQUESTED",
    ]


def test_cancel_requested_queued_run_cannot_start(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    repository.request_cancel(
        "run",
        requested_at=T1,
    )

    with pytest.raises(
        RunStateConflictError,
        match="cancellation",
    ):
        repository.start_run(
            "run",
            started_at=T2,
        )

    record = repository.get_run(
        "run"
    )

    assert record.status is RunState.QUEUED
    assert record.started_at is None
    assert record.cancel_requested_at == T1

    assert [
        event.event_type
        for event in repository.list_events(
            "run"
        )
    ] == [
        "QUEUED",
        "CANCEL_REQUESTED",
    ]

    cancelled = repository.complete_run(
        "run",
        RunState.CANCELLED,
        finished_at=T3,
    )

    assert (
        cancelled.status
        is RunState.CANCELLED
    )


def test_cancel_request_on_running_run(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    repository.start_run(
        "run",
        started_at=T1,
    )

    record = repository.request_cancel(
        "run",
        requested_at=T2,
    )

    assert record.status is RunState.RUNNING
    assert record.cancel_requested_at == T2

    cancelled = repository.complete_run(
        "run",
        RunState.CANCELLED,
        finished_at=T3,
    )

    assert (
        cancelled.status
        is RunState.CANCELLED
    )


def test_cancel_request_is_idempotent(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    first = repository.request_cancel(
        "run",
        requested_at=T1,
    )

    second = repository.request_cancel(
        "run",
        requested_at=T2,
    )

    assert (
        first.cancel_requested_at
        == T1
    )

    assert (
        second.cancel_requested_at
        == T1
    )

    events = repository.list_events(
        "run"
    )

    assert [
        event.event_type
        for event in events
    ].count(
        "CANCEL_REQUESTED"
    ) == 1


def test_cancel_request_on_terminal_run_is_rejected(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    repository.start_run(
        "run",
        started_at=T1,
    )

    repository.complete_run(
        "run",
        RunState.SUCCEEDED,
        finished_at=T2,
    )

    with pytest.raises(
        RunStateConflictError,
    ):
        repository.request_cancel(
            "run",
            requested_at=T3,
        )


def test_missing_run_raises(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    with pytest.raises(
        LedgerRecordNotFoundError,
    ):
        repository.get_run(
            "missing"
        )

    with pytest.raises(
        LedgerRecordNotFoundError,
    ):
        repository.start_run(
            "missing",
            started_at=T1,
        )


def test_restart_recovery_interrupts_only_running_and_is_idempotent(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    repository.ensure_workspace(
        "workspace",
        created_at=T0,
    )

    for suffix in (
        "queued",
        "running",
        "success",
        "failed",
    ):
        repository.snapshot_configuration(
            "config-" + suffix,
            "workspace",
            "{}",
            created_at=T0,
        )

        repository.queue_run(
            "run-" + suffix,
            "workspace",
            "config-" + suffix,
            created_at=T0,
            queued_at=T0,
        )

    repository.start_run(
        "run-running",
        started_at=T1,
    )

    repository.start_run(
        "run-success",
        started_at=T1,
    )

    repository.complete_run(
        "run-success",
        RunState.SUCCEEDED,
        finished_at=T2,
    )

    repository.start_run(
        "run-failed",
        started_at=T1,
    )

    repository.complete_run(
        "run-failed",
        RunState.FAILED,
        finished_at=T2,
    )

    recovered = (
        repository.recover_interrupted_runs(
            interrupted_at=T3,
        )
    )

    assert [
        record.run_id
        for record in recovered
    ] == [
        "run-running",
    ]

    assert (
        repository.get_run(
            "run-queued"
        ).status
        is RunState.QUEUED
    )

    assert (
        repository.get_run(
            "run-running"
        ).status
        is RunState.INTERRUPTED
    )

    assert (
        repository.get_run(
            "run-success"
        ).status
        is RunState.SUCCEEDED
    )

    assert (
        repository.get_run(
            "run-failed"
        ).status
        is RunState.FAILED
    )

    assert [
        event.event_type
        for event in repository.list_events(
            "run-running"
        )
    ] == [
        "QUEUED",
        "RUNNING",
        "RECOVERY_INTERRUPTED",
    ]

    assert (
        repository.recover_interrupted_runs(
            interrupted_at=T4,
        )
        == ()
    )

    assert len(
        repository.list_events(
            "run-running"
        )
    ) == 3


def test_restart_recovery_rolls_back_if_event_append_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(
        tmp_path
    )

    _queued_run(
        repository
    )

    repository.start_run(
        "run",
        started_at=T1,
    )

    def fail_event(
        *_args,
        **_kwargs,
    ):
        raise RuntimeError(
            "forced event failure"
        )

    monkeypatch.setattr(
        repository_module,
        "_append_event",
        fail_event,
    )

    with pytest.raises(
        RuntimeError,
        match="forced event failure",
    ):
        repository.recover_interrupted_runs(
            interrupted_at=T2,
        )

    assert (
        repository.get_run(
            "run"
        ).status
        is RunState.RUNNING
    )

    assert [
        event.event_type
        for event in repository.list_events(
            "run"
        )
    ] == [
        "QUEUED",
        "RUNNING",
    ]


def test_service_clock_owns_operation_timestamps(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    times = iter(
        [
            T0,
            T1,
            T2,
            T3,
        ]
    )

    service = RunLifecycleService(
        repository=repository,
        clock=lambda: next(
            times
        ),
    )

    service.ensure_workspace(
        "workspace"
    )

    configuration = (
        service.snapshot_configuration(
            "configuration",
            "workspace",
            "{}",
        )
    )

    queued = service.queue_run(
        "run",
        "workspace",
        "configuration",
    )

    running = service.start_run(
        "run"
    )

    assert configuration.created_at == T1
    assert queued.created_at == T2
    assert queued.queued_at == T2
    assert running.started_at == T3

def test_revise_review_draft_rejects_stale_expected_revision(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    repository.ensure_workspace(
        "workspace",
        created_at=T0,
    )

    repository.create_review_draft(
        "draft",
        "workspace",
        '{"revision":1}',
        created_at=T0,
    )

    first = repository.revise_review_draft(
        "draft",
        '{"revision":2}',
        expected_revision=1,
        updated_at=T1,
    )

    assert first.revision == 2

    with pytest.raises(
        ReviewDraftRevisionConflictError,
        match="expected 1, current 2",
    ):
        repository.revise_review_draft(
            "draft",
            '{"stale":true}',
            expected_revision=1,
            updated_at=T2,
        )

    current = repository.snapshot_configuration(
        "configuration",
        "workspace",
        '{"revision":2}',
        created_at=T3,
        source_draft_id="draft",
    )

    assert (
        current.source_draft_revision
        == 2
    )


def test_service_forwards_expected_revision_and_clock(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    times = iter(
        [
            T0,
            T1,
            T2,
        ]
    )

    service = RunLifecycleService(
        repository=repository,
        clock=lambda: next(
            times
        ),
    )

    service.ensure_workspace(
        "workspace"
    )

    service.create_review_draft(
        "draft",
        "workspace",
        '{"revision":1}',
    )

    revised = service.revise_review_draft(
        "draft",
        '{"revision":2}',
        expected_revision=1,
    )

    assert revised.revision == 2
    assert revised.updated_at == T2


def test_get_configuration_round_trip(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    repository.ensure_workspace(
        "workspace",
        created_at=T0,
    )

    canonical_json = (
        '{"mapping_mode":"strict",'
        '"profile_version":"0.2.0"}'
    )

    stored = (
        repository.snapshot_configuration(
            "configuration",
            "workspace",
            canonical_json,
            created_at=T1,
        )
    )

    assert (
        repository.get_configuration(
            "configuration"
        )
        == stored
    )

    service = RunLifecycleService(
        repository=repository,
        clock=lambda: T2,
    )

    assert (
        service.get_configuration(
            "configuration"
        )
        == stored
    )


def test_missing_configuration_raises(
    tmp_path: Path,
) -> None:
    repository = _repository(
        tmp_path
    )

    with pytest.raises(
        LedgerRecordNotFoundError,
        match="Run configuration does not exist",
    ):
        repository.get_configuration(
            "missing"
        )

    service = RunLifecycleService(
        repository=repository,
        clock=lambda: T0,
    )

    with pytest.raises(
        LedgerRecordNotFoundError,
        match="Run configuration does not exist",
    ):
        service.get_configuration(
            "missing"
        )


def _history_candidate_service(
    tmp_path,
    *,
    constant_time: bool = False,
):
    from proteomics_csv_validation.application.run_lifecycle import (
        RunLifecycleService,
    )
    from proteomics_csv_validation.infrastructure.sqlite import (
        initialize_ledger,
    )
    from proteomics_csv_validation.infrastructure.sqlite.run_repository import (
        SQLiteRunRepository,
    )

    database = (
        tmp_path
        / "history-ledger.sqlite3"
    )

    initialize_ledger(
        database
    )

    if constant_time:
        def clock() -> str:
            return "2026-01-01T00:00:00Z"

    else:
        counter = {
            "value": 0,
        }

        def clock() -> str:
            value = counter[
                "value"
            ]

            counter[
                "value"
            ] += 1

            return (
                "2026-01-01T00:"
                + f"{value:02d}"
                + ":00Z"
            )

    repository = SQLiteRunRepository(
        database
    )

    return (
        repository,
        RunLifecycleService(
            repository,
            clock,
        ),
    )


def _history_candidate_configuration(
    filename: str,
) -> str:
    import hashlib
    import json

    document = {
        "mapping_mode": "strict",
        "profile_version": "0.2.0",
        "source": {
            "byte_count": 1,
            "display_name": filename,
            "sha256": hashlib.sha256(
                filename.encode(
                    "utf-8"
                )
            ).hexdigest(),
        },
    }

    return json.dumps(
        document,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )


def _history_candidate_add_run(
    service,
    *,
    workspace_id: str,
    run_id: str,
    configuration_id: str,
    filename: str,
) -> None:
    service.snapshot_configuration(
        configuration_id,
        workspace_id,
        _history_candidate_configuration(
            filename
        ),
    )

    service.queue_run(
        run_id,
        workspace_id,
        configuration_id,
    )


def test_list_runs_empty_workspace_returns_immutable_empty_tuple(
    tmp_path,
) -> None:
    _, service = _history_candidate_service(
        tmp_path
    )

    service.ensure_workspace(
        "history-empty"
    )

    observed = service.list_runs(
        "history-empty",
        limit=50,
    )

    assert observed == ()
    assert isinstance(
        observed,
        tuple,
    )


def test_list_runs_is_workspace_scoped_and_newest_first(
    tmp_path,
) -> None:
    _, service = _history_candidate_service(
        tmp_path
    )

    for workspace_id in (
        "history-a",
        "history-b",
    ):
        service.ensure_workspace(
            workspace_id
        )

    _history_candidate_add_run(
        service,
        workspace_id="history-a",
        run_id="1" * 32,
        configuration_id="a" * 32,
        filename="older.csv",
    )

    _history_candidate_add_run(
        service,
        workspace_id="history-b",
        run_id="9" * 32,
        configuration_id="f" * 32,
        filename="other.csv",
    )

    _history_candidate_add_run(
        service,
        workspace_id="history-a",
        run_id="2" * 32,
        configuration_id="b" * 32,
        filename="newer.csv",
    )

    observed = service.list_runs(
        "history-a",
        limit=50,
    )

    assert tuple(
        run.run_id
        for run in observed
    ) == (
        "2" * 32,
        "1" * 32,
    )

    assert all(
        run.workspace_id
        == "history-a"
        for run in observed
    )


def test_list_runs_uses_run_id_as_deterministic_tie_break(
    tmp_path,
) -> None:
    _, service = _history_candidate_service(
        tmp_path,
        constant_time=True,
    )

    service.ensure_workspace(
        "history-tie"
    )

    _history_candidate_add_run(
        service,
        workspace_id="history-tie",
        run_id="a" * 32,
        configuration_id="1" * 32,
        filename="a.csv",
    )

    _history_candidate_add_run(
        service,
        workspace_id="history-tie",
        run_id="b" * 32,
        configuration_id="2" * 32,
        filename="b.csv",
    )

    observed = service.list_runs(
        "history-tie",
        limit=50,
    )

    assert tuple(
        run.run_id
        for run in observed
    ) == (
        "b" * 32,
        "a" * 32,
    )

    assert (
        observed[
            0
        ].created_at
        == observed[
            1
        ].created_at
    )


def test_list_runs_enforces_bound(
    tmp_path,
) -> None:
    _, service = _history_candidate_service(
        tmp_path
    )

    service.ensure_workspace(
        "history-limit"
    )

    for index in range(
        4
    ):
        _history_candidate_add_run(
            service,
            workspace_id="history-limit",
            run_id=(
                f"{index + 1:x}"
                * 32
            ),
            configuration_id=(
                f"{index + 10:x}"
                * 32
            ),
            filename=(
                "history-"
                + str(
                    index
                )
                + ".csv"
            ),
        )

    observed = service.list_runs(
        "history-limit",
        limit=2,
    )

    assert len(
        observed
    ) == 2

    assert tuple(
        run.run_id
        for run in observed
    ) == (
        "4" * 32,
        "3" * 32,
    )


def test_list_runs_rejects_invalid_limit(
    tmp_path,
) -> None:
    import pytest

    repository, service = (
        _history_candidate_service(
            tmp_path
        )
    )

    service.ensure_workspace(
        "history-invalid"
    )

    for target in (
        service,
        repository,
    ):
        for value in (
            0,
            -1,
        ):
            with pytest.raises(
                ValueError
            ):
                target.list_runs(
                    "history-invalid",
                    limit=value,
                )

        for value in (
            True,
            "1",
        ):
            with pytest.raises(
                TypeError
            ):
                target.list_runs(
                    "history-invalid",
                    limit=value,
                )
