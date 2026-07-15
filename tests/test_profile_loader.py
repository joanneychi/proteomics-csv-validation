"""Tests for strict built-in profile loading."""

from __future__ import annotations

import pytest

from proteomics_csv_validation.errors import (
    ProfileNotFoundError,
)
from proteomics_csv_validation.profiles.loader import (
    load_default_profile,
    load_profile,
)


def test_default_profile_identity_and_required_order() -> None:
    """The reviewed built-in profile loads with its canonical identity."""

    profile = load_default_profile()

    assert (
        profile.profile_id
        == "proteomics_processed_sample_summary"
    )

    assert profile.profile_version == "0.1.0"

    assert tuple(
        field.name
        for field in profile.required_fields
    ) == (
        "study_id",
        "sample_id",
        "experimental_condition",
        "sample_preparation_batch",
        "quantified_protein_group_count",
        "protein_group_intensity_sum",
    )


def test_unknown_profile_is_rejected() -> None:
    """Registry control prevents arbitrary profile selection."""

    with pytest.raises(
        ProfileNotFoundError
    ):
        load_profile(
            "unknown",
            "1.0.0",
        )
