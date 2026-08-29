"""Application-facing workflow facade for one browser Review submission."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from proteomics_csv_validation.application.publication import (
    PublicationService,
)
from proteomics_csv_validation.application.review_execution import (
    QueuedReviewExecution,
    ResultPublicationError,
    ResultPublicationRecoveryError,
    ReviewExecutionService,
)
from proteomics_csv_validation.application.run_lifecycle import (
    RunLifecycleService,
)
from proteomics_csv_validation.application.structural_review import (
    StructuralReviewFailure,
    StructuralReviewRequest,
)
from proteomics_csv_validation.domain.result_artifact import (
    RESULT_BUNDLE_ARTIFACT_KIND,
    ResultBundleConfiguration,
    ResultStoreError,
    SourceFileEvidence,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    LedgerRecordNotFoundError,
    RunState,
)

_WORKSPACE_ID = "local-default"


class ResultReader(
    Protocol
):
    """Port required for verified result reads."""

    def read_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bytes:
        ...


@dataclass(
    frozen=True,
    slots=True,
)
class ReviewSubmission:
    """Byte-bound input needed to create and execute one Review run."""

    input_path: Path
    profile_version: str
    mapping_mode: str
    source_display_name: str
    source_sha256: str
    source_byte_count: int
    mapping_path: Path | None = None
    mapping_display_name: str | None = None
    mapping_sha256: str | None = None
    mapping_byte_count: int | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class ReviewResultView:
    """Application-safe durable result state for presentation."""

    run_id: str
    configuration_id: str
    status: str
    started_at: str | None
    finished_at: str | None
    artifact_sha256: str | None
    artifact_byte_count: int | None
    artifact_schema_id: str | None
    artifact_schema_version: str | None
    total_findings: int | None
    evidence_available: bool
    validation_status: str | None = None


class ReviewSubmissionError(
    RuntimeError
):
    """Expected application-facing Review submission failure."""

    def __init__(
        self,
        code: str,
    ) -> None:
        super().__init__(
            "The structural review could not be completed."
        )

        self.code = code


class ReviewResultNotFound(
    LookupError
):
    """Raised when a requested durable run does not exist."""


class ReviewWorkflowPort(
    Protocol
):
    """Presentation-facing Review workflow contract."""

    def recover_interrupted_runs(
        self,
    ) -> None:
        ...

    def submit(
        self,
        submission: ReviewSubmission,
    ) -> str:
        ...

    def result(
        self,
        run_id: str,
    ) -> ReviewResultView:
        ...


class ReviewWorkflowService:
    """Coordinate browser submission using certified application services."""

    def __init__(
        self,
        *,
        lifecycle: RunLifecycleService,
        execution: ReviewExecutionService,
        publication: PublicationService,
        result_reader: ResultReader,
    ) -> None:
        self._lifecycle = lifecycle
        self._execution = execution
        self._publication = publication
        self._result_reader = result_reader

    def recover_interrupted_runs(
        self,
    ) -> None:
        self._lifecycle.ensure_workspace(
            _WORKSPACE_ID
        )

        self._lifecycle.recover_interrupted_runs()

    @staticmethod
    def _mapping_source(
        submission: ReviewSubmission,
    ) -> SourceFileEvidence | None:
        if submission.mapping_path is None:
            if any(
                value is not None
                for value in (
                    submission.mapping_display_name,
                    submission.mapping_sha256,
                    submission.mapping_byte_count,
                )
            ):
                raise ValueError(
                    "Mapping evidence requires a mapping path."
                )

            return None

        if (
            submission.mapping_display_name is None
            or submission.mapping_sha256 is None
            or submission.mapping_byte_count is None
        ):
            raise ValueError(
                "Mapping path requires complete mapping evidence."
            )

        return SourceFileEvidence(
            display_name=(
                submission.mapping_display_name
            ),
            sha256=submission.mapping_sha256,
            byte_count=(
                submission.mapping_byte_count
            ),
        )

    @staticmethod
    def _configuration_json(
        *,
        profile_version: str,
        mapping_mode: str,
        source: SourceFileEvidence,
        mapping_source: (
            SourceFileEvidence
            | None
        ),
    ) -> str:
        document: dict[
            str,
            object,
        ] = {
            "mapping_mode": mapping_mode,
            "profile_version": (
                profile_version
            ),
            "source": {
                "byte_count": (
                    source.byte_count
                ),
                "display_name": (
                    source.display_name
                ),
                "sha256": source.sha256,
            },
        }

        if mapping_source is not None:
            document[
                "column_mapping_source"
            ] = {
                "byte_count": (
                    mapping_source.byte_count
                ),
                "display_name": (
                    mapping_source.display_name
                ),
                "sha256": (
                    mapping_source.sha256
                ),
            }

        return json.dumps(
            document,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

    def submit(
        self,
        submission: ReviewSubmission,
    ) -> str:
        source = SourceFileEvidence(
            display_name=(
                submission.source_display_name
            ),
            sha256=submission.source_sha256,
            byte_count=(
                submission.source_byte_count
            ),
        )

        mapping_source = (
            self._mapping_source(
                submission
            )
        )

        result_configuration = (
            ResultBundleConfiguration(
                profile_version=(
                    submission.profile_version
                ),
                mapping_mode=(
                    submission.mapping_mode
                ),
                source=source,
                column_mapping_source=(
                    mapping_source
                ),
            )
        )

        configuration_id = uuid4().hex
        run_id = uuid4().hex
        artifact_id = uuid4().hex

        self._lifecycle.ensure_workspace(
            _WORKSPACE_ID
        )

        self._lifecycle.snapshot_configuration(
            configuration_id,
            _WORKSPACE_ID,
            self._configuration_json(
                profile_version=(
                    submission.profile_version
                ),
                mapping_mode=(
                    submission.mapping_mode
                ),
                source=source,
                mapping_source=(
                    mapping_source
                ),
            ),
        )

        self._lifecycle.queue_run(
            run_id,
            _WORKSPACE_ID,
            configuration_id,
        )

        command = QueuedReviewExecution(
            run_id=run_id,
            artifact_id=artifact_id,
            workspace_id=_WORKSPACE_ID,
            configuration_id=(
                configuration_id
            ),
            review_request=(
                StructuralReviewRequest(
                    input_path=(
                        submission.input_path
                    ),
                    profile_version=(
                        submission.profile_version
                    ),
                    auto_map=(
                        submission.mapping_mode
                        == "automatic"
                    ),
                    column_map=(
                        submission.mapping_path
                        if (
                            submission.mapping_mode
                            == "explicit"
                        )
                        else None
                    ),
                )
            ),
            result_configuration=(
                result_configuration
            ),
        )

        try:
            self._execution.execute(
                command
            )

        except StructuralReviewFailure as exc:
            raise ReviewSubmissionError(
                exc.code
            ) from exc

        except (
            ResultPublicationError,
            ResultPublicationRecoveryError,
        ):
            # Analysis state is durable and the result page
            # communicates publication unavailability separately.
            pass

        return run_id

    def result(
        self,
        run_id: str,
    ) -> ReviewResultView:
        try:
            run = self._lifecycle.get_run(
                run_id
            )

        except LedgerRecordNotFoundError as exc:
            raise ReviewResultNotFound(
                run_id
            ) from exc

        artifacts = tuple(
            artifact
            for artifact in self._publication.list_artifacts(
                run_id
            )
            if (
                artifact.kind
                == RESULT_BUNDLE_ARTIFACT_KIND
            )
        )

        if len(
            artifacts
        ) > 1:
            raise RuntimeError(
                "More than one result bundle exists for the run."
            )

        artifact = (
            artifacts[
                0
            ]
            if artifacts
            else None
        )

        if (
            run.status
            is not RunState.SUCCEEDED
            and artifact
            is not None
        ):
            raise RuntimeError(
                "A non-successful run unexpectedly has a result bundle."
            )

        total_findings: (
            int
            | None
        ) = None

        validation_status: (
            str
            | None
        ) = None

        evidence_available = False

        if artifact is not None:
            try:
                payload = (
                    self._result_reader
                    .read_verified(
                        artifact.relative_path,
                        expected_sha256=(
                            artifact.sha256
                        ),
                        expected_byte_count=(
                            artifact.byte_count
                        ),
                    )
                )

                document = json.loads(
                    payload
                )

                if not isinstance(
                    document,
                    dict,
                ):
                    raise ValueError(
                        "Result bundle must be an object."
                    )

                validation = document.get(
                    "validation"
                )

                status_value = (
                    validation.get(
                        "status"
                    )
                    if isinstance(
                        validation,
                        dict,
                    )
                    else None
                )

                if (
                    not isinstance(
                        status_value,
                        str,
                    )
                    or not status_value
                ):
                    raise ValueError(
                        "Result bundle validation status is invalid."
                    )

                summary = (
                    validation.get(
                        "summary"
                    )
                    if isinstance(
                        validation,
                        dict,
                    )
                    else None
                )

                value = (
                    summary.get(
                        "total_findings"
                    )
                    if isinstance(
                        summary,
                        dict,
                    )
                    else None
                )

                if (
                    not isinstance(
                        value,
                        int,
                    )
                    or value < 0
                ):
                    raise ValueError(
                        "Result bundle finding total is invalid."
                    )

                total_findings = value
                validation_status = status_value
                evidence_available = True

            except (
                ResultStoreError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
            ):
                evidence_available = False

        return ReviewResultView(
            run_id=run.run_id,
            configuration_id=(
                run.configuration_id
            ),
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            artifact_sha256=(
                artifact.sha256
                if artifact is not None
                else None
            ),
            artifact_byte_count=(
                artifact.byte_count
                if artifact is not None
                else None
            ),
            artifact_schema_id=(
                artifact.schema_id
                if artifact is not None
                else None
            ),
            artifact_schema_version=(
                artifact.schema_version
                if artifact is not None
                else None
            ),
            total_findings=(
                total_findings
            ),
            validation_status=(
                validation_status
            ),
            evidence_available=(
                evidence_available
            ),
        )
