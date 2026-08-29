"""Tests for immutable result-bundle filesystem storage."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from proteomics_csv_validation.application.result_publication import (
    ResultArtifactStore,
)
from proteomics_csv_validation.domain.result_artifact import (
    ResultStoreError,
)
from proteomics_csv_validation.infrastructure.filesystem.result_store import (
    FilesystemResultStore,
)

from proteomics_csv_validation.infrastructure.filesystem import (
    result_store as result_store_module,
)


_RUN_ID = (
    "0123456789abcdef"
    "0123456789abcdef"
)

_PAYLOAD = (
    b'{"schema_id":"test"}\n'
)


def _imports(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8"
        ),
        filename=str(path),
    )

    modules: set[str] = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias
                in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(
                node.module
            )

    return modules


def test_publish_is_atomic_and_reports_metadata(
    tmp_path: Path,
) -> None:
    store: ResultArtifactStore = (
        FilesystemResultStore(
            tmp_path
        )
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    assert artifact.relative_path == (
        "results/"
        + _RUN_ID
        + ".json"
    )

    assert artifact.sha256 == (
        hashlib.sha256(
            _PAYLOAD
        ).hexdigest()
    )

    assert artifact.byte_count == len(
        _PAYLOAD
    )

    target = (
        tmp_path
        / artifact.relative_path
    )

    assert target.read_bytes() == (
        _PAYLOAD
    )

    assert list(
        (
            tmp_path
            / "results"
        ).glob(
            "*.tmp"
        )
    ) == []


def test_publish_refuses_existing_result(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    first = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    original = (
        tmp_path
        / first.relative_path
    ).read_bytes()

    with pytest.raises(
        ResultStoreError,
    ):
        store.publish(
            _RUN_ID,
            b"different\n",
        )

    assert (
        tmp_path
        / first.relative_path
    ).read_bytes() == original


def test_publish_rejects_invalid_run_id(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    for run_id in (
        "",
        "a" * 31,
        "A" * 32,
        "g" * 32,
        "../" + (
            "a"
            * 32
        ),
        "a" * 33,
    ):
        with pytest.raises(
            ResultStoreError,
        ):
            store.publish(
                run_id,
                _PAYLOAD,
            )


def test_publish_requires_nonempty_bytes(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.publish(
            _RUN_ID,
            b"",
        )

    with pytest.raises(
        ResultStoreError,
    ):
        store.publish(
            _RUN_ID,
            "not bytes",  # type: ignore[arg-type]
        )


def test_read_verified_returns_exact_bytes(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    observed = store.read_verified(
        artifact.relative_path,
        expected_sha256=(
            artifact.sha256
        ),
        expected_byte_count=(
            artifact.byte_count
        ),
    )

    assert observed == _PAYLOAD


def test_read_rejects_path_escape(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    for relative_path in (
        "../result.json",
        "/tmp/result.json",
        "results/../result.json",
        r"results\result.json",
        "results/not-a-run.json",
    ):
        with pytest.raises(
            ResultStoreError,
        ):
            store.read_verified(
                relative_path,
                expected_sha256=(
                    "a"
                    * 64
                ),
                expected_byte_count=1,
            )


def test_read_rejects_hash_mismatch(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.read_verified(
            artifact.relative_path,
            expected_sha256=(
                "0"
                * 64
            ),
            expected_byte_count=(
                artifact.byte_count
            ),
        )


def test_read_rejects_byte_count_mismatch(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.read_verified(
            artifact.relative_path,
            expected_sha256=(
                artifact.sha256
            ),
            expected_byte_count=(
                artifact.byte_count
                + 1
            ),
        )


def test_results_directory_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    results = (
        tmp_path
        / "results"
    )

    original = Path.is_symlink

    def fake_is_symlink(
        self: Path,
    ) -> bool:
        if self == results:
            return True

        return original(
            self
        )

    monkeypatch.setattr(
        Path,
        "is_symlink",
        fake_is_symlink,
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.publish(
            _RUN_ID,
            _PAYLOAD,
        )


def test_target_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = (
        tmp_path
        / "results"
    )

    results.mkdir()

    target = (
        results
        / (
            _RUN_ID
            + ".json"
        )
    )

    original = Path.is_symlink

    def fake_is_symlink(
        self: Path,
    ) -> bool:
        if self == target:
            return True

        return original(
            self
        )

    monkeypatch.setattr(
        Path,
        "is_symlink",
        fake_is_symlink,
    )

    store = FilesystemResultStore(
        tmp_path
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.publish(
            _RUN_ID,
            _PAYLOAD,
        )


def test_link_failure_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_link(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise OSError(
            "link failure"
        )

    monkeypatch.setattr(
        result_store_module.os,
        "link",
        fail_link,
    )

    store = FilesystemResultStore(
        tmp_path
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.publish(
            _RUN_ID,
            _PAYLOAD,
        )

    results = (
        tmp_path
        / "results"
    )

    assert results.is_dir()

    assert list(
        results.iterdir()
    ) == []


def test_filesystem_store_has_no_application_or_adapter_dependency() -> None:
    path = Path(
        result_store_module.__file__
    )

    forbidden = (
        "proteomics_csv_validation.application",
        "proteomics_csv_validation.adapters",
        "proteomics_csv_validation.web",
        "proteomics_csv_validation.pipeline",
        "proteomics_csv_validation.profiles",
        "proteomics_csv_validation.validators",
        "proteomics_csv_validation.models",
    )

    for module in _imports(
        path
    ):
        assert not module.startswith(
            forbidden
        ), (
            path,
            module,
        )


def test_discard_verified_removes_exact_artifact_and_is_idempotent(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    assert store.discard_verified(
        artifact.relative_path,
        expected_sha256=(
            artifact.sha256
        ),
        expected_byte_count=(
            artifact.byte_count
        ),
    ) is True

    assert not (
        tmp_path
        / artifact.relative_path
    ).exists()

    assert store.discard_verified(
        artifact.relative_path,
        expected_sha256=(
            artifact.sha256
        ),
        expected_byte_count=(
            artifact.byte_count
        ),
    ) is False


def test_discard_verified_rejects_tampered_artifact(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    target = (
        tmp_path
        / artifact.relative_path
    )

    original = target.read_bytes()

    tampered = bytearray(
        original
    )

    tampered[
        0
    ] ^= 1

    target.write_bytes(
        bytes(
            tampered
        )
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.discard_verified(
            artifact.relative_path,
            expected_sha256=(
                artifact.sha256
            ),
            expected_byte_count=(
                artifact.byte_count
            ),
        )

    assert target.exists()


def test_discard_verified_rejects_target_symlink(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    target = (
        tmp_path
        / artifact.relative_path
    )

    outside = (
        tmp_path
        / "outside.json"
    )

    outside.write_bytes(
        _PAYLOAD
    )

    target.unlink()

    target.symlink_to(
        outside
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.discard_verified(
            artifact.relative_path,
            expected_sha256=(
                artifact.sha256
            ),
            expected_byte_count=(
                artifact.byte_count
            ),
        )

    assert outside.read_bytes() == (
        _PAYLOAD
    )


def test_discard_verified_rejects_wrong_expected_evidence(
    tmp_path: Path,
) -> None:
    store = FilesystemResultStore(
        tmp_path
    )

    artifact = store.publish(
        _RUN_ID,
        _PAYLOAD,
    )

    target = (
        tmp_path
        / artifact.relative_path
    )

    with pytest.raises(
        ResultStoreError,
    ):
        store.discard_verified(
            artifact.relative_path,
            expected_sha256=(
                "0"
                * 64
            ),
            expected_byte_count=(
                artifact.byte_count
            ),
        )

    assert target.read_bytes() == (
        _PAYLOAD
    )
