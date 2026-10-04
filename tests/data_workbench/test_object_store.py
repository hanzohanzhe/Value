from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gridform_core.data_workbench.object_store import (
    ByteLimitExceeded,
    FetchCancelled,
    LocalObjectStore,
)


def test_stream_is_hashed_and_installed_under_relative_object_key(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    stored = store.put_stream(
        [b"official ", b"bytes"], media_type="application/octet-stream"
    )

    expected = hashlib.sha256(b"official bytes").hexdigest()
    assert stored.sha256 == expected
    assert stored.object_key == f"raw/sha256/{expected}"
    assert not Path(stored.object_key).is_absolute()
    assert store.verify(stored.object_key, expected)


def test_duplicate_bytes_reuse_one_verified_object(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)

    first = store.put_stream([b"same"], media_type="text/csv")
    second = store.put_stream([b"sa", b"me"], media_type="text/csv")

    assert first == second
    assert len(list((tmp_path / "raw" / "sha256").iterdir())) == 1


def test_byte_limit_and_cancellation_remove_partial_staging_files(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)

    with pytest.raises(ByteLimitExceeded):
        store.put_stream([b"1234", b"5678"], media_type="text/csv", max_bytes=6)
    assert list((tmp_path / "staging").iterdir()) == []

    calls = iter((False, True))
    with pytest.raises(FetchCancelled):
        store.put_stream(
            [b"1234", b"5678"],
            media_type="text/csv",
            cancel_requested=lambda: next(calls),
        )
    assert list((tmp_path / "staging").iterdir()) == []


def test_corrupted_existing_object_is_rejected_not_overwritten(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    stored = store.put_stream([b"verified"], media_type="text/csv")
    path = tmp_path / stored.object_key
    path.write_bytes(b"corrupt")

    assert not store.verify(stored.object_key, stored.sha256)
    with pytest.raises(ValueError, match="corrupt"):
        store.put_stream([b"verified"], media_type="text/csv")
    assert path.read_bytes() == b"corrupt"


def test_object_key_cannot_escape_store(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)

    assert not store.verify("../../outside", "0" * 64)
