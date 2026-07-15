"""Package metadata for the proteomics CSV validation prototype."""

from __future__ import annotations

from importlib.metadata import version


_DISTRIBUTION_NAME = "proteomics-csv-validation"

__version__ = version(
    _DISTRIBUTION_NAME
)


__all__ = [
    "__version__",
]
