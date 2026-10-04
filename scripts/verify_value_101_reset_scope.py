"""Exercise the real VALUE 101 reset API against an isolated temporary state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from backend import server


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@contextmanager
def _isolated_server(state: Path) -> Iterator[str]:
    names = {
        "STATE_ROOT": state,
        "PACKS_ROOT": state / "data-packs",
        "PROJECTS_ROOT": state / "projects",
        "RUNS_ROOT": state / "runs",
        "TRASH_ROOT": state / "trash",
    }
    previous = {name: getattr(server, name) for name in names}
    old_data_home = os.environ.get("VALUE_DATA_HOME")
    try:
        for name, value in names.items():
            setattr(server, name, value)
        os.environ["VALUE_DATA_HOME"] = str(state)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=10)
    finally:
        for name, value in previous.items():
            setattr(server, name, value)
        if old_data_home is None:
            os.environ.pop("VALUE_DATA_HOME", None)
        else:
            os.environ["VALUE_DATA_HOME"] = old_data_home


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), "utf-8")


def verify_reset_scope() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="value-101-reset-verification-") as temporary:
        state = Path(temporary).resolve()
        guided = {
            "extensions": {
                "value_101": {
                    "origin": "guided-course",
                    "course_revision": "value-101/v1",
                    "variant_kind": "baseline",
                }
            }
        }
        value_study = state / "projects" / "value-study" / "project.json"
        value_run = state / "runs" / "value-run" / "status.json"
        _write_json(value_study, {"id": "value-study", **guided})
        _write_json(value_run, {"id": "value-run", "status": "completed", **guided})

        sentinels = [
            state / "projects" / "ordinary-study" / "project.json",
            state / "runs" / "ordinary-run" / "status.json",
            state / "data-packs" / "ordinary-pack" / "manifest.json",
            state / "module-workbench" / "ordinary-module" / "module.json",
            state / "settings" / "user-preferences.json",
        ]
        for index, path in enumerate(sentinels):
            _write_json(path, {"sentinel": index, "path": path.relative_to(state).as_posix()})
        before_hashes = {
            path.relative_to(state).as_posix(): _sha256(path) for path in sentinels
        }
        before_tree = _tree_sha256(state, sentinels)

        with _isolated_server(state) as origin:
            request = urllib.request.Request(
                origin + "/api/tutorials/value-101/reset",
                method="POST",
                data=json.dumps({"confirm": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                api_status = response.status
                api_payload = json.loads(response.read().decode("utf-8"))

        after_hashes = {
            path.relative_to(state).as_posix(): _sha256(path)
            for path in sentinels
            if path.is_file()
        }
        after_tree = _tree_sha256(state, sentinels) if len(after_hashes) == len(sentinels) else ""
        trash_location = Path(str(api_payload.get("trash_location") or ""))
        trash_members = sorted(
            path for path in trash_location.rglob("*") if path.is_file()
        ) if trash_location.is_dir() else []
        trash_hashes = {
            path.relative_to(trash_location).as_posix(): _sha256(path)
            for path in trash_members
        }
        expected_trash = {
            "studies/value-study/project.json",
            "runs/value-run/status.json",
            "study-records/value-study.json",
            "trash-record.json",
        }
        unrelated_unchanged = before_hashes == after_hashes and before_tree == after_tree
        passed = all((
            api_status == 200,
            api_payload.get("ok") is True,
            api_payload.get("recoverable") is True,
            expected_trash.issubset(trash_hashes),
            not value_study.exists(),
            not value_run.exists(),
            unrelated_unchanged,
        ))
        return {
            "schema_version": "value.101-reset-verification/v1",
            "passed": bool(passed),
            "api_exercised": True,
            "api_status": api_status,
            "unrelated_state_unchanged": unrelated_unchanged,
            "unrelated_tree_sha256_before": before_tree,
            "unrelated_tree_sha256_after": after_tree,
            "unrelated_member_sha256_before": before_hashes,
            "unrelated_member_sha256_after": after_hashes,
            "deleted_study_ids": list(api_payload.get("deleted_study_ids") or []),
            "deleted_run_ids": list(api_payload.get("deleted_run_ids") or []),
            "recoverable": api_payload.get("recoverable") is True,
            "trash_member_sha256": trash_hashes,
            "temporary_state_retained": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"reset_scope": verify_reset_scope()}
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, "utf-8")
    print(encoded, end="")
    return 0 if report["reset_scope"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
