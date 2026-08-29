"""Adapter from the application boundary to the existing validator."""

from __future__ import annotations

from dataclasses import dataclass

from proteomics_csv_validation.application.structural_review import (
    StructuralReviewFailure,
    StructuralReviewRequest,
)
from proteomics_csv_validation.errors import (
    ColumnMappingError,
    InputAccessError,
    InputError,
    ProfileError,
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
    """Invoke the existing deterministic validation engine through a safe boundary."""

    def validate(
        self,
        request: StructuralReviewRequest,
    ) -> ValidationResult:
        """Resolve the existing profile contract and validate one input."""

        try:
            if request.profile_version is None:
                profile = (
                    load_default_profile()
                )
            else:
                profile = load_profile(
                    _PROFILE_ID,
                    request.profile_version,
                )

            return validate_input(
                request.input_path,
                profile,
                auto_map=(
                    request.auto_map
                ),
                column_map=(
                    request.column_map
                ),
            )

        except InputAccessError as exc:
            raise StructuralReviewFailure(
                "INPUT_ACCESS",
                "The input file could not be accessed.",
            ) from exc

        except InputError as exc:
            raise StructuralReviewFailure(
                "INPUT",
                "The input file could not be reviewed.",
            ) from exc

        except ProfileError as exc:
            raise StructuralReviewFailure(
                "PROFILE",
                "The selected validation profile could not be loaded.",
            ) from exc

        except ColumnMappingError as exc:
            raise StructuralReviewFailure(
                "COLUMN_MAPPING",
                "Column mapping could not be resolved.",
            ) from exc
