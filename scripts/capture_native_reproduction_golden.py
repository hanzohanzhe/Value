"""Capture and check the P0-6 S1 default-PSM reproduction goldens.

Commands::

    capture_native_reproduction_golden.py capture          # write the 96-period synthetic golden (never overwrites)
    capture_native_reproduction_golden.py check            # compare the live kernel with the synthetic golden
    capture_native_reproduction_golden.py revise --reason TEXT --correction-id ID [...]
                                                           # append an accounting-only revision
    capture_native_reproduction_golden.py write-head-copy  # regenerate the frozen 35aadb3 loop copy
    capture_native_reproduction_golden.py capture-e2e      # write the VALUE 101 48-period market.sqlite baseline
    capture_native_reproduction_golden.py check-e2e        # compare a fresh 48-period run with that baseline

``capture`` and ``write-head-copy`` refuse to run unless the live kernel file is
byte-identical to the pinned 35aadb3 source (whole-file SHA-256 plus the
SHA-256 of every copied line range) and, when git and the commit are
available, ``git show 35aadb3:<kernel>`` has the same hash.  They also check
that the capture leaves the checkout unchanged: the content hash of
``gridform_core/`` (no trace files, no caches) and, when git is available, the
full ``git status --porcelain --ignored -uall`` listing are compared before and
after the runs.  The synthetic run is executed twice and must be
identical.  See tests/native_reproduction_harness.py for the scenario, the
frozen loop and the zone rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import native_reproduction_harness as harness  # noqa: E402

E2E_SCHEMA = "value.native-e2e-baseline/v1"
E2E_CASES = ("D3", "C3")
E2E_NOTES = [
    "P0-6 S1: VALUE 101 value_101_day (48 periods) market.sqlite of the default PSM at HEAD, for the S3 byte/value identity check.",
    "Cases are the frozen golden projects tests/golden/projects/<case>.json run through scripts/golden/run_case.py (D3: doctoral reference configuration with the legacy storage tariff; C3: default dynamic storage cost).",
    "Every table column is hashed over its rowid-ordered values (exact repr); period_summary is also kept in full. Zones follow tests/golden/zones.json with metadata keys classified individually; identity-zone entries and the whole-file hash are informational.",
    "Universal corrections that legitimately change these values (P0-4 accounting, P0-5a readers) re-capture as value101_baseline_48p_head_v2.json (plan M3); v1 is never rewritten.",
]


def _git(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.decode("utf-8")


def head_commit() -> str:
    return (_git("rev-parse", "HEAD") or "unknown").strip()


def verified_source() -> tuple[str, dict[str, Any]]:
    """Read the live kernel and prove it is the pinned 35aadb3 text."""

    source = harness.kernel_path().read_text(encoding="utf-8")
    harness.verify_head_source(source)
    git_text = _git("show", f"{harness.HEAD_COMMIT}:{harness.KERNEL_RELPATH}")
    git_check = "unavailable"
    if git_text is not None:
        if harness.sha256_text(git_text) != harness.HEAD_KERNEL_SHA256:
            raise SystemExit(f"git show {harness.HEAD_COMMIT}:{harness.KERNEL_RELPATH} does not have the pinned hash")
        git_check = "matched"
    return source, {"git_show_35aadb3": git_check}


def _guarded_tree() -> dict[str, str | None]:
    """State of the checkout that a capture must not change."""

    return {
        "gridform_core_tree_sha256": harness.tree_sha256(ROOT / "gridform_core"),
        "git_status_sha256": worktree_status_sha256(),
    }


def worktree_status_sha256() -> str | None:
    """Hash of ``git status`` including untracked and ignored files (None without git)."""

    status = _git("status", "--porcelain=v1", "--ignored", "-uall")
    return None if status is None else hashlib.sha256(status.encode("utf-8")).hexdigest()


def _source_record(extra: Mapping[str, Any]) -> dict[str, Any]:
    record = harness.verify_head_copy()
    record.update(extra)
    record["live_kernel_sha256_at_capture"] = harness.sha256_text(harness.kernel_path().read_text(encoding="utf-8"))
    record["runtime_compat_tree_sha256_at_capture"] = harness.tree_sha256(harness.kernel_path().parent)
    return record


def command_write_head_copy(_arguments) -> int:
    source, _ = verified_source()
    rendered = harness.render_head_copy(source)
    harness.HEAD_COPY_PATH.parent.mkdir(parents=True, exist_ok=True)
    harness.HEAD_COPY_PATH.write_text(rendered, encoding="utf-8", newline="")
    print(f"wrote {harness.HEAD_COPY_PATH.relative_to(ROOT)} ({harness.sha256_text(rendered)})")
    return 0


def command_capture(_arguments) -> int:
    if harness.GOLDEN_PATH.exists():
        raise SystemExit(f"{harness.GOLDEN_PATH.relative_to(ROOT)} exists; revision 0 is written once (use check or revise)")
    source, git_record = verified_source()
    if harness.render_head_copy(source) != harness.HEAD_COPY_PATH.read_text(encoding="utf-8"):
        raise SystemExit("the committed head copy is not the rendering of the pinned source (run write-head-copy)")
    before = _guarded_tree()
    first = harness.observe()
    second = harness.observe()
    after = _guarded_tree()
    if before != after:
        raise SystemExit(f"the checkout changed during the capture: {before} -> {after}")
    differences = [
        item for case in first for item in harness.compare_columns(case, first[case], second[case], {})
    ]
    if differences:
        raise SystemExit("two synthetic runs differ:\n" + "\n".join(item.describe() for item in differences[:20]))
    record = _source_record(git_record)
    record["gridform_core_tree_sha256_before_after"] = before["gridform_core_tree_sha256"]
    record["git_status_unchanged"] = "unavailable" if before["git_status_sha256"] is None else "matched"
    golden = harness.new_golden(first, base_commit=head_commit(), source=record)
    text = harness.dump_golden(golden)
    harness.GOLDEN_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {harness.GOLDEN_PATH.relative_to(ROOT)} ({len(text.encode('utf-8'))} bytes)")
    return 0


def command_check(_arguments) -> int:
    golden = harness.load_golden()
    differences = harness.compare_with_golden(golden, harness.observe())
    if not differences:
        print("native reproduction golden: identical")
        return 0
    for item in differences[:60]:
        print(item.describe())
    print(f"{len(differences)} column difference(s)")
    return 1


def command_revise(arguments) -> int:
    golden = harness.load_golden()
    revised = harness.append_revision(
        golden, harness.observe(), reason=arguments.reason,
        correction_ids=arguments.correction_id, base_commit=head_commit(),
    )
    harness.GOLDEN_PATH.write_text(harness.dump_golden(revised), encoding="utf-8")
    revision = revised["revisions"][-1]
    print(f"appended revision {revision['index']}: {len(revision['delta'])} column change(s)")
    for item in revision["delta"]:
        print("  " + item)
    return 0


# ---------------------------------------------------------------------------
# VALUE 101 48-period end-to-end baseline
# ---------------------------------------------------------------------------


def _column_hash(values: list[Any]) -> str:
    return hashlib.sha256(json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def market_digest(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        tables: dict[str, Any] = {}
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        metadata: dict[str, Any] = {}
        period_summary: dict[str, list[Any]] = {}
        for table in names:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            rows = connection.execute(
                f'SELECT {", ".join(chr(34) + c + chr(34) for c in columns)} FROM "{table}" ORDER BY rowid'
            ).fetchall()
            if table == "metadata":
                metadata = {str(key): value for key, value in rows}
                continue
            tables[table] = {
                "rows": len(rows),
                "columns": {column: _column_hash([row[index] for row in rows]) for index, column in enumerate(columns)},
            }
            if table == "period_summary":
                period_summary = {column: [row[index] for row in rows] for index, column in enumerate(columns)}
    finally:
        connection.close()
    return {
        "file_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "tables": tables,
        "metadata": metadata,
        "period_summary": period_summary,
    }


def run_e2e_case(case: str, workdir: Path) -> dict[str, Any]:
    output = workdir / case
    completed = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "golden" / "run_case.py"), case, "--keep-output", str(output)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(f"golden case {case} failed:\n{completed.stderr[-4000:]}")
    return market_digest(output / "market" / "market.sqlite")


def e2e_zone(key: str) -> str:
    """Zone of an ``market/market.sqlite::<table>.<column>`` or metadata key."""

    if key.startswith("market/market.sqlite::metadata["):
        name = key[len("market/market.sqlite::metadata["):-1]
        if name in {"schema_version", "psm_module_version"} or name.endswith("_version"):
            return "identity"
        return "accounting"
    return harness.zone_of(key)


def e2e_entries(digest: Mapping[str, Any]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for table, payload in digest["tables"].items():
        entries[f"market/market.sqlite::{table}.#rows"] = payload["rows"]
        for column, value in payload["columns"].items():
            entries[f"market/market.sqlite::{table}.{column}"] = value
    for key, value in digest["metadata"].items():
        entries[f"market/market.sqlite::metadata[{key}]"] = value
    return entries


def e2e_differences(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[tuple[str, str, Any, Any]]:
    left, right = e2e_entries(expected), e2e_entries(actual)
    differences = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            differences.append((e2e_zone(key), key, left.get(key), right.get(key)))
    return differences


def command_capture_e2e(_arguments) -> int:
    if harness.E2E_BASELINE_PATH.exists():
        raise SystemExit(f"{harness.E2E_BASELINE_PATH.relative_to(ROOT)} exists; v1 is written once")
    verified_source()
    before = _guarded_tree()
    with tempfile.TemporaryDirectory(prefix="p06-e2e-") as temporary:
        cases = {case: run_e2e_case(case, Path(temporary) / "first") for case in E2E_CASES}
        repeat = {case: run_e2e_case(case, Path(temporary) / "second") for case in E2E_CASES}
    after = _guarded_tree()
    if after != before:
        raise SystemExit(f"the checkout changed during the capture: {before} -> {after}")
    for case in E2E_CASES:
        if cases[case] != repeat[case]:
            raise SystemExit(f"two runs of {case} differ")
    zones = {key: e2e_zone(key) for case in cases.values() for key in e2e_entries(case)}
    baseline = {
        "schema_version": E2E_SCHEMA,
        "id": "value101_baseline_48p_head_v1",
        "notes": E2E_NOTES,
        "base_commit": head_commit(),
        "source": _source_record({}),
        "zones": zones,
        "cases": cases,
    }
    harness.E2E_BASELINE_PATH.write_text(json.dumps(baseline, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {harness.E2E_BASELINE_PATH.relative_to(ROOT)}")
    return 0


def command_check_e2e(_arguments) -> int:
    baseline = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
    failed = False
    with tempfile.TemporaryDirectory(prefix="p06-e2e-") as temporary:
        for case, expected in baseline["cases"].items():
            for zone, key, left, right in e2e_differences(expected, run_e2e_case(case, Path(temporary))):
                failed = failed or zone != "identity"
                print(f"[{zone}] {case} {key}: {left!r} -> {right!r}")
    print("e2e baseline: " + ("DIFFERENT" if failed else "identical in trajectory and accounting zones"))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capture").set_defaults(handler=command_capture)
    commands.add_parser("check").set_defaults(handler=command_check)
    revise = commands.add_parser("revise")
    revise.add_argument("--reason", required=True)
    revise.add_argument("--correction-id", action="append", required=True)
    revise.set_defaults(handler=command_revise)
    commands.add_parser("write-head-copy").set_defaults(handler=command_write_head_copy)
    commands.add_parser("capture-e2e").set_defaults(handler=command_capture_e2e)
    commands.add_parser("check-e2e").set_defaults(handler=command_check_e2e)
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
