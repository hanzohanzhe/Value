"""Capture and check the P0-6 S1 default-PSM reproduction goldens.

Commands::

    capture_native_reproduction_golden.py capture          # write the 96-period synthetic golden (never overwrites)
    capture_native_reproduction_golden.py check            # compare the frozen and the live loop with the synthetic golden
    capture_native_reproduction_golden.py revise --reason TEXT --correction-id ID [...] [--trajectory]
                                                           # append an accounting-only revision (live loop);
                                                           # --trajectory: A26 kernel corrections, once each
    capture_native_reproduction_golden.py write-head-copy  # regenerate the frozen 35aadb3 loop copy
    capture_native_reproduction_golden.py capture-e2e      # write the VALUE 101 48-period market.sqlite baseline
    capture_native_reproduction_golden.py check-e2e        # compare a fresh 48-period run with that baseline
                                                           # (until it is retired, see e2e_retirement)

``capture`` and ``capture-e2e`` record the SHA-256 of their tooling files and
refuse to run from a checkout with uncommitted changes outside those tooling
files and the fixture being written (``--allow-dirty`` overrides and is
recorded).  Provenance is verified by content, not by commit id:
:func:`find_tooling_commit` finds the commit in ``git rev-list HEAD`` whose
blobs match every recorded tooling hash (``base_commit`` is informational and
does not survive a rebase).
``capture`` and ``write-head-copy`` refuse to run unless the live kernel file is
byte-identical to the pinned 35aadb3 source (whole-file SHA-256 plus the
SHA-256 of every copied line range) and, when git and the commit are
available, ``git show 35aadb3:<kernel>`` has the same hash.  They also check
that the capture leaves the checkout unchanged: the content hash of
``gridform_core/`` (no trace files, no caches) and, when git is available, the
full ``git status --porcelain --ignored -uall`` listing are compared before and
after the runs.  The synthetic run is executed twice through the frozen loop
and once through the live loop (render_live_loop, byte-identical to the frozen
copy at 35aadb3); all three must be identical.  ``check-e2e`` gates on the
zones stored in the baseline (a zone may only become stricter).  See tests/native_reproduction_harness.py for the scenario, the
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

from gridform_validation.golden import ZONE_STRENGTH  # noqa: E402
from tests import native_reproduction_harness as harness  # noqa: E402

E2E_SCHEMA = "value.native-e2e-baseline/v1"
E2E_ARTIFACT_PREFIX = "market/market.sqlite::"
E2E_CASES = ("D3", "C3")
E2E_NOTES = [
    "P0-6 S1: VALUE 101 value_101_day (48 periods) market.sqlite of the default PSM at HEAD, for the S3 byte/value identity check.",
    "Cases are the frozen golden projects tests/golden/projects/<case>.json run through scripts/golden/run_case.py (D3: doctoral reference configuration with the legacy storage tariff; C3: default dynamic storage cost).",
    "Every table column is hashed over its rowid-ordered values (exact repr); period_summary is also kept in full. Each metadata row is keyed market/market.sqlite::metadata.<name> (plus metadata.#rows). Zones come from tests/golden/zones.json alone (the single zone authority), so every metadata row is identity like metadata.key/value in the X0 goldens; identity-zone entries and the whole-file hash are informational.",
    "This baseline has no revision path and is never rewritten. It gates only until an X0 golden of the same case (tests/golden/doctoral/D3.json or tests/golden/corrected/C3.json) takes a revision that changes a gated market/market.sqlite key (e2e_retirement); from then on X0, which has the accounting-revision and doctoral re-baseline paths, is the gate for value_101_day, and no v2 of this file is captured.",
]

# The X0 goldens of the same VALUE 101 cases.  They carry the revision path
# (accounting revisions under a correction id, doctoral trajectory
# re-baselines with the allowlist and a numeric report), so this baseline
# does not get a second one.
E2E_SUCCESSORS = {
    "D3": ROOT / "tests" / "golden" / "doctoral" / "D3.json",
    "C3": ROOT / "tests" / "golden" / "corrected" / "C3.json",
}


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


# Files that determine a capture.  Their SHA-256 at capture time is recorded
# in the fixture's source record.  A capture refuses to run from a checkout with
# uncommitted changes other than these files and the fixture being written
# (unless --allow-dirty, which is recorded), so the commit that contains exactly
# the recorded tooling (find_tooling_commit) reproduces revision 0.  The
# tooling may be uncommitted at capture time because its content is recorded:
# the capture and its tooling then land in one commit.
SYNTHETIC_TOOLING = (
    "tests/native_reproduction_harness.py",
    "scripts/capture_native_reproduction_golden.py",
    "tests/fixtures/native_psm/head_run_simulation_35aadb3.py",
    "tests/golden/zones.json",
    "gridform_validation/golden.py",
)
E2E_TOOLING = (
    "tests/native_reproduction_harness.py",
    "scripts/capture_native_reproduction_golden.py",
    "tests/golden/zones.json",
    "gridform_validation/golden.py",
    "scripts/golden/run_case.py",
    *(f"tests/golden/projects/{case}.json" for case in E2E_CASES),
)


def capture_provenance(tooling: tuple[str, ...], outputs: tuple[Path, ...], *, allow_dirty: bool) -> dict[str, Any]:
    """Tooling hashes and checkout state for the source record.

    Refuses (SystemExit) when the checkout has uncommitted or untracked
    changes other than the tooling files (whose content is recorded) and the
    fixture being written, unless ``allow_dirty``.
    """

    record: dict[str, Any] = {
        "capture_tooling": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in tooling
        },
    }
    status = _git("status", "--porcelain=v1", "-uall")
    if status is None:
        record["checkout_state"] = "unavailable"
        return record
    skipped = {output.relative_to(ROOT).as_posix() for output in outputs}
    changed = sorted(
        line[3:] for line in status.splitlines()
        if line.strip() and line[3:] not in skipped
    )
    uncommitted_tooling = [path for path in changed if path in tooling]
    dirty = [path for path in changed if path not in tooling]
    if dirty and not allow_dirty:
        raise SystemExit(
            "refusing to capture from a checkout with uncommitted changes outside the recorded tooling "
            "(commit or remove them, or pass --allow-dirty):\n  " + "\n  ".join(dirty[:20])
        )
    record["checkout_state"] = "dirty" if dirty else "clean"
    if dirty:
        record["dirty_paths"] = dirty
    if uncommitted_tooling:
        record["uncommitted_tooling"] = uncommitted_tooling
    return record


def find_tooling_commit(tooling: Mapping[str, str]) -> str | None:
    """The newest commit reachable from HEAD whose blobs match every recorded
    tooling SHA-256, or None.  Raises LookupError when git is unavailable.

    Every distinct state of the tooling paths is the tree of some commit in
    ``git rev-list HEAD -- <paths>``, so walking that list is exhaustive.
    """

    if _git("rev-parse", "--git-dir") is None:
        raise LookupError("git is not available for this checkout")
    paths = sorted(tooling)
    listing = _git("rev-list", "HEAD", "--", *paths)
    if listing is None:
        raise LookupError("git rev-list failed")
    blob_sha256: dict[str, str] = {}
    for commit in listing.split():
        tree = _git("ls-tree", "-r", commit, "--", *paths) or ""
        blobs = {}
        for line in tree.splitlines():
            meta, _, path = line.partition("\t")
            blobs[path] = meta.split()[2]
        if set(blobs) != set(paths):
            continue
        matched = True
        for path in paths:
            blob = blobs[path]
            if blob not in blob_sha256:
                try:
                    content = subprocess.run(["git", "cat-file", "blob", blob], cwd=ROOT, capture_output=True,
                                             check=True).stdout
                except (OSError, subprocess.CalledProcessError):
                    raise LookupError(f"git cat-file blob {blob} failed") from None
                blob_sha256[blob] = hashlib.sha256(content).hexdigest()
            if blob_sha256[blob] != tooling[path]:
                matched = False
                break
        if matched:
            return commit
    return None


def _guarded_tree() -> dict[str, str | None]:
    """State of the checkout that a capture must not change."""

    return {
        "gridform_core_tree_sha256": harness.tree_sha256(ROOT / "gridform_core"),
        "git_status_sha256": worktree_status_sha256(),
    }


def worktree_status_sha256(paths: tuple[str, ...] = ()) -> str | None:
    """Hash of ``git status`` including untracked and ignored files (None without git).

    ``paths`` limits the listing (``git status ... -- <paths>``); the capture
    commands, which run alone, check the whole checkout.
    """

    status = _git("status", "--porcelain=v1", "--ignored", "-uall", *(("--", *paths) if paths else ()))
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


def command_capture(arguments) -> int:
    if harness.GOLDEN_PATH.exists():
        raise SystemExit(f"{harness.GOLDEN_PATH.relative_to(ROOT)} exists; revision 0 is written once (use check or revise)")
    provenance = capture_provenance(SYNTHETIC_TOOLING, (harness.GOLDEN_PATH,), allow_dirty=arguments.allow_dirty)
    source, git_record = verified_source()
    if harness.render_head_copy(source) != harness.HEAD_COPY_PATH.read_text(encoding="utf-8"):
        raise SystemExit("the committed head copy is not the rendering of the pinned source (run write-head-copy)")
    if harness.render_live_loop(source, label=harness.HEAD_COMMIT, header=harness.HEADER) != \
            harness.HEAD_COPY_PATH.read_text(encoding="utf-8"):
        raise SystemExit("render_live_loop of the pinned source is not the frozen copy")
    before = _guarded_tree()
    first = harness.observe(loop="frozen")
    second = harness.observe(loop="frozen")
    live = harness.observe(loop="live")
    after = _guarded_tree()
    if before != after:
        raise SystemExit(f"the checkout changed during the capture: {before} -> {after}")
    for label, other in (("two frozen-loop runs", second), ("the frozen and the live loop", live)):
        differences = [
            item for case in first for item in harness.compare_columns(case, first[case], other[case], {})
        ]
        if differences:
            raise SystemExit(f"{label} differ:\n" + "\n".join(item.describe() for item in differences[:20]))
    record = _source_record({**git_record, **provenance})
    record["gridform_core_tree_sha256_before_after"] = before["gridform_core_tree_sha256"]
    record["git_status_unchanged"] = "unavailable" if before["git_status_sha256"] is None else "matched"
    golden = harness.new_golden(first, base_commit=head_commit(), source=record)
    text = harness.dump_golden(golden)
    harness.GOLDEN_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {harness.GOLDEN_PATH.relative_to(ROOT)} ({len(text.encode('utf-8'))} bytes)")
    return 0


def command_check(arguments) -> int:
    golden = harness.load_golden()
    failed = False
    for loop in arguments.loop or harness.LOOPS:
        gated = harness.gated_zones(golden, loop)
        differences = harness.compare_with_golden(golden, harness.observe(loop=loop))
        blocking = [item for item in differences if item.zone in gated]
        for item in differences[:60]:
            print(f"{loop}: {item.describe()}" + ("" if item.zone in gated else " (informational)"))
        print(f"{loop} loop: {len(differences)} column difference(s), {len(blocking)} in gated zones {list(gated)}")
        failed = failed or bool(blocking)
    print("native reproduction golden: " + ("DIFFERENT" if failed else "identical in the gated zones"))
    return 1 if failed else 0


def command_revise(arguments) -> int:
    golden = harness.load_golden()
    revised = harness.append_revision(
        golden, harness.observe(loop="live"), reason=arguments.reason,
        correction_ids=arguments.correction_id, base_commit=head_commit(), loop="live",
        trajectory=arguments.trajectory,
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
    """Zone of an e2e key: tests/golden/zones.json through harness.zone_of,
    with no rule of its own (P0_CONVENTIONS 2: zones.json is the single zone
    authority; metadata rows fall under 'market/market.sqlite::metadata.*')."""

    return harness.zone_of(key)


def e2e_entries(digest: Mapping[str, Any]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for table, payload in digest["tables"].items():
        entries[f"{E2E_ARTIFACT_PREFIX}{table}.#rows"] = payload["rows"]
        for column, value in payload["columns"].items():
            entries[f"{E2E_ARTIFACT_PREFIX}{table}.{column}"] = value
    entries[f"{E2E_ARTIFACT_PREFIX}metadata.#rows"] = len(digest["metadata"])
    for name, value in digest["metadata"].items():
        entries[f"{E2E_ARTIFACT_PREFIX}metadata.{name}"] = value
    return entries


def gate_zone(key: str, stored_zones: Mapping[str, str] | None = None) -> str:
    """Zone of ``key`` for gating: the baseline's stored zone, made stricter by
    the current rules if they say so but never weaker; current rules only for
    keys the baseline did not record."""

    current = e2e_zone(key)
    stored = (stored_zones or {}).get(key)
    if stored is None:
        return current
    return stored if ZONE_STRENGTH[stored] >= ZONE_STRENGTH[current] else current


def e2e_differences(expected: Mapping[str, Any], actual: Mapping[str, Any],
                    stored_zones: Mapping[str, str] | None = None) -> list[tuple[str, str, Any, Any]]:
    left, right = e2e_entries(expected), e2e_entries(actual)
    differences = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            differences.append((gate_zone(key, stored_zones), key, left.get(key), right.get(key)))
    return differences


def market_ledger_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    """Gated ``market/market.sqlite::`` keys whose record differs between two
    X0 digests (``revision["digest"]``).  Identity-zone keys are left out: the
    e2e baseline never gates them, so they cannot be why it would fail."""

    before, after = previous.get("columns", {}), current.get("columns", {})
    changed = []
    for key in sorted(set(before) | set(after)):
        if not key.startswith(E2E_ARTIFACT_PREFIX):
            continue
        left, right = before.get(key) or {}, after.get(key) or {}
        if (left.get("count"), left.get("sha256")) == (right.get("count"), right.get("sha256")) and left and right:
            continue
        zones = {record.get("zone") for record in (left, right) if record} | {harness.zone_of(key)}
        if zones <= {"identity"}:
            continue
        changed.append(key)
    return changed


def e2e_retirement(successors: Mapping[str, Path] | None = None) -> str | None:
    """Why the v1 e2e baseline no longer gates, or None while it does.

    The baseline is the P0-6 S3 acceptance check ('48-period market.sqlite
    identical'): S2 and S3 are behaviour-preserving, so it must hold through
    them.  The first universal correction that changes value_101_day's
    market.sqlite (P0-4 S4-S6, A2, P0-5a) revises the X0 golden of D3 or C3 in
    the same commit; a revision whose digest changes a gated
    ``market/market.sqlite::`` key compared with the previous revision retires
    this baseline for both cases.  A revision that leaves market.sqlite alone
    (planning, other artifacts, identity only) does not.  It is deliberately
    not retired by S3 itself, whose acceptance it is.
    """

    for case, path in (successors or E2E_SUCCESSORS).items():
        golden = json.loads(path.read_text(encoding="utf-8"))
        if golden.get("case") != case:
            raise ValueError(f"{path} is the X0 golden of {golden.get('case')!r}, expected {case!r}")
        revisions = golden.get("revisions", [])
        for index in range(1, len(revisions)):
            changed = market_ledger_changes(revisions[index - 1].get("digest", {}), revisions[index].get("digest", {}))
            if not changed:
                continue
            revision = revisions[index]
            why = ", ".join([*revision.get("correction_ids", []), *revision.get("findings", [])]) or "no id"
            shown = ", ".join(changed[:3]) + (f" (+{len(changed) - 3} more)" if len(changed) > 3 else "")
            return (
                f"X0 golden {case} ({path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}) revision "
                f"{revision.get('revision', index)} ({why}) changes {shown}; value_101_day is gated by the X0 "
                "goldens tests/golden/doctoral/D3.json and tests/golden/corrected/C3.json from here on"
            )
    return None


def command_capture_e2e(arguments) -> int:
    if harness.E2E_BASELINE_PATH.exists():
        raise SystemExit(f"{harness.E2E_BASELINE_PATH.relative_to(ROOT)} exists; v1 is written once")
    provenance = capture_provenance(E2E_TOOLING, (harness.E2E_BASELINE_PATH,), allow_dirty=arguments.allow_dirty)
    _, git_record = verified_source()
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
        "source": _source_record({**git_record, **provenance}),
        "zones": zones,
        "cases": cases,
    }
    harness.E2E_BASELINE_PATH.write_text(json.dumps(baseline, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {harness.E2E_BASELINE_PATH.relative_to(ROOT)}")
    return 0


def command_check_e2e(arguments) -> int:
    retired = e2e_retirement()
    if retired and not arguments.even_if_retired:
        print(f"e2e baseline retired: {retired}")
        return 0
    baseline = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
    failed = False
    with tempfile.TemporaryDirectory(prefix="p06-e2e-") as temporary:
        for case, expected in baseline["cases"].items():
            actual = run_e2e_case(case, Path(temporary))
            for zone, key, left, right in e2e_differences(expected, actual, baseline.get("zones")):
                failed = failed or zone != "identity"
                print(f"[{zone}] {case} {key}: {left!r} -> {right!r}")
    print("e2e baseline: " + ("DIFFERENT" if failed else "identical in trajectory and accounting zones"))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    dirty_help = "capture although the checkout has uncommitted changes (recorded as checkout_state 'dirty')"
    capture = commands.add_parser("capture")
    capture.add_argument("--allow-dirty", action="store_true", help=dirty_help)
    capture.set_defaults(handler=command_capture)
    check = commands.add_parser("check")
    check.add_argument("--loop", action="append", choices=harness.LOOPS,
                       help="loop(s) to check (default: frozen and live)")
    check.set_defaults(handler=command_check)
    revise = commands.add_parser("revise")
    revise.add_argument("--reason", required=True)
    revise.add_argument("--correction-id", action="append", required=True)
    revise.add_argument("--trajectory", action="store_true",
                        help="also accept trajectory changes (DECISIONS A26 kernel corrections only, once each)")
    revise.set_defaults(handler=command_revise)
    commands.add_parser("write-head-copy").set_defaults(handler=command_write_head_copy)
    capture_e2e = commands.add_parser("capture-e2e")
    capture_e2e.add_argument("--allow-dirty", action="store_true", help=dirty_help)
    capture_e2e.set_defaults(handler=command_capture_e2e)
    check_e2e = commands.add_parser("check-e2e")
    check_e2e.add_argument("--even-if-retired", action="store_true",
                           help="compare even after an X0 D3/C3 revision retired the baseline (informational)")
    check_e2e.set_defaults(handler=command_check_e2e)
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
