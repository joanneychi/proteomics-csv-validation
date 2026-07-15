"""Expected operational exception hierarchy."""

from __future__ import annotations


class ProteomicsValidationError(Exception):
    """Base class for expected application failures."""


class InputError(ProteomicsValidationError):
    """Base class for input-related operational failures."""


class InputAccessError(InputError):
    """Raised when the selected input cannot be accessed safely."""


class ProfileError(ProteomicsValidationError):
    """Base class for profile-resolution and definition failures."""


class ProfileNotFoundError(ProfileError):
    """Raised when a registered profile resource cannot be found."""


class ProfileDefinitionError(ProfileError):
    """Raised when a profile resource violates its descriptor contract."""


class OutputWriteError(ProteomicsValidationError):
    """Raised when a technical report cannot be published safely."""
