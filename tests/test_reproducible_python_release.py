from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.build_python_release import normalize_sdist_archive


def _write_variant(path: Path, *, gzip_mtime: int, tar_mtime: int, reverse: bool) -> None:
    rows = [("package/a.txt", b"alpha"), ("package/b.txt", b"beta")]
    if reverse:
        rows.reverse()
    with path.open("wb") as raw:
        with gzip.GzipFile(filename=path.name, mode="wb", fileobj=raw, mtime=gzip_mtime) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, data in rows:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mtime = tar_mtime
                    info.uid = 1000
                    info.gid = 1000
                    info.uname = "developer"
                    info.gname = "developer"
                    archive.addfile(info, io.BytesIO(data))


class ReproduciblePythonReleaseTests(unittest.TestCase):
    def test_normalized_sdist_is_byte_identical_for_equal_content(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            normalized_first = root / "normalized-first.tar.gz"
            normalized_second = root / "normalized-second.tar.gz"
            _write_variant(first, gzip_mtime=1, tar_mtime=2, reverse=False)
            _write_variant(second, gzip_mtime=3, tar_mtime=4, reverse=True)

            normalize_sdist_archive(first, normalized_first, epoch=1767225600)
            normalize_sdist_archive(second, normalized_second, epoch=1767225600)

            self.assertEqual(
                hashlib.sha256(normalized_first.read_bytes()).hexdigest(),
                hashlib.sha256(normalized_second.read_bytes()).hexdigest(),
            )
            with tarfile.open(normalized_first, "r:gz") as archive:
                self.assertEqual(
                    [member.name for member in archive.getmembers()],
                    ["package/a.txt", "package/b.txt"],
                )
                self.assertTrue(all(member.mtime == 1767225600 for member in archive.getmembers()))


if __name__ == "__main__":
    unittest.main()
