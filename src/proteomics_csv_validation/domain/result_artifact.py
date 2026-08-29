"""Domain contracts for durable structural-review result evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re


RESULT_BUNDLE_SCHEMA_ID = (
    "proteomics_csv_validation.result_bundle"
)

RESULT_BUNDLE_SCHEMA_VERSION = "1.0.0"

RESULT_BUNDLE_ARTIFACT_KIND = "RESULT_BUNDLE"

RESULT_BUNDLE_JSON_SCHEMA_DIALECT = (
    "https://json-schema.org/draft/2020-12/schema"
)

_SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)

_RESULT_RELATIVE_PATH_PATTERN = re.compile(
    r"^results/[0-9a-f]{32}\.json$"
)

_MAPPING_MODES = frozenset(
    {
        "strict",
        "automatic",
        "explicit",
    }
)


class ResultArtifactError(RuntimeError):
    """Base failure for result serialization or filesystem evidence."""


class ResultBundleSerializationError(
    ResultArtifactError
):
    """Raised when completed evidence cannot form a result bundle."""


class ResultStoreError(
    ResultArtifactError
):
    """Raised when durable result bytes cannot be stored or verified."""


def _valid_byte_count(
    value: object,
    *,
    allow_zero: bool,
) -> bool:
    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
    ):
        return False

    if allow_zero:
        return value >= 0

    return value > 0


@dataclass(frozen=True, slots=True)
class SourceFileEvidence:
    """Path-free identity for one temporarily staged source file."""

    display_name: str
    sha256: str
    byte_count: int

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.display_name,
                str,
            )
            or self.display_name == ""
        ):
            raise ValueError(
                "display_name must be a nonempty string."
            )

        if (
            self.display_name
            in {
                ".",
                "..",
            }
            or "/"
            in self.display_name
            or "\\"
            in self.display_name
            or "\x00"
            in self.display_name
        ):
            raise ValueError(
                "display_name must contain a basename only."
            )

        if (
            not isinstance(
                self.sha256,
                str,
            )
            or _SHA256_PATTERN.fullmatch(
                self.sha256
            )
            is None
        ):
            raise ValueError(
                "sha256 must be 64 lowercase hexadecimal characters."
            )

        if not _valid_byte_count(
            self.byte_count,
            allow_zero=True,
        ):
            raise ValueError(
                "byte_count must be a nonnegative integer."
            )


@dataclass(frozen=True, slots=True)
class ResultBundleConfiguration:
    """Configuration evidence needed by the versioned result bundle."""

    profile_version: str
    mapping_mode: str
    source: SourceFileEvidence
    column_mapping_source: (
        SourceFileEvidence
        | None
    ) = None

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.profile_version,
                str,
            )
            or self.profile_version == ""
        ):
            raise ValueError(
                "profile_version must be a nonempty string."
            )

        if (
            not isinstance(
                self.mapping_mode,
                str,
            )
            or self.mapping_mode
            not in _MAPPING_MODES
        ):
            raise ValueError(
                "mapping_mode must be strict, automatic, or explicit."
            )

        if not isinstance(
            self.source,
            SourceFileEvidence,
        ):
            raise TypeError(
                "source must be SourceFileEvidence."
            )

        if (
            self.column_mapping_source
            is not None
            and not isinstance(
                self.column_mapping_source,
                SourceFileEvidence,
            )
        ):
            raise TypeError(
                "column_mapping_source must be SourceFileEvidence or None."
            )

        if (
            self.mapping_mode
            == "explicit"
            and self.column_mapping_source
            is None
        ):
            raise ValueError(
                "Explicit mapping requires column-mapping source evidence."
            )

        if (
            self.mapping_mode
            != "explicit"
            and self.column_mapping_source
            is not None
        ):
            raise ValueError(
                "Only explicit mapping may contain column-mapping source evidence."
            )


@dataclass(frozen=True, slots=True)
class StoredResultArtifact:
    """Filesystem identity of one exact immutable result bundle."""

    relative_path: str
    sha256: str
    byte_count: int

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.relative_path,
                str,
            )
            or _RESULT_RELATIVE_PATH_PATTERN.fullmatch(
                self.relative_path
            )
            is None
        ):
            raise ValueError(
                "relative_path must identify one generated result bundle."
            )

        if (
            not isinstance(
                self.sha256,
                str,
            )
            or _SHA256_PATTERN.fullmatch(
                self.sha256
            )
            is None
        ):
            raise ValueError(
                "sha256 must be 64 lowercase hexadecimal characters."
            )

        if not _valid_byte_count(
            self.byte_count,
            allow_zero=False,
        ):
            raise ValueError(
                "byte_count must be a positive integer."
            )
