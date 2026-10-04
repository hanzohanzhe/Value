"""P0 construction gate: ``python -B scripts/p0_gate.py quick|full|nightly``.

Tiers (plan X0 3.3):

quick   every commit   (<= 10 min on the reference host, >= 1 GB free)
full    before a package merges  (>= 1.5 GB free)
nightly every milestone           (>= 2 GB free)

Each step reports passed / failed / skipped with timing; the JSON report is
written to ``<tmp>/p0-gate-report.json`` (or ``--report``).  Steps whose
machinery arrives in later X0 steps or packages are skipped with the reason
until their entry point exists, so the gate grows without being rewritten.

Guard rails: refuses to run when VALUE_DATA_HOME, TMPDIR or the report path
lies inside the managed install, never starts services on ports 8766/8800,
and every Python subprocess runs with -B and PYTHONDONTWRITEBYTECODE=1.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
TIERS = ("quick", "full", "nightly")
DISK_MINIMUM_BYTES = {"quick": 1 * 1024**3, "full": int(1.5 * 1024**3), "nightly": 2 * 1024**3}
FORBIDDEN_PORTS = ("8766", "8800")
ESLINT_BASELINE = ROOT / "tests" / "baselines" / "eslint-baseline.json"
ESLINT_SCHEMA = "value.eslint-ratchet/v2"
# Anchor of the append-only rules (plan 3.9): the M0 commit that fixed golden
# revision 0, the frozen golden projects and the ratchet baselines.  Moving it
# is an integrator decision recorded in the commit message, never a lane's.
APPEND_ONLY_BASE = "8336d1881680678917c02ca32f4fce5a9c036f5f"
GOLDEN_FAMILY_DIRS = ("tests/golden/doctoral", "tests/golden/corrected")
GOLDEN_PROJECT_DIR = "tests/golden/projects"
RATCHET_BASELINE_FILES = (
    "tests/baselines/known-failures-linux-py310.txt",
    "tests/baselines/known-failures-pytest-linux-py310.txt",
)
QUARANTINE_FILE = "tests/baselines/quarantine.txt"
ESLINT_BASELINE_FILE = "tests/baselines/eslint-baseline.json"
UNQUARANTINABLE_MODULE_PREFIX = "test_golden"
NODE_TEST_EXCLUDE = {"rendered-html.test.mjs"}  # needs a production build; F1-11
HTTP_HARNESS_PATTERN = re.compile(r"ThreadingHTTPServer\(\s*\(\s*[\"']127\.0\.0\.1[\"']\s*,\s*0\s*\)\s*,\s*server\.Handler\s*\)")
FRONTEND_PREFIXES = ("app/", "e2e/", "tsconfig", "eslint.config", "package.json")


def _load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RATCHET = _load_script("run_backend_tests", "scripts/run_backend_tests.py")


# --------------------------------------------------------------------------
# helpers


def python_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ)
    environment.setdefault("PYTHONPYCACHEPREFIX", str(Path(tempfile.gettempdir()) / "value-gate-pycache"))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ROOT)
    if extra:
        environment.update(extra)
    return environment


def node_executable() -> str | None:
    configured = os.environ.get("VALUE_NODE")
    if configured:
        return configured
    found = shutil.which("node")
    if found:
        return found
    installed = RATCHET.installed_root()
    if installed is not None and (installed / "runtime" / "node" / "bin" / "node").is_file():
        return str(installed / "runtime" / "node" / "bin" / "node")
    return None


def run(command: Sequence[str], *, timeout: float = 3600, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    for part in command:
        for port in FORBIDDEN_PORTS:
            if re.search(rf"(^|[:=]){port}($|/)", str(part)):
                raise SystemExit(f"p0_gate refuses a command that names port {port}: {command}")
    return subprocess.run(
        list(command),
        cwd=ROOT,
        env=environment or python_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def changed_files(reference: str | None) -> set[str] | None:
    if not reference:
        return None
    committed = run(["git", "diff", "--name-only", f"{reference}...HEAD"]).stdout.split()
    working = run(["git", "diff", "--name-only", "HEAD"]).stdout.split()
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.split()
    return set(committed) | set(working) | set(untracked)


def added_files(reference: str | None) -> set[str]:
    if not reference:
        return set()
    committed = run(["git", "diff", "--name-only", "--diff-filter=A", f"{reference}...HEAD"]).stdout.split()
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.split()
    return set(committed) | set(untracked)


class Step:
    def __init__(self, name: str, function: Callable[["Gate"], dict[str, Any]]) -> None:
        self.name = name
        self.function = function


class Gate:
    def __init__(self, tier: str, arguments: argparse.Namespace) -> None:
        self.tier = tier
        self.arguments = arguments
        self.python = arguments.python
        self.changed = changed_files(arguments.changed_since)
        self.results: list[dict[str, Any]] = []

    def execute(self, steps: Iterable[Step]) -> None:
        for step in steps:
            if step.name in (self.arguments.skip or []):
                self.results.append({"step": step.name, "status": "skipped", "detail": "skipped by --skip", "seconds": 0})
                continue
            started = time.monotonic()
            try:
                outcome = step.function(self)
            except subprocess.TimeoutExpired as exc:
                outcome = {"status": "failed", "detail": f"timeout after {exc.timeout} s"}
            except Exception as exc:  # noqa: BLE001 - a crashing step is a failed step
                outcome = {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
            outcome["step"] = step.name
            outcome["seconds"] = round(time.monotonic() - started, 2)
            self.results.append(outcome)
            if not self.arguments.quiet:
                print(f"[p0_gate] {step.name}: {outcome['status']} ({outcome['seconds']} s)", file=sys.stderr)


def _status(ok: bool, detail: Any = None, **extra: Any) -> dict[str, Any]:
    return {"status": "passed" if ok else "failed", "detail": detail, **extra}


def _skipped(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "detail": reason}


def _tail(text: str, limit: int = 3000) -> str:
    return text[-limit:]


# --------------------------------------------------------------------------
# steps


def step_guard(gate: Gate) -> dict[str, Any]:
    installed = RATCHET.installed_root()
    paths = [os.environ.get("VALUE_DATA_HOME"), tempfile.gettempdir(), gate.arguments.report]
    RATCHET.refuse_installed_paths([path for path in paths if path], installed)
    try:
        RATCHET.refuse_installed_paths([ROOT], installed)
    except SystemExit:
        return _status(False, "the gate must run in a source checkout, not inside the managed install")
    free = shutil.disk_usage(tempfile.gettempdir()).free
    minimum = DISK_MINIMUM_BYTES[gate.tier]
    return _status(free >= minimum, {"free_bytes": free, "minimum_bytes": minimum, "installed_root": str(installed) if installed else None})


def step_release_manifest(gate: Gate) -> dict[str, Any]:
    completed = run([gate.python, "-B", "scripts/refresh_source_release_manifest.py", "--check"])
    return _status(completed.returncode == 0, _tail(completed.stdout))


def local_path_needles(root: Path = ROOT) -> list[bytes]:
    needles = [str(root.resolve())]
    home = Path.home()
    if len(home.parts) >= 3:  # never a bare "/" or "/home"
        needles.append(str(home))
    return [needle.encode("utf-8") for needle in dict.fromkeys(needles)]


def local_path_leaks(relative_paths: Iterable[str], root: Path = ROOT) -> list[str]:
    """Release members whose bytes contain this checkout's or the user's home path."""

    needles = local_path_needles(root)
    leaks = []
    for relative in relative_paths:
        path = root / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        if any(needle in data for needle in needles):
            leaks.append(relative)
    return leaks


def step_release_path_hygiene(gate: Gate) -> dict[str, Any]:
    manifest = json.loads((ROOT / "source-release-manifest.json").read_text(encoding="utf-8"))
    leaks = local_path_leaks(manifest.get("include", []))
    return _status(not leaks, {"leaks": leaks, "rule": "no public release file may contain a local absolute path"})


def step_methodology_catalog(gate: Gate) -> dict[str, Any]:
    script = ROOT / "scripts" / "check_methodology_catalog.py"
    if not script.is_file():
        return _skipped("methodology catalogue arrives with X0 S8")
    completed = run([gate.python, "-B", str(script)])
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


def step_runtime_overlay(gate: Gate) -> dict[str, Any]:
    script = ROOT / "scripts" / "seal_runtime_overlay.py"
    if not script.is_file():
        return _skipped("RUNTIME_OVERLAY v2 sealing arrives with X0 S5")
    completed = run([gate.python, "-B", str(script), "--verify"])
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


def step_version_ledger(gate: Gate) -> dict[str, Any]:
    script = ROOT / "scripts" / "check_version_ledger.py"
    if not script.is_file():
        return _skipped("docs/release/VERSION_LEDGER.json check not present")
    completed = run([gate.python, "-B", str(script)])
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


def step_backend_ratchet(gate: Gate) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="value-gate-ratchet-") as folder:
        report = Path(folder) / "ratchet.json"
        command = [gate.python, "-B", "scripts/run_backend_tests.py", "--json-output", str(report)]
        if gate.arguments.jobs:
            command += ["--jobs", str(gate.arguments.jobs)]
        completed = run(command, timeout=3600)
        payload = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    summary = {key: payload.get(key) for key in ("ids", "failing", "baseline_size", "new_failures", "fixed_but_listed", "flaky", "expired_quarantine", "fingerprint_differences", "wall_seconds")}
    return _status(completed.returncode == 0 and payload.get("passed", False), summary or _tail(completed.stderr))


def step_pytest_ratchet(gate: Gate) -> dict[str, Any]:
    completed = run([gate.python, "-B", "scripts/run_backend_tests.py", "--pytest"], timeout=3600)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"raw": _tail(completed.stdout + completed.stderr)}
    if payload.get("status") == "not_run":
        return {"status": "skipped", "detail": f"pytest unavailable; {payload.get('not_run_count')} pytest-style ids not run"}
    return _status(completed.returncode == 0, payload)


def step_golden_bookkeeping(gate: Gate) -> dict[str, Any]:
    completed = run([gate.python, "-B", "scripts/golden/capture.py", "validate"])
    return _status(completed.returncode == 0, _tail(completed.stdout))


def _golden_tier(gate: Gate, tier: str) -> dict[str, Any]:
    cases = json.loads((ROOT / "tests" / "golden" / "cases.json").read_text(encoding="utf-8"))["cases"]
    selected = sorted(name for name, case in cases.items() if case["tier"] == tier)
    if not selected:
        return _skipped(f"no {tier} golden cases")
    completed = run([gate.python, "-B", "scripts/golden/capture.py", "check", "--cases", *selected], timeout=7200)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"raw": _tail(completed.stdout + completed.stderr)}
    return _status(completed.returncode == 0, payload)


def step_golden_full(gate: Gate) -> dict[str, Any]:
    return _golden_tier(gate, "full")


def step_golden_nightly(gate: Gate) -> dict[str, Any]:
    return _golden_tier(gate, "nightly")


def step_node_tests(gate: Gate) -> dict[str, Any]:
    node = node_executable()
    if node is None:
        return _status(False, "node executable not found (set VALUE_NODE)")
    files = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("*.test.mjs") if path.name not in NODE_TEST_EXCLUDE)
    completed = run([node, "--test", *files], timeout=900)
    counts = dict(re.findall(r"^# (pass|fail) (\d+)", completed.stdout, flags=re.MULTILINE))
    return _status(completed.returncode == 0, {"files": files, "counts": counts, "tail": "" if completed.returncode == 0 else _tail(completed.stdout)})


def http_harness_violations(paths: Iterable[str], root: Path = ROOT) -> list[str]:
    violations = []
    for name in sorted(paths):
        if not (name.startswith("tests/") and name.endswith(".py")):
            continue
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if HTTP_HARNESS_PATTERN.search(text) and "local_api_harness" not in text:
            violations.append(name)
    return violations


def step_http_harness(gate: Gate) -> dict[str, Any]:
    reference = gate.arguments.changed_since or gate.arguments.base
    violations = http_harness_violations(added_files(reference))
    return _status(not violations, {"reference": reference, "violations": violations,
                                    "rule": "new HTTP tests start the API through tests/local_api_harness.start_local_api (C14)"})


def _frontend_changed(gate: Gate) -> bool:
    if gate.changed is None:
        return True
    return any(name.startswith(FRONTEND_PREFIXES) for name in gate.changed)


def step_typecheck(gate: Gate) -> dict[str, Any]:
    if not _frontend_changed(gate):
        return _skipped("no frontend change since --changed-since")
    node = node_executable()
    if node is None:
        return _status(False, "node executable not found")
    completed = run([node, "node_modules/typescript/bin/tsc", "-p", "tsconfig.frontend.json"], timeout=900)
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


_ABSOLUTE_PATH = re.compile(r"(?<![\w:/.\\])(?:[A-Za-z]:[\\/]|/)(?:[^\s:'\"`()]+[\\/])+([^\s:'\"`()]+)")
_LINE_COLUMN = re.compile(r":\d+(?::\d+)?\b")


def eslint_message_key(message: str, root: Path | str = ROOT) -> str:
    """Location-independent ratchet text for one ESLint message.

    Only the first line is kept (rules such as react-hooks/set-state-in-effect
    append a code frame), the checkout root and any other absolute path are
    reduced to their last component, and ``:line[:col]`` suffixes are dropped,
    so the key is the same in every worktree and survives edits that only move
    the offending line.
    """

    text = str(message).splitlines()[0] if str(message) else ""
    root_text = str(root).rstrip("/\\")
    if root_text:
        text = text.replace(root_text + "/", "").replace(root_text + "\\", "").replace(root_text, "")
    text = _ABSOLUTE_PATH.sub(lambda match: match.group(1), text)
    text = _LINE_COLUMN.sub("", text)
    return " ".join(text.split())


def eslint_counts(messages: Iterable[dict[str, Any]], root: Path | str = ROOT) -> dict[str, int]:
    """Count findings per ``[relative file, ruleId, normalised first line]``."""

    counts: collections.Counter[str] = collections.Counter()
    for row in messages:
        key = [row["file"], row.get("ruleId"), eslint_message_key(row["message"], root)]
        counts[json.dumps(key, ensure_ascii=False)] += 1
    return dict(sorted(counts.items()))


def compare_eslint(baseline: dict[str, int], current: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
    increased = [
        {"key": json.loads(key), "baseline": baseline.get(key, 0), "current": count}
        for key, count in current.items()
        if count > baseline.get(key, 0)
    ]
    decreased = [
        {"key": json.loads(key), "baseline": count, "current": current.get(key, 0)}
        for key, count in baseline.items()
        if current.get(key, 0) < count
    ]
    return {"increased": increased, "decreased": decreased}


def run_eslint(node: str) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="value-gate-eslint-") as folder:
        output = Path(folder) / "eslint.json"
        run([node, "node_modules/eslint/bin/eslint.js", ".", "--ignore-pattern", "dist", "--ignore-pattern", ".next", "-f", "json", "-o", str(output)], timeout=1800)
        payload = json.loads(output.read_text(encoding="utf-8"))
    messages = []
    for entry in payload:
        relative = Path(entry["filePath"]).resolve().relative_to(ROOT).as_posix()
        for message in entry["messages"]:
            messages.append({"file": relative, "ruleId": message.get("ruleId"), "message": message["message"], "severity": message.get("severity")})
    return messages


def step_eslint(gate: Gate) -> dict[str, Any]:
    if not _frontend_changed(gate):
        return _skipped("no frontend change since --changed-since")
    node = node_executable()
    if node is None:
        return _status(False, "node executable not found")
    current = eslint_counts(run_eslint(node))
    if gate.arguments.update_eslint_baseline:
        baseline = load_eslint_baseline() if ESLINT_BASELINE.is_file() else {}
        difference = compare_eslint(baseline, current)
        if difference["increased"] and ESLINT_BASELINE.is_file():
            return _status(False, {"refused": "the ESLint baseline may only shrink", **difference})
        write_eslint_baseline(current)
        return _status(True, {"updated": True, **difference})
    if not ESLINT_BASELINE.is_file():
        return _status(False, "tests/baselines/eslint-baseline.json is missing")
    baseline = load_eslint_baseline()
    difference = compare_eslint(baseline, current)
    ok = not difference["increased"] and not difference["decreased"]
    return _status(ok, {**difference, "hint": None if ok else "fix new findings; after fixing old ones run --update-eslint-baseline"})


def load_eslint_baseline(path: Path = ESLINT_BASELINE, root: Path | str = ROOT) -> dict[str, int]:
    """Baseline counts re-keyed with :func:`eslint_message_key` (reads v1 and v2)."""

    return eslint_baseline_counts(path.read_text(encoding="utf-8"), root)


def eslint_baseline_counts(text: str, root: Path | str = ROOT) -> dict[str, int]:
    payload = json.loads(text)
    counts: collections.Counter[str] = collections.Counter()
    for key, count in payload["counts"].items():
        file_name, rule, message = json.loads(key)
        counts[json.dumps([file_name, rule, eslint_message_key(message, root)], ensure_ascii=False)] += int(count)
    return dict(sorted(counts.items()))


def write_eslint_baseline(counts: dict[str, int]) -> None:
    ESLINT_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ESLINT_SCHEMA,
        "command": "eslint . --ignore-pattern dist --ignore-pattern .next",
        "key": "[relative file, ruleId, first message line without absolute paths or :line:col] -> count",
        "counts": counts,
    }
    ESLINT_BASELINE.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# append-only rules for goldens and baselines (plan 3.9 hotspot rules)


def _listed_ids(text: str) -> set[str]:
    ids = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        identifier = line.split("|", 1)[0].split("#", 1)[0].strip()
        if identifier:
            ids.add(identifier)
    return ids


def _quarantine_expiries(text: str) -> dict[str, str]:
    expiries = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        fields = dict(part.partition("=")[::2] for part in parts[1:])
        expiries[parts[0]] = fields.get("expires", "").strip()
    return expiries


def _expiry_rank(expires: str) -> int:
    if expires in RATCHET.MILESTONES:
        return RATCHET.MILESTONES.index(expires)
    return len(RATCHET.MILESTONES)  # host (permanent) or malformed: the latest


def _test_module(identifier: str) -> str:
    for prefix in ("IMPORT:", "CRASH:", "TIMEOUT:"):
        if identifier.startswith(prefix):
            identifier = identifier[len(prefix):]
    return identifier.split("::", 1)[0].rsplit("/", 1)[-1].split(".", 1)[0]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def append_only_violations(
    read_base: Callable[[str], str | None],
    read_head: Callable[[str], str | None],
    base_golden_paths: Iterable[str],
    base_project_paths: Iterable[str] = (),
) -> list[str]:
    """Violations of: goldens append-only, frozen projects immutable, ratchet
    baselines and quarantine only shrink.

    ``read_base``/``read_head`` return a file's text (``None`` when absent).
    """

    violations: list[str] = []
    for path in sorted(base_golden_paths):
        base_text = read_base(path)
        if base_text is None:
            continue
        head_text = read_head(path)
        if head_text is None:
            violations.append(f"{path}: golden file deleted")
            continue
        base, head = json.loads(base_text), json.loads(head_text)
        for field in ("schema_version", "family", "case"):
            if base.get(field) != head.get(field):
                violations.append(f"{path}: header field {field!r} changed")
        base_revisions, head_revisions = base.get("revisions") or [], head.get("revisions") or []
        if len(head_revisions) < len(base_revisions):
            violations.append(f"{path}: revisions removed ({len(base_revisions)} -> {len(head_revisions)})")
        for index, revision in enumerate(base_revisions[: len(head_revisions)]):
            if _canonical(revision) != _canonical(head_revisions[index]):
                violations.append(f"{path}: revision {index} was rewritten (golden files are append-only)")

    for path in sorted(base_project_paths):
        base_text = read_base(path)
        if base_text is not None and read_head(path) != base_text:
            violations.append(f"{path}: frozen golden project changed or deleted (snapshots are immutable)")

    for path in RATCHET_BASELINE_FILES:
        base_text, head_text = read_base(path), read_head(path)
        head_ids = _listed_ids(head_text or "")
        added = sorted(head_ids - _listed_ids(base_text or ""))
        if added:
            violations.append(f"{path}: {len(added)} id(s) added (the baseline only shrinks): {added[:5]}")
        golden_ids = sorted(identifier for identifier in head_ids if _test_module(identifier).startswith(UNQUARANTINABLE_MODULE_PREFIX))
        if golden_ids:
            violations.append(f"{path}: golden tests may never be baselined: {golden_ids}")

    base_quarantine = _quarantine_expiries(read_base(QUARANTINE_FILE) or "")
    head_quarantine = _quarantine_expiries(read_head(QUARANTINE_FILE) or "")
    added = sorted(set(head_quarantine) - set(base_quarantine))
    if added:
        violations.append(f"{QUARANTINE_FILE}: {len(added)} id(s) added (quarantine only shrinks): {added[:5]}")
    extended = sorted(
        identifier
        for identifier in set(head_quarantine) & set(base_quarantine)
        if _expiry_rank(head_quarantine[identifier]) > _expiry_rank(base_quarantine[identifier])
    )
    if extended:
        violations.append(f"{QUARANTINE_FILE}: expiry moved later for {extended[:5]}")
    golden_ids = sorted(identifier for identifier in head_quarantine if _test_module(identifier).startswith(UNQUARANTINABLE_MODULE_PREFIX))
    if golden_ids:
        violations.append(f"{QUARANTINE_FILE}: golden tests may never be quarantined: {golden_ids}")

    base_eslint, head_eslint = read_base(ESLINT_BASELINE_FILE), read_head(ESLINT_BASELINE_FILE)
    if head_eslint is not None:
        base_counts = eslint_baseline_counts(base_eslint) if base_eslint is not None else {}
        grown = compare_eslint(base_counts, eslint_baseline_counts(head_eslint))["increased"]
        if grown:
            violations.append(f"{ESLINT_BASELINE_FILE}: {len(grown)} key(s) grew (the ESLint baseline only shrinks)")
    return violations


def step_append_only(gate: Gate) -> dict[str, Any]:
    if run(["git", "rev-parse", "--git-dir"]).returncode != 0:
        return _skipped("not a git checkout")
    base = gate.arguments.append_base
    resolved = run(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"])
    if resolved.returncode != 0:
        return _status(False, f"append-only base {base} is not a commit in this repository")
    commit = resolved.stdout.strip()
    if run(["git", "merge-base", "--is-ancestor", commit, "HEAD"]).returncode != 0:
        return _status(False, f"append-only base {commit} is not an ancestor of HEAD")

    def read_base(path: str) -> str | None:
        shown = run(["git", "show", f"{commit}:{path}"])
        return shown.stdout if shown.returncode == 0 else None

    def read_head(path: str) -> str | None:
        target = ROOT / path
        return target.read_text(encoding="utf-8") if target.is_file() else None

    listed = run(["git", "ls-tree", "-r", "--name-only", commit, "--", *GOLDEN_FAMILY_DIRS]).stdout.split()
    projects = run(["git", "ls-tree", "-r", "--name-only", commit, "--", GOLDEN_PROJECT_DIR]).stdout.split()
    violations = append_only_violations(
        read_base, read_head, [path for path in listed if path.endswith(".json")], projects
    )
    return _status(not violations, {"base": commit, "golden_files": len(listed), "frozen_projects": len(projects),
                                    "violations": violations})


def step_reference_tables(gate: Gate) -> dict[str, Any]:
    completed = run([gate.python, "-B", "scripts/generate_reference_tables.py", "--check"])
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


SOURCE_SCOPE_CHECKS = ("source_path", "source_hash", "source_name", "source_manifest")


def step_publication_scope(gate: Gate) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="value-gate-scope-") as folder:
        report = Path(folder) / "scope.json"
        run([gate.python, "-B", "scripts/check_publication_scope.py", "--report", str(report)])
        payload = json.loads(report.read_text(encoding="utf-8"))
    errors = [row for row in payload.get("errors", []) if str(row.get("check", "")).split(":", 1)[0] in SOURCE_SCOPE_CHECKS]
    other = [row for row in payload.get("errors", []) if row not in errors]
    return _status(not errors, {"source_errors": errors, "ignored_non_source_errors": other})


def step_e2e_offline(gate: Gate) -> dict[str, Any]:
    command = os.environ.get("VALUE_P0_E2E_COMMAND")
    if not os.environ.get("VALUE_E2E_CHROMIUM") or not command:
        return _skipped("offline e2e needs VALUE_E2E_CHROMIUM and VALUE_P0_E2E_COMMAND (infrastructure: P0-9 S0)")
    completed = run(command.split(), timeout=3600, environment=python_environment({"VALUE_E2E_UI_ONLY": "1"}))
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


def step_energy_balance(gate: Gate) -> dict[str, Any]:
    script = ROOT / "scripts" / "check_energy_balance_invariant.py"
    if not script.is_file():
        return _skipped("corrected-profile energy-balance invariant arrives with P0-4")
    completed = run([gate.python, "-B", str(script)], timeout=3600)
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


def step_validation_oracles(gate: Gate) -> dict[str, Any]:
    script = ROOT / "scripts" / "run_p0_validation_oracles.py"
    if not script.is_file():
        return _skipped("validation_24h/168h independent-oracle runs are wired in after X0 S6/P0-4")
    completed = run([gate.python, "-B", str(script)], timeout=7200)
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


def step_golden_sensitivity(gate: Gate) -> dict[str, Any]:
    script = ROOT / "scripts" / "golden" / "sensitivity.py"
    if not script.is_file():
        return _skipped("golden sensitivity needs the methodology profiles (X0 S8)")
    completed = run([gate.python, "-B", str(script)], timeout=7200)
    return _status(completed.returncode == 0, _tail(completed.stdout + completed.stderr))


QUICK_STEPS = [
    Step("guard", step_guard),
    Step("release_manifest", step_release_manifest),
    Step("release_path_hygiene", step_release_path_hygiene),
    Step("methodology_catalog", step_methodology_catalog),
    Step("runtime_overlay", step_runtime_overlay),
    Step("version_ledger", step_version_ledger),
    Step("golden_bookkeeping", step_golden_bookkeeping),
    Step("append_only", step_append_only),
    Step("backend_ratchet", step_backend_ratchet),
    Step("node_tests", step_node_tests),
    Step("http_harness", step_http_harness),
    Step("typecheck_frontend", step_typecheck),
    Step("eslint_ratchet", step_eslint),
]
FULL_STEPS = QUICK_STEPS + [
    Step("pytest_ratchet", step_pytest_ratchet),
    Step("golden_full", step_golden_full),
    Step("reference_tables", step_reference_tables),
    Step("publication_scope", step_publication_scope),
    Step("e2e_offline", step_e2e_offline),
    Step("energy_balance", step_energy_balance),
]
NIGHTLY_STEPS = FULL_STEPS + [
    Step("golden_nightly", step_golden_nightly),
    Step("validation_oracles", step_validation_oracles),
    Step("golden_sensitivity", step_golden_sensitivity),
]
STEPS = {"quick": QUICK_STEPS, "full": FULL_STEPS, "nightly": NIGHTLY_STEPS}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tier", choices=TIERS)
    parser.add_argument("--changed-since", help="git ref; frontend checks run only when app/ etc. changed")
    parser.add_argument("--base", default="35aadb3", help="branch point used by the new-HTTP-test check")
    parser.add_argument("--append-base", default=APPEND_ONLY_BASE,
                        help="commit whose golden revisions and baselines HEAD may only extend or shrink")
    parser.add_argument("--report", default=str(Path(tempfile.gettempdir()) / "p0-gate-report.json"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--skip", action="append", help="skip a named step (recorded in the report)")
    parser.add_argument("--only", action="append", help="run only the named step(s)")
    parser.add_argument("--update-eslint-baseline", action="store_true", help="shrink the ESLint baseline after fixes")
    parser.add_argument("--quiet", action="store_true")
    arguments = parser.parse_args(argv)
    gate = Gate(arguments.tier, arguments)
    steps = STEPS[arguments.tier]
    if arguments.only:
        steps = [step for step in steps if step.name in arguments.only]
    started = time.monotonic()
    gate.execute(steps)
    failed = [row["step"] for row in gate.results if row["status"] == "failed"]
    report = {
        "schema_version": "value.p0-gate/v1",
        "tier": arguments.tier,
        "commit": run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "dirty": bool(run(["git", "status", "--porcelain"]).stdout.strip()),
        "seconds": round(time.monotonic() - started, 2),
        "steps": gate.results,
        "failed": failed,
        "passed": not failed,
    }
    Path(arguments.report).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    summary = {"tier": report["tier"], "seconds": report["seconds"], "failed": failed, "passed": report["passed"],
               "steps": {row["step"]: row["status"] for row in gate.results}, "report": arguments.report}
    print(json.dumps(summary, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
