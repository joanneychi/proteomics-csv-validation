"""Shared immutable fixtures for the validation test suite."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from proteomics_csv_validation.profiles.loader import (
    load_default_profile,
)
from proteomics_csv_validation.profiles.models import (
    ProfileDefinition,
)


_REPOSITORY_ROOT = (
    Path(
        __file__
    )
    .resolve()
    .parents[
        1
    ]
)


def _strict_object(
    pairs: list[
        tuple[
            str,
            Any,
        ]
    ],
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate JSON key: {key!r}"
            )

        result[key] = value

    return result


def _reject_constant(
    value: str,
) -> None:
    raise ValueError(
        f"Nonstandard JSON constant: {value}"
    )


def _freeze(
    value: object,
) -> object:
    if isinstance(
        value,
        dict,
    ):
        return MappingProxyType(
            {
                str(
                    key
                ): _freeze(
                    item
                )
                for key, item
                in value.items()
            }
        )

    if isinstance(
        value,
        list,
    ):
        return tuple(
            _freeze(
                item
            )
            for item
            in value
        )

    return value


@pytest.fixture(
    scope="session"
)
def repository_root() -> Path:
    """Return the repository root used by controlled fixtures."""

    return _REPOSITORY_ROOT


@pytest.fixture(
    scope="session"
)
def baseline_input_path(
    repository_root: Path,
) -> Path:
    """Return the reviewed no-finding synthetic input."""

    return (
        repository_root
        / "data"
        / "synthetic"
        / "baseline_valid.csv"
    )


@pytest.fixture(
    scope="session"
)
def seeded_input_path(
    repository_root: Path,
) -> Path:
    """Return the reviewed seeded schema-and-identifier input."""

    return (
        repository_root
        / "data"
        / "synthetic"
        / "seeded_errors.csv"
    )


@pytest.fixture(
    scope="session"
)
def required_value_missing_input_path(
    repository_root: Path,
) -> Path:
    """Return the reviewed required-value input."""

    return (
        repository_root
        / "data"
        / "synthetic"
        / "required_value_missing_values.csv"
    )


@pytest.fixture(
    scope="session"
)
def default_profile() -> ProfileDefinition:
    """Return the installed built-in profile."""

    return load_default_profile()


@pytest.fixture(
    scope="session"
)
def loaded_seeded_expected(
    repository_root: Path,
) -> Mapping[
    str,
    object,
]:
    """Return the strict frozen seeded expected-results fixture."""

    path = (
        repository_root
        / "data"
        / "expected"
        / "seeded_errors.expected.json"
    )

    loaded = json.loads(
        path.read_text(
            encoding="utf-8"
        ),
        object_pairs_hook=(
            _strict_object
        ),
        parse_constant=(
            _reject_constant
        ),
    )

    frozen = _freeze(
        loaded
    )

    assert isinstance(
        frozen,
        Mapping,
    )

    return frozen

@pytest.fixture(
    scope="session"
)
def loaded_required_value_missing_expected(
    repository_root: Path,
) -> Mapping[
    str,
    object,
]:
    """Return the strict frozen required-value expected-results fixture."""

    path = (
        repository_root
        / "data"
        / "expected"
        / "required_value_missing_values.expected.json"
    )

    loaded = json.loads(
        path.read_text(
            encoding="utf-8"
        ),
        object_pairs_hook=(
            _strict_object
        ),
        parse_constant=(
            _reject_constant
        ),
    )

    frozen = _freeze(
        loaded
    )

    assert isinstance(
        frozen,
        Mapping,
    )

    return frozen
