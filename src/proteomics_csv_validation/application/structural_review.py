"""Application boundary for deterministic structural review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StructuralReviewRequest:
    """Inputs already supported by the certified structural validator."""

    input_path: Path
    profile_version: str | None = None
    auto_map: bool = False
    column_map: Path | None = None


class StructuralReviewEvidence(Protocol):
    """Structural view of immutable deterministic validation evidence."""

    application_version: str
    descriptor_schema_version: str
    profile_id: str
    profile_version: str
    input_name: str
    status: Any
    rows: int
    configured_rules: tuple[Any, ...]
    findings: tuple[Any, ...]
    summary: Any
    column_mapping: Any


class StructuralReviewEngine(Protocol):
    """Port for one deterministic processed-CSV structural review."""

    def validate(
        self,
        request: StructuralReviewRequest,
    ) -> StructuralReviewEvidence:
        """Return immutable structural-review evidence."""


@dataclass(frozen=True, slots=True)
class StructuralReviewService:
    """Application service independent of core orchestration modules."""

    engine: StructuralReviewEngine

    def review(
        self,
        request: StructuralReviewRequest,
    ) -> StructuralReviewEvidence:
        """Execute one structural review through the configured engine."""

        if not isinstance(
            request,
            StructuralReviewRequest,
        ):
            raise TypeError(
                "request must be a StructuralReviewRequest."
            )

        return self.engine.validate(
            request
        )
