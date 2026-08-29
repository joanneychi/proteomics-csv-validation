"""Atomic filesystem storage for immutable result-bundle bytes."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import tempfile

from proteomics_csv_validation.domain.result_artifact import (
    ResultStoreError,
    StoredResultArtifact,
)


_RUN_ID_PATTERN = re.compile(
    r"^[0-9a-f]{32}$"
)

_RELATIVE_PATH_PATTERN = re.compile(
    r"^results/[0-9a-f]{32}\.json$"
)

_SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


def _validated_run_id(
    run_id: str,
) -> str:
    if (
        not isinstance(
            run_id,
            str,
        )
        or _RUN_ID_PATTERN.fullmatch(
            run_id
        )
        is None
    ):
        raise ResultStoreError(
            "run_id must be 32 lowercase hexadecimal characters."
        )

    return run_id


def _validated_relative_path(
    relative_path: str,
) -> str:
    if (
        not isinstance(
            relative_path,
            str,
        )
        or _RELATIVE_PATH_PATTERN.fullmatch(
            relative_path
        )
        is None
    ):
        raise ResultStoreError(
            "Result artifact path is invalid."
        )

    return relative_path


def _validated_sha256(
    value: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or _SHA256_PATTERN.fullmatch(
            value
        )
        is None
    ):
        raise ResultStoreError(
            "Expected SHA-256 identity is invalid."
        )

    return value


def _validated_byte_count(
    value: int,
) -> int:
    if (
        not isinstance(
            value,
            int,
        )
        or isinstance(
            value,
            bool,
        )
        or value <= 0
    ):
        raise ResultStoreError(
            "Expected byte count must be a positive integer."
        )

    return value


class FilesystemResultStore:
    """Publish and verify immutable result bundles below one owned root."""

    def __init__(
        self,
        root: Path,
    ) -> None:
        if not isinstance(
            root,
            Path,
        ):
            raise TypeError(
                "root must be a pathlib.Path."
            )

        self._root = root

    def _root_directory(
        self,
        *,
        create: bool,
    ) -> Path:
        root = self._root

        try:
            if root.is_symlink():
                raise ResultStoreError(
                    "Result storage root cannot be a symbolic link."
                )

            if create:
                root.mkdir(
                    parents=True,
                    exist_ok=True,
                    mode=0o700,
                )

            if (
                not root.exists()
                or not root.is_dir()
                or root.is_symlink()
            ):
                raise ResultStoreError(
                    "Result storage root is unavailable."
                )

        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(
                "Result storage root could not be prepared."
            ) from exc

        return root

    def _results_directory(
        self,
        *,
        create: bool,
    ) -> Path:
        root = self._root_directory(
            create=create
        )

        directory = (
            root
            / "results"
        )

        try:
            if directory.is_symlink():
                raise ResultStoreError(
                    "Result directory cannot be a symbolic link."
                )

            if create:
                directory.mkdir(
                    exist_ok=True,
                    mode=0o700,
                )

            if (
                not directory.exists()
                or not directory.is_dir()
                or directory.is_symlink()
            ):
                raise ResultStoreError(
                    "Result directory is unavailable."
                )

        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(
                "Result directory could not be prepared."
            ) from exc

        return directory

    def publish(
        self,
        run_id: str,
        payload: bytes,
    ) -> StoredResultArtifact:
        normalized_run_id = (
            _validated_run_id(
                run_id
            )
        )

        if (
            not isinstance(
                payload,
                bytes,
            )
            or len(
                payload
            )
            == 0
        ):
            raise ResultStoreError(
                "Result payload must be nonempty bytes."
            )

        directory = (
            self._results_directory(
                create=True
            )
        )

        target = (
            directory
            / (
                normalized_run_id
                + ".json"
            )
        )

        try:
            if (
                target.exists()
                or target.is_symlink()
            ):
                raise ResultStoreError(
                    "A result bundle already exists for this run."
                )
        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(
                "Result target identity could not be verified."
            ) from exc

        digest = hashlib.sha256(
            payload
        ).hexdigest()

        byte_count = len(
            payload
        )

        file_descriptor = -1
        temporary_path: Path | None = (
            None
        )

        try:
            (
                file_descriptor,
                temporary_name,
            ) = tempfile.mkstemp(
                dir=directory,
                prefix=(
                    "."
                    + normalized_run_id
                    + "."
                ),
                suffix=".tmp",
            )

            temporary_path = Path(
                temporary_name
            )

            with os.fdopen(
                file_descriptor,
                "wb",
            ) as handle:
                file_descriptor = -1

                handle.write(
                    payload
                )

                handle.flush()

                os.fsync(
                    handle.fileno()
                )

            try:
                os.link(
                    temporary_path,
                    target,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise ResultStoreError(
                    "A result bundle already exists for this run."
                ) from exc

        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(
                "Result bundle could not be published atomically."
            ) from exc
        finally:
            if file_descriptor >= 0:
                try:
                    os.close(
                        file_descriptor
                    )
                except OSError:
                    pass

            if temporary_path is not None:
                try:
                    temporary_path.unlink(
                        missing_ok=True
                    )
                except OSError:
                    pass

        relative_path = (
            "results/"
            + normalized_run_id
            + ".json"
        )

        return StoredResultArtifact(
            relative_path=relative_path,
            sha256=digest,
            byte_count=byte_count,
        )

    def read_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bytes:
        normalized_path = (
            _validated_relative_path(
                relative_path
            )
        )

        expected_digest = (
            _validated_sha256(
                expected_sha256
            )
        )

        expected_size = (
            _validated_byte_count(
                expected_byte_count
            )
        )

        directory = (
            self._results_directory(
                create=False
            )
        )

        filename = normalized_path.split(
            "/",
            1,
        )[1]

        target = (
            directory
            / filename
        )

        try:
            if (
                target.is_symlink()
                or not target.is_file()
            ):
                raise ResultStoreError(
                    "Result artifact is unavailable."
                )

            data = target.read_bytes()

        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(
                "Result artifact could not be read safely."
            ) from exc

        if len(
            data
        ) != expected_size:
            raise ResultStoreError(
                "Result artifact byte count does not match recorded evidence."
            )

        observed_digest = hashlib.sha256(
            data
        ).hexdigest()

        if not hmac.compare_digest(
            observed_digest,
            expected_digest,
        ):
            raise ResultStoreError(
                "Result artifact digest does not match recorded evidence."
            )

        return data

    def discard_verified(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        expected_byte_count: int,
    ) -> bool:
        normalized_path = (
            _validated_relative_path(
                relative_path
            )
        )

        expected_digest = (
            _validated_sha256(
                expected_sha256
            )
        )

        expected_size = (
            _validated_byte_count(
                expected_byte_count
            )
        )

        root = self._root

        try:
            if root.is_symlink():
                raise ResultStoreError(
                    "Result storage root cannot be a symbolic link."
                )

            if not root.exists():
                return False

            if not root.is_dir():
                raise ResultStoreError(
                    "Result storage root is unavailable."
                )

            directory = (
                root
                / "results"
            )

            if directory.is_symlink():
                raise ResultStoreError(
                    "Result directory cannot be a symbolic link."
                )

            if not directory.exists():
                return False

            if not directory.is_dir():
                raise ResultStoreError(
                    "Result directory is unavailable."
                )

            filename = (
                normalized_path.split(
                    "/",
                    1,
                )[1]
            )

            target = (
                directory
                / filename
            )

            if target.is_symlink():
                raise ResultStoreError(
                    "Result artifact cannot be discarded through a symbolic link."
                )

            if not target.exists():
                return False

            if not target.is_file():
                raise ResultStoreError(
                    "Result artifact is unavailable."
                )

            before = target.stat(
                follow_symlinks=False
            )

            data = target.read_bytes()

            if len(
                data
            ) != expected_size:
                raise ResultStoreError(
                    "Result artifact byte count does not match expected evidence."
                )

            observed_digest = (
                hashlib.sha256(
                    data
                ).hexdigest()
            )

            if not hmac.compare_digest(
                observed_digest,
                expected_digest,
            ):
                raise ResultStoreError(
                    "Result artifact digest does not match expected evidence."
                )

            after = target.stat(
                follow_symlinks=False
            )

            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )

            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )

            if before_identity != after_identity:
                raise ResultStoreError(
                    "Result artifact changed during verified discard."
                )

            try:
                target.unlink()
            except FileNotFoundError:
                return False

        except ResultStoreError:
            raise
        except OSError as exc:
            raise ResultStoreError(
                "Result artifact could not be discarded safely."
            ) from exc

        return True
