"""Application orchestration for one already-queued structural review."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from proteomics_csv_validation.application.publication import (
    PublicationService,
)
from proteomics_csv_validation.application.result_publication import (
    ResultArtifactStore,
    ResultBundleSerializer,
)
from proteomics_csv_validation.application.run_lifecycle import (
    RunLifecycleService,
)
from proteomics_csv_validation.application.structural_review import (
    StructuralReviewFailure,
    StructuralReviewRequest,
    StructuralReviewService,
)
from proteomics_csv_validation.domain.publication import (
    RunArtifactRecord,
)
from proteomics_csv_validation.domain.result_artifact import (
    RESULT_BUNDLE_ARTIFACT_KIND,
    RESULT_BUNDLE_SCHEMA_ID,
    RESULT_BUNDLE_SCHEMA_VERSION,
    ResultBundleConfiguration,
    SourceFileEvidence,
    StoredResultArtifact,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    AnalysisRunRecord,
    RunState,
)


_ID_PATTERN = re.compile(
    r"^[0-9a-f]{32}$"
)


class ReviewExecutionContractError(
    RuntimeError
):
    """Raised before execution when queued-run evidence disagrees."""


class ReviewFailureFinalizationError(
    RuntimeError
):
    """Raised when a review failure cannot be persisted as FAILED."""

    def __init__(
        self,
        run_id: str,
    ) -> None:
        self.run_id = run_id

        super().__init__(
            "Structural review failed and its FAILED run state could not be recorded."
        )


class ResultPublicationError(
    RuntimeError
):
    """Raised after successful analysis when result publication fails cleanly."""

    def __init__(
        self,
        run_id: str,
    ) -> None:
        self.run_id = run_id

        super().__init__(
            "Structural review completed, but durable result publication failed."
        )


class ResultPublicationRecoveryError(
    RuntimeError
):
    """Raised when cross-store publication state cannot be resolved safely."""

    def __init__(
        self,
        run_id: str,
    ) -> None:
        self.run_id = run_id

        super().__init__(
            "Structural review completed, but result publication recovery requires review."
        )


def _mapping_mode(
    request: StructuralReviewRequest,
) -> str:
    if (
        request.auto_map
        and request.column_map
        is not None
    ):
        raise ValueError(
            "Automatic and explicit column mapping are mutually exclusive."
        )

    if request.column_map is not None:
        return "explicit"

    if request.auto_map:
        return "automatic"

    return "strict"


def _observed_file_identity(
    path: Path,
    *,
    unavailable_code: str,
    unavailable_message: str,
) -> tuple[
    str,
    int,
]:
    digest = hashlib.sha256()
    byte_count = 0

    try:
        with path.open(
            "rb"
        ) as handle:
            while True:
                chunk = handle.read(
                    1024
                    * 1024
                )

                if not chunk:
                    break

                digest.update(
                    chunk
                )

                byte_count += len(
                    chunk
                )

    except OSError as exc:
        raise StructuralReviewFailure(
            unavailable_code,
            unavailable_message,
        ) from exc

    return (
        digest.hexdigest(),
        byte_count,
    )


def _verify_file_evidence(
    path: Path,
    evidence: SourceFileEvidence,
    *,
    unavailable_code: str,
    unavailable_message: str,
    mismatch_code: str,
    mismatch_message: str,
) -> None:
    observed_sha256, observed_size = (
        _observed_file_identity(
            path,
            unavailable_code=(
                unavailable_code
            ),
            unavailable_message=(
                unavailable_message
            ),
        )
    )

    if (
        observed_sha256
        != evidence.sha256
        or observed_size
        != evidence.byte_count
    ):
        raise StructuralReviewFailure(
            mismatch_code,
            mismatch_message,
        )


def _verify_execution_evidence(
    command: QueuedReviewExecution,
) -> None:
    _verify_file_evidence(
        command.review_request.input_path,
        command.result_configuration.source,
        unavailable_code=(
            "SOURCE_EVIDENCE_UNAVAILABLE"
        ),
        unavailable_message=(
            "The staged input file is unavailable."
        ),
        mismatch_code=(
            "SOURCE_EVIDENCE_MISMATCH"
        ),
        mismatch_message=(
            "The staged input file no longer matches its recorded evidence."
        ),
    )

    if (
        command.result_configuration.mapping_mode
        == "explicit"
    ):
        mapping_path = (
            command.review_request.column_map
        )

        mapping_evidence = (
            command
            .result_configuration
            .column_mapping_source
        )

        if (
            mapping_path is None
            or mapping_evidence is None
        ):
            raise ReviewExecutionContractError(
                "Explicit mapping execution is missing mapping evidence."
            )

        _verify_file_evidence(
            mapping_path,
            mapping_evidence,
            unavailable_code=(
                "MAPPING_EVIDENCE_UNAVAILABLE"
            ),
            unavailable_message=(
                "The staged column-mapping file is unavailable."
            ),
            mismatch_code=(
                "MAPPING_EVIDENCE_MISMATCH"
            ),
            mismatch_message=(
                "The staged column-mapping file no longer matches its recorded evidence."
            ),
        )


def _result_artifact_matches(
    artifact: RunArtifactRecord,
    command: QueuedReviewExecution,
    stored: StoredResultArtifact,
) -> bool:
    return (
        artifact.artifact_id
        == command.artifact_id
        and artifact.run_id
        == command.run_id
        and artifact.export_attempt_id
        is None
        and artifact.kind
        == RESULT_BUNDLE_ARTIFACT_KIND
        and artifact.schema_id
        == RESULT_BUNDLE_SCHEMA_ID
        and artifact.schema_version
        == RESULT_BUNDLE_SCHEMA_VERSION
        and artifact.relative_path
        == stored.relative_path
        and artifact.sha256
        == stored.sha256
        and artifact.byte_count
        == stored.byte_count
    )


@dataclass(frozen=True, slots=True)
class QueuedReviewExecution:
    """Inputs required to execute one already-queued structural review."""

    run_id: str
    artifact_id: str
    workspace_id: str
    configuration_id: str
    review_request: StructuralReviewRequest
    result_configuration: ResultBundleConfiguration

    def __post_init__(
        self,
    ) -> None:
        for label, value in (
            (
                "run_id",
                self.run_id,
            ),
            (
                "artifact_id",
                self.artifact_id,
            ),
        ):
            if (
                not isinstance(
                    value,
                    str,
                )
                or _ID_PATTERN.fullmatch(
                    value
                )
                is None
            ):
                raise ValueError(
                    label
                    + " must be 32 lowercase hexadecimal characters."
                )

        for label, value in (
            (
                "workspace_id",
                self.workspace_id,
            ),
            (
                "configuration_id",
                self.configuration_id,
            ),
        ):
            if (
                not isinstance(
                    value,
                    str,
                )
                or value == ""
            ):
                raise ValueError(
                    label
                    + " must be a nonempty string."
                )

        if not isinstance(
            self.review_request,
            StructuralReviewRequest,
        ):
            raise TypeError(
                "review_request must be StructuralReviewRequest."
            )

        if not isinstance(
            self.review_request.input_path,
            Path,
        ):
            raise TypeError(
                "review_request.input_path must be pathlib.Path."
            )

        if (
            self.review_request.column_map
            is not None
            and not isinstance(
                self.review_request.column_map,
                Path,
            )
        ):
            raise TypeError(
                "review_request.column_map must be pathlib.Path or None."
            )

        if not isinstance(
            self.result_configuration,
            ResultBundleConfiguration,
        ):
            raise TypeError(
                "result_configuration must be ResultBundleConfiguration."
            )

        if (
            self.review_request.profile_version
            is None
        ):
            raise ValueError(
                "Queued review execution requires an explicit profile version."
            )

        if (
            self.review_request.profile_version
            != self.result_configuration.profile_version
        ):
            raise ValueError(
                "Review request and result configuration profile versions differ."
            )

        if (
            _mapping_mode(
                self.review_request
            )
            != self.result_configuration.mapping_mode
        ):
            raise ValueError(
                "Review request and result configuration mapping modes differ."
            )


@dataclass(frozen=True, slots=True)
class ReviewExecutionOutcome:
    """Durable identities returned after analysis and publication succeed."""

    run: AnalysisRunRecord
    artifact: RunArtifactRecord


@dataclass(frozen=True, slots=True)
class ReviewExecutionService:
    """Coordinate lifecycle, validation, serialization, and result publication."""

    lifecycle: RunLifecycleService
    structural_review: StructuralReviewService
    serializer: ResultBundleSerializer
    result_store: ResultArtifactStore
    publication: PublicationService

    def _verified_outcome(
        self,
        *,
        run: AnalysisRunRecord,
        artifact: RunArtifactRecord,
    ) -> ReviewExecutionOutcome:
        try:
            self.result_store.read_verified(
                artifact.relative_path,
                expected_sha256=(
                    artifact.sha256
                ),
                expected_byte_count=(
                    artifact.byte_count
                ),
            )

        except Exception as verification_error:
            raise ResultPublicationRecoveryError(
                run.run_id
            ) from verification_error

        return ReviewExecutionOutcome(
            run=run,
            artifact=artifact,
        )

    def _recover_result_publication(
        self,
        *,
        command: QueuedReviewExecution,
        succeeded: AnalysisRunRecord,
        stored: StoredResultArtifact,
        publication_error: Exception,
    ) -> ReviewExecutionOutcome:
        try:
            artifacts = (
                self.publication
                .list_artifacts(
                    command.run_id
                )
            )

        except Exception as recovery_error:
            raise ResultPublicationRecoveryError(
                command.run_id
            ) from recovery_error

        result_artifacts = tuple(
            artifact
            for artifact in artifacts
            if artifact.kind
            == RESULT_BUNDLE_ARTIFACT_KIND
        )

        for artifact in result_artifacts:
            if _result_artifact_matches(
                artifact,
                command,
                stored,
            ):
                return self._verified_outcome(
                    run=succeeded,
                    artifact=artifact,
                )

        if result_artifacts:
            raise ResultPublicationRecoveryError(
                command.run_id
            ) from publication_error

        try:
            self.result_store.discard_verified(
                stored.relative_path,
                expected_sha256=(
                    stored.sha256
                ),
                expected_byte_count=(
                    stored.byte_count
                ),
            )

        except Exception as cleanup_error:
            raise ResultPublicationRecoveryError(
                command.run_id
            ) from cleanup_error

        raise ResultPublicationError(
            command.run_id
        ) from publication_error

    def execute(
        self,
        command: QueuedReviewExecution,
    ) -> ReviewExecutionOutcome:
        if not isinstance(
            command,
            QueuedReviewExecution,
        ):
            raise TypeError(
                "command must be QueuedReviewExecution."
            )

        queued = self.lifecycle.get_run(
            command.run_id
        )

        if (
            queued.workspace_id
            != command.workspace_id
            or queued.configuration_id
            != command.configuration_id
        ):
            raise ReviewExecutionContractError(
                "Queued run identity does not match the requested execution."
            )

        self.lifecycle.start_run(
            command.run_id
        )

        try:
            _verify_execution_evidence(
                command
            )

            validation = (
                self.structural_review.review(
                    command.review_request
                )
            )

            _verify_execution_evidence(
                command
            )

        except Exception:
            try:
                self.lifecycle.complete_run(
                    command.run_id,
                    RunState.FAILED,
                )

            except Exception as state_error:
                raise ReviewFailureFinalizationError(
                    command.run_id
                ) from state_error

            raise

        succeeded = (
            self.lifecycle.complete_run(
                command.run_id,
                RunState.SUCCEEDED,
            )
        )

        try:
            payload = self.serializer.serialize(
                run=succeeded,
                configuration=(
                    command.result_configuration
                ),
                validation=validation,
            )

        except Exception as exc:
            raise ResultPublicationError(
                command.run_id
            ) from exc

        try:
            stored = (
                self.result_store.publish(
                    command.run_id,
                    payload,
                )
            )

        except Exception as exc:
            raise ResultPublicationError(
                command.run_id
            ) from exc

        try:
            artifact = (
                self.publication
                .record_result_artifact(
                    command.artifact_id,
                    command.run_id,
                    schema_id=(
                        RESULT_BUNDLE_SCHEMA_ID
                    ),
                    schema_version=(
                        RESULT_BUNDLE_SCHEMA_VERSION
                    ),
                    relative_path=(
                        stored.relative_path
                    ),
                    sha256=stored.sha256,
                    byte_count=(
                        stored.byte_count
                    ),
                )
            )

        except Exception as exc:
            return (
                self._recover_result_publication(
                    command=command,
                    succeeded=succeeded,
                    stored=stored,
                    publication_error=exc,
                )
            )

        if not _result_artifact_matches(
            artifact,
            command,
            stored,
        ):
            return (
                self._recover_result_publication(
                    command=command,
                    succeeded=succeeded,
                    stored=stored,
                    publication_error=(
                        RuntimeError(
                            "Recorded result artifact identity was inconsistent."
                        )
                    ),
                )
            )

        return self._verified_outcome(
            run=succeeded,
            artifact=artifact,
        )
