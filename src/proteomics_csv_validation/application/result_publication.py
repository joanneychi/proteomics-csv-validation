"""Application ports for versioned result serialization and storage."""

from __future__ import annotations

from typing import Protocol

from proteomics_csv_validation.application.structural_review import (
    StructuralReviewEvidence,
)
from proteomics_csv_validation.domain.result_artifact import (
    ResultBundleConfiguration,
    StoredResultArtifact,
)
from proteomics_csv_validation.domain.run_lifecycle import (
    AnalysisRunRecord,
)


class ResultBundleSerializer(
    Protocol
):
    """Port for converting completed review evidence to exact JSON bytes."""

    def serialize(
        self,
        *,
        run: AnalysisRunRecord,
        configuration: ResultBundleConfiguration,
        validation: StructuralReviewEvidence,
    ) -> bytes:
        """Return deterministic result-bundle bytes."""


class ResultArtifactStore(
    Protocol
):
    """Port for immutable result-bundle filesystem publication."""

    def publish(
        self,
        run_id: str,
        payload: bytes,
    ) -> StoredResultArtifact:
        """Publish exact bytes under an application-controlled result path."""

    def read_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bytes:
        """Read bytes only when path, size, and digest remain trustworthy."""

    def discard_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bool:
        """Remove only exact verified unregistered result bytes."""
