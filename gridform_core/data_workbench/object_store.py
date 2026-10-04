"""Content-addressed local storage for immutable official source objects."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from uuid import uuid4

from .contracts import StoredObject


class ByteLimitExceeded(ValueError):
    pass


class FetchCancelled(RuntimeError):
    pass


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.raw_root = self.root / "raw" / "sha256"
        self.staging_root = self.root / "staging"
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, object_key: str) -> Path | None:
        key = PurePosixPath(object_key)
        if key.is_absolute() or key.parts[:2] != ("raw", "sha256") or len(key.parts) != 3:
            return None
        if len(key.parts[2]) != 64 or any(char not in "0123456789abcdef" for char in key.parts[2]):
            return None
        path = (self.root / Path(*key.parts)).resolve()
        if path.parent != self.raw_root:
            return None
        return path

    def put_stream(
        self,
        blocks: Iterable[bytes],
        *,
        media_type: str,
        max_bytes: int | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> StoredObject:
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes cannot be negative")
        cancelled = cancel_requested or (lambda: False)
        staging = self.staging_root / f"fetch-{uuid4().hex}.partial"
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with staging.open("xb") as stream:
                for block in blocks:
                    if cancelled():
                        raise FetchCancelled("Fetch was cancelled before object installation")
                    if not isinstance(block, bytes):
                        raise TypeError("Object-store blocks must be bytes")
                    byte_size += len(block)
                    if max_bytes is not None and byte_size > max_bytes:
                        raise ByteLimitExceeded(
                            f"Source object exceeded configured {max_bytes}-byte limit"
                        )
                    digest.update(block)
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())

            sha256 = digest.hexdigest()
            object_key = f"raw/sha256/{sha256}"
            target = self.raw_root / sha256
            if target.exists():
                if not self.verify(object_key, sha256):
                    raise ValueError(f"Existing object {object_key} is corrupt")
                staging.unlink()
            else:
                os.replace(staging, target)
            return StoredObject(
                object_key=object_key,
                sha256=sha256,
                byte_size=byte_size,
                media_type=media_type,
            )
        finally:
            if staging.exists():
                staging.unlink()

    def verify(self, object_key: str, sha256: str) -> bool:
        path = self._path_for_key(object_key)
        if path is None or not path.is_file() or path.name != sha256:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest() == sha256
