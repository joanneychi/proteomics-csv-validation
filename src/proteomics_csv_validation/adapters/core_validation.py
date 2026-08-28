"""Adapter from the application boundary to the existing validator."""

from __future__ import annotations

from dataclasses import dataclass

from proteomics_csv_validation.application.structural_review import (
    StructuralReviewRequest,
)
from proteomics_csv_validation.models import (
    ValidationResult,
)
from proteomics_csv_validation.pipeline import (
    validate_input,
)
from proteomics_csv_validation.profiles.loader import (
    load_default_profile,
    load_profile,
)


_PROFILE_ID = (
    "proteomics_processed_sample_summary"
)


@dataclass(frozen=True, slots=True)
class LegacyCoreValidationAdapter:
    """Invoke the existing deterministic validation engine unchanged."""

    def validate(
        self,
        request: StructuralReviewRequest,
    ) -> ValidationResult:
        """Resolve the existing profile contract and validate one input."""

        if request.profile_version is None:
            profile = load_default_profile()
        else:
            profile = load_profile(
                _PROFILE_ID,
                request.profile_version,
            )

        return validate_input(
            request.input_path,
            profile,
            auto_map=request.auto_map,
            column_map=request.column_map,
        )
