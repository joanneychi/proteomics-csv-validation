"""Tests for installed metadata, resources, and command configuration."""

from __future__ import annotations

from importlib import metadata, resources
from pathlib import Path
import tomllib

from proteomics_csv_validation import __version__


def test_installed_distribution_version_matches_package() -> None:
    """One distribution metadata record controls the public version."""

    assert (
        metadata.version(
            "proteomics-csv-validation"
        )
        == __version__
    )


def test_profile_resource_is_installed() -> None:
    """The built-in profile remains available outside the repository."""

    resource = (
        resources.files(
            "proteomics_csv_validation.profiles"
        )
        .joinpath(
            "data"
        )
        .joinpath(
            "proteomics_processed_sample_summary-0.1.0.json"
        )
    )

    assert resource.is_file()


def test_pyproject_declares_console_entry_point(
    repository_root: Path,
) -> None:
    """Packaging metadata exposes the canonical installed command."""

    document = tomllib.loads(
        (
            repository_root
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        document[
            "project"
        ][
            "scripts"
        ][
            "proteomics-csv-validate"
        ]
        ==
        "proteomics_csv_validation.cli:main"
    )

def test_pyproject_build_backend_supports_license_expression(
    repository_root: Path,
) -> None:
    """The declared backend minimum supports PEP 639 license expressions."""

    document = tomllib.loads(
        (
            repository_root
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        document[
            "build-system"
        ][
            "requires"
        ]
        == [
            "setuptools>=77.0.0",
        ]
    )

    assert (
        document[
            "project"
        ][
            "license"
        ]
        == "LicenseRef-Proprietary"
    )
