"""Outer composition root for the browser Review application workflow."""

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from threading import Lock

from proteomics_csv_validation.adapters.core_validation import (
    LegacyCoreValidationAdapter,
)
from proteomics_csv_validation.adapters.result_bundle import (
    ValidationResultBundleSerializer,
)
from proteomics_csv_validation.application.browser_review import (
    ReviewResultView,
    ReviewSubmission,
    ReviewWorkflowPort,
    ReviewWorkflowService,
)
from proteomics_csv_validation.application.publication import (
    PublicationService,
)
from proteomics_csv_validation.application.review_execution import (
    ReviewExecutionService,
)
from proteomics_csv_validation.application.run_lifecycle import (
    RunLifecycleService,
)
from proteomics_csv_validation.application.structural_review import (
    StructuralReviewService,
)
from proteomics_csv_validation.infrastructure.filesystem.result_store import (
    FilesystemResultStore,
)
from proteomics_csv_validation.infrastructure.sqlite import (
    initialize_ledger,
)
from proteomics_csv_validation.infrastructure.sqlite.publication_repository import (
    SQLitePublicationRepository,
)
from proteomics_csv_validation.infrastructure.sqlite.run_repository import (
    SQLiteRunRepository,
)


def _utc_now() -> str:
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


class _LazyReviewWorkflow:
    """Initialize concrete durable services once on first workflow use."""

    def __init__(
        self,
        data_root: Path,
    ) -> None:
        self._data_root = data_root
        self._lock = Lock()
        self._service: (
            ReviewWorkflowService
            | None
        ) = None

    def _get_service(
        self,
    ) -> ReviewWorkflowService:
        service = self._service

        if service is not None:
            return service

        with self._lock:
            service = self._service

            if service is not None:
                return service

            database = (
                self._data_root
                / "ledger.sqlite3"
            )

            initialize_ledger(
                database
            )

            lifecycle = RunLifecycleService(
                SQLiteRunRepository(
                    database
                ),
                _utc_now,
            )

            publication = PublicationService(
                SQLitePublicationRepository(
                    database
                ),
                _utc_now,
            )

            result_store = (
                FilesystemResultStore(
                    self._data_root
                    / "artifacts"
                )
            )

            execution = ReviewExecutionService(
                lifecycle=lifecycle,
                structural_review=(
                    StructuralReviewService(
                        LegacyCoreValidationAdapter()
                    )
                ),
                serializer=(
                    ValidationResultBundleSerializer()
                ),
                result_store=(
                    result_store
                ),
                publication=publication,
            )

            service = ReviewWorkflowService(
                lifecycle=lifecycle,
                execution=execution,
                publication=publication,
                result_reader=(
                    result_store
                ),
            )

            self._service = service

            return service

    def recover_interrupted_runs(
        self,
    ) -> None:
        self._get_service().recover_interrupted_runs()

    def submit(
        self,
        submission: ReviewSubmission,
    ) -> str:
        return self._get_service().submit(
            submission
        )

    def result(
        self,
        run_id: str,
    ) -> ReviewResultView:
        return self._get_service().result(
            run_id
        )


def build_review_workflow(
    data_root: Path,
) -> ReviewWorkflowPort:
    """Create the lazy outer composition bridge for Review."""

    if not isinstance(
        data_root,
        Path,
    ):
        raise TypeError(
            "data_root must be a pathlib.Path."
        )

    if not data_root.is_absolute():
        raise ValueError(
            "data_root must be absolute."
        )

    return _LazyReviewWorkflow(
        data_root
    )
