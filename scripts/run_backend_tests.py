"""Fingerprinted unittest ratchet for the VALUE backend test suite.

The official entry point (``python -m unittest discover -s tests``) is run
module by module in isolated, hermetic subprocesses.  Every test method is
recorded as ``module.Class.method``; a module that cannot be imported is
recorded as ``IMPORT:module``; subTest outcomes are merged into the owning
method; class/module fixtures that fail are recorded as
``module.Class.setUpClass`` / ``module.setUpModule``.

The set of failing ids is compared with the committed baseline
``tests/baselines/known-failures-linux-py310.txt``.  The first line of that
file is ``# fingerprint: {json}`` describing the environment the baseline was
captured in.  A run fails (exit code 1) when

* a failing id is not in the baseline (``new_failures``),
* a baseline id now passes (``fixed_but_listed``; remove it with
  ``--update-baseline``),
* a quarantine entry has expired, or
* ``--strict`` is given and the environment fingerprint differs.

Ids listed in ``tests/baselines/quarantine.txt`` are reported but never take
part in the ratchet.  ``--update-baseline`` may only delete entries; adding
entries requires ``--allow-add --reason "..."``.

``--pytest`` runs the pytest-style modules against a separate baseline.  When
pytest is not importable those ids are reported as ``not_run``.

Every subprocess runs with ``-B``, ``PYTHONDONTWRITEBYTECODE=1`` and private
``PYTHONPYCACHEPREFIX``/``VALUE_DATA_HOME``/``HOME``/``TMPDIR`` directories
created with ``mkdtemp`` and removed afterwards.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import datetime as _dt
import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
BASELINE_DIR = TESTS / "baselines"
DEFAULT_BASELINE = BASELINE_DIR / "known-failures-linux-py310.txt"
DEFAULT_PYTEST_BASELINE = BASELINE_DIR / "known-failures-pytest-linux-py310.txt"
DEFAULT_QUARANTINE = BASELINE_DIR / "quarantine.txt"
MILESTONE_FILE = BASELINE_DIR / "milestone.txt"
FINGERPRINT_PREFIX = "# fingerprint: "
FINGERPRINT_PACKAGES = ("numpy", "scipy", "pandas", "pulp", "cbcbox", "pytest", "pypdf")
FINGERPRINT_LOCKS = ("requirements/value-all-py310.lock", "requirements/value-test-py310.lock")
FAILING_OUTCOMES = frozenset({"fail", "error", "unexpected_success"})
MILESTONES = tuple(f"M{index}" for index in range(0, 9))
PYTEST_TOP_LEVEL_MODULES = (
    "tests/test_full_desktop_installer.py",
    "tests/test_market_ledger_v6.py",
    "tests/test_prompt107_production_gate.py",
    "tests/test_run_reproduction.py",
    "tests/test_vre_curtailment_attribution.py",
)
PYTEST_DIRECTORIES = ("tests/data_workbench",)
DEFAULT_MODULE_TIMEOUT_SECONDS = 1200


# --------------------------------------------------------------------------
# Hermetic environment


def installed_root() -> Path | None:
    """Return the read-only managed install that tests must never write into."""

    configured = os.environ.get("VALUE_INSTALLED_ROOT")
    if configured:
        return Path(configured).resolve()
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.name == "runtime" and (parent.parent / "app").exists():
            return parent.parent
    return None


def refuse_installed_paths(paths: Iterable[Path | str | None], installed: Path | None = None) -> None:
    """Raise SystemExit when any path lies inside the managed install."""

    installed = installed if installed is not None else installed_root()
    if installed is None:
        return
    for raw in paths:
        if not raw:
            continue
        candidate = Path(raw).resolve()
        if candidate == installed or installed in candidate.parents:
            raise SystemExit(f"refusing to write test state inside the managed install: {candidate}")


def hermetic_environment(scratch: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a subprocess environment whose writable state lives in ``scratch``."""

    environment = dict(base if base is not None else os.environ)
    for name in ("home", "tmp", "data", "pycache", "xdg-cache", "xdg-config", "xdg-data"):
        (scratch / name).mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(scratch / "pycache"),
            "VALUE_DATA_HOME": str(scratch / "data"),
            "HOME": str(scratch / "home"),
            "TMPDIR": str(scratch / "tmp"),
            "TEMP": str(scratch / "tmp"),
            "TMP": str(scratch / "tmp"),
            "XDG_CACHE_HOME": str(scratch / "xdg-cache"),
            "XDG_CONFIG_HOME": str(scratch / "xdg-config"),
            "XDG_DATA_HOME": str(scratch / "xdg-data"),
            "PYTHONPATH": os.pathsep.join([str(ROOT)]),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    environment.pop("PYTHONSTARTUP", None)
    refuse_installed_paths([environment["VALUE_DATA_HOME"], environment["TMPDIR"], environment["HOME"]])
    return environment


# --------------------------------------------------------------------------
# Fingerprint


def _distribution_version(name: str) -> str | None:
    try:
        from importlib import metadata

        return metadata.version(name)
    except Exception:  # pragma: no cover - depends on environment
        return None


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_fingerprint(root: Path = ROOT) -> dict[str, Any]:
    fingerprint: dict[str, Any] = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": f"{sys.platform}-{platform.machine()}",
    }
    for package in FINGERPRINT_PACKAGES:
        fingerprint[package] = _distribution_version(package)
    for lock in FINGERPRINT_LOCKS:
        fingerprint[f"sha256:{lock}"] = _sha256_file(root / lock)
    return fingerprint


def fingerprint_differences(expected: Mapping[str, Any] | None, actual: Mapping[str, Any]) -> dict[str, list[Any]]:
    if not expected:
        return {"<baseline>": [None, "missing fingerprint"]}
    keys = sorted(set(expected) | set(actual))
    return {key: [expected.get(key), actual.get(key)] for key in keys if expected.get(key) != actual.get(key)}


# --------------------------------------------------------------------------
# Baseline and quarantine files


class Baseline:
    def __init__(self, fingerprint: dict[str, Any] | None, entries: dict[str, str]) -> None:
        self.fingerprint = fingerprint
        self.entries = entries

    @property
    def ids(self) -> set[str]:
        return set(self.entries)


def read_baseline(path: Path) -> Baseline:
    if not path.is_file():
        return Baseline(None, {})
    fingerprint: dict[str, Any] | None = None
    entries: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(FINGERPRINT_PREFIX):
            fingerprint = json.loads(line[len(FINGERPRINT_PREFIX):])
            continue
        if line.startswith("#"):
            continue
        identifier, _, comment = line.partition("#")
        entries[identifier.strip()] = comment.strip()
    return Baseline(fingerprint, entries)


def write_baseline(path: Path, fingerprint: Mapping[str, Any], entries: Mapping[str, str], header: Sequence[str] = ()) -> None:
    lines = [FINGERPRINT_PREFIX + json.dumps(dict(fingerprint), sort_keys=True)]
    lines.extend(f"# {text}" for text in header)
    for identifier in sorted(entries):
        comment = entries[identifier]
        lines.append(f"{identifier}  # {comment}" if comment else identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def current_milestone(path: Path = MILESTONE_FILE) -> str:
    override = os.environ.get("VALUE_P0_MILESTONE")
    if override:
        return override.strip()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or "M0"
    return "M0"


def read_quarantine(path: Path) -> dict[str, dict[str, str]]:
    """Parse ``id | reason=... | owner=... | expires=M3`` lines."""

    entries: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        fields: dict[str, str] = {}
        for part in parts[1:]:
            key, _, value = part.partition("=")
            fields[key.strip()] = value.strip()
        missing = [key for key in ("reason", "owner", "expires") if not fields.get(key)]
        if missing:
            raise ValueError(f"quarantine entry {parts[0]!r} lacks {', '.join(missing)}")
        if fields["expires"] not in MILESTONES:
            raise ValueError(f"quarantine entry {parts[0]!r} has unknown milestone {fields['expires']!r}")
        entries[parts[0]] = fields
    return entries


def expired_quarantine(entries: Mapping[str, Mapping[str, str]], milestone: str) -> list[str]:
    if milestone not in MILESTONES:
        raise ValueError(f"unknown milestone {milestone!r}")
    position = MILESTONES.index(milestone)
    return sorted(identifier for identifier, fields in entries.items() if MILESTONES.index(fields["expires"]) < position)


# --------------------------------------------------------------------------
# Discovery


def discover_modules(tests_dir: Path = TESTS, pattern_prefix: str = "test_") -> list[str]:
    return sorted(path.stem for path in tests_dir.glob(f"{pattern_prefix}*.py") if path.is_file())


def _is_pytest_style(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    has_case = any(
        isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Attribute) and base.attr == "TestCase")
            or (isinstance(base, ast.Name) and base.id.endswith("TestCase"))
            for base in node.bases
        )
        for node in tree.body
    )
    has_functions = any(isinstance(node, ast.FunctionDef) and node.name.startswith("test_") for node in tree.body)
    return has_functions and not has_case


def static_pytest_ids(root: Path = ROOT) -> list[str]:
    """Return pytest node ids found statically (used when pytest is absent)."""

    files: list[Path] = [root / name for name in PYTEST_TOP_LEVEL_MODULES]
    for directory in PYTEST_DIRECTORIES:
        files.extend(sorted((root / directory).glob("test_*.py")))
    identifiers: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(root).as_posix()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                identifiers.append(f"{relative}::{node.name}")
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                        identifiers.append(f"{relative}::{node.name}::{child.name}")
    return sorted(set(identifiers))


# --------------------------------------------------------------------------
# Worker (runs inside the hermetic subprocess)


def _normalise_test_id(test: Any) -> str:
    import unittest

    if isinstance(test, unittest.case._SubTest):  # type: ignore[attr-defined]
        test = test.test_case
    class_name = type(test).__name__
    if class_name == "_FailedTest":
        method = getattr(test, "_testMethodName", "unknown")
        return f"IMPORT:{method}"
    if class_name == "_ErrorHolder":
        description = str(getattr(test, "description", test))
        # "setUpClass (module.Class)" or "setUpModule (module)"
        name, _, scope = description.partition(" (")
        scope = scope.rstrip(")")
        return f"{scope}.{name}" if scope else name
    return test.id()


def _worker(module: str, output: Path, tests_dir: Path = TESTS) -> int:
    import io
    import unittest

    sys.path[:0] = [str(tests_dir), str(ROOT)]
    outcomes: dict[str, str] = {}
    details: dict[str, str] = {}
    rank = {"pass": 0, "skip": 1, "expected_failure": 1, "unexpected_success": 3, "fail": 4, "error": 5}

    def record(test: Any, outcome: str, detail: str | None = None) -> None:
        identifier = _normalise_test_id(test)
        previous = outcomes.get(identifier)
        if previous is None or rank[outcome] > rank[previous]:
            outcomes[identifier] = outcome
            if detail:
                details[identifier] = detail[-2000:]

    class Recorder(unittest.TextTestResult):
        def addSuccess(self, test: Any) -> None:  # noqa: N802
            super().addSuccess(test)
            record(test, "pass")

        def addFailure(self, test: Any, err: Any) -> None:  # noqa: N802
            super().addFailure(test, err)
            record(test, "fail", self._exc_info_to_string(err, test))

        def addError(self, test: Any, err: Any) -> None:  # noqa: N802
            super().addError(test, err)
            record(test, "error", self._exc_info_to_string(err, test))

        def addSkip(self, test: Any, reason: str) -> None:  # noqa: N802
            super().addSkip(test, reason)
            record(test, "skip", reason)

        def addExpectedFailure(self, test: Any, err: Any) -> None:  # noqa: N802
            super().addExpectedFailure(test, err)
            record(test, "expected_failure")

        def addUnexpectedSuccess(self, test: Any) -> None:  # noqa: N802
            super().addUnexpectedSuccess(test)
            record(test, "unexpected_success")

        def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:  # noqa: N802
            super().addSubTest(test, subtest, err)
            if err is not None:
                failure = issubclass(err[0], test.failureException)
                record(test, "fail" if failure else "error", self._exc_info_to_string(err, test))

    started = time.monotonic()
    stream = io.StringIO()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(module)
    except BaseException as exc:  # noqa: BLE001 - any import-time failure is a result
        outcomes[f"IMPORT:{module}"] = "error"
        details[f"IMPORT:{module}"] = f"{type(exc).__name__}: {exc}"
    else:
        runner = unittest.TextTestRunner(stream=stream, verbosity=0, resultclass=Recorder)
        runner.run(suite)
    payload = {
        "module": module,
        "outcomes": outcomes,
        "details": details,
        "seconds": round(time.monotonic() - started, 3),
    }
    output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return 0


# --------------------------------------------------------------------------
# Orchestration


def _run_module(module: str, python: str, timeout: float, tests_dir: Path = TESTS, keep_scratch: bool = False) -> dict[str, Any]:
    scratch = Path(tempfile.mkdtemp(prefix=f"value-ratchet-{module}-"))
    output = scratch / "result.json"
    started = time.monotonic()
    try:
        environment = hermetic_environment(scratch)
        command = [python, "-B", str(Path(__file__).resolve()), "--_worker", module, "--_output", str(output), "--tests-dir", str(tests_dir)]
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "module": module,
                "outcomes": {f"TIMEOUT:{module}": "error"},
                "details": {f"TIMEOUT:{module}": f"module exceeded {timeout} s"},
                "seconds": round(time.monotonic() - started, 3),
            }
        if output.is_file():
            payload = json.loads(output.read_text(encoding="utf-8"))
            if completed.returncode != 0:
                payload["outcomes"][f"CRASH:{module}"] = "error"
                payload["details"][f"CRASH:{module}"] = (completed.stderr or "")[-2000:]
            return payload
        return {
            "module": module,
            "outcomes": {f"CRASH:{module}": "error"},
            "details": {f"CRASH:{module}": (completed.stderr or completed.stdout or "")[-2000:]},
            "seconds": round(time.monotonic() - started, 3),
        }
    finally:
        if not keep_scratch:
            shutil.rmtree(scratch, ignore_errors=True)


def run_modules(
    modules: Sequence[str],
    *,
    python: str = sys.executable,
    jobs: int | None = None,
    timeout: float = DEFAULT_MODULE_TIMEOUT_SECONDS,
    progress: bool = False,
    tests_dir: Path = TESTS,
) -> dict[str, Any]:
    jobs = jobs or min(16, max(1, (os.cpu_count() or 2)))
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_run_module, module, python, timeout, tests_dir): module for module in modules}
        for future in concurrent.futures.as_completed(futures):
            payload = future.result()
            results.append(payload)
            if progress:
                failing = sum(1 for outcome in payload["outcomes"].values() if outcome in FAILING_OUTCOMES)
                print(f"[ratchet] {payload['module']}: {len(payload['outcomes'])} ids, {failing} failing, {payload['seconds']} s", file=sys.stderr)
    outcomes: dict[str, str] = {}
    details: dict[str, str] = {}
    timings: dict[str, float] = {}
    for payload in results:
        outcomes.update(payload["outcomes"])
        details.update(payload.get("details", {}))
        timings[payload["module"]] = payload["seconds"]
    return {
        "outcomes": dict(sorted(outcomes.items())),
        "details": details,
        "timings": dict(sorted(timings.items())),
        "wall_seconds": round(time.monotonic() - started, 3),
    }


def failing_ids(outcomes: Mapping[str, str]) -> set[str]:
    return {identifier for identifier, outcome in outcomes.items() if outcome in FAILING_OUTCOMES}


def compare(
    failing: set[str],
    observed: set[str],
    baseline: Baseline,
    quarantine: Mapping[str, Mapping[str, str]],
    modules: Sequence[str] | None = None,
) -> dict[str, list[str]]:
    """Return ratchet differences.  ``observed`` is every id that ran."""

    quarantined = set(quarantine)
    listed = baseline.ids - quarantined
    if modules is not None:
        selected = set(modules)

        def in_scope(identifier: str) -> bool:
            if ":" in identifier.split(".")[0]:
                return identifier.split(":", 1)[1].split(".")[0] in selected
            return identifier.split(".")[0] in selected

        listed = {identifier for identifier in listed if in_scope(identifier)}
    new_failures = sorted((failing - quarantined) - baseline.ids)
    fixed_but_listed = sorted(identifier for identifier in listed if identifier not in failing)
    return {
        "new_failures": new_failures,
        "fixed_but_listed": fixed_but_listed,
        "quarantined_failing": sorted(failing & quarantined),
        "quarantined_passing": sorted((observed - failing) & quarantined),
    }


def _pytest_available(python: str) -> str | None:
    completed = subprocess.run(
        [python, "-B", "-c", "import pytest, sys; sys.stdout.write(pytest.__version__)"],
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def run_pytest(python: str) -> dict[str, Any]:
    identifiers = static_pytest_ids()
    version = _pytest_available(python)
    if version is None:
        return {"status": "not_run", "reason": "pytest is not importable", "ids": identifiers, "outcomes": {}}
    import xml.etree.ElementTree as element_tree

    scratch = Path(tempfile.mkdtemp(prefix="value-ratchet-pytest-"))
    try:
        report = scratch / "junit.xml"
        targets = [name for name in (*PYTEST_TOP_LEVEL_MODULES, *PYTEST_DIRECTORIES) if (ROOT / name).exists()]
        subprocess.run(
            [python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={report}", *targets],
            cwd=ROOT,
            env=hermetic_environment(scratch),
            capture_output=True,
            text=True,
        )
        outcomes: dict[str, str] = {}
        if report.is_file():
            for case in element_tree.parse(report).iter("testcase"):
                classname = case.get("classname", "").replace(".", "/")
                name = case.get("name", "")
                identifier = f"{classname}.py::{name}"
                if case.find("failure") is not None:
                    outcomes[identifier] = "fail"
                elif case.find("error") is not None:
                    outcomes[identifier] = "error"
                elif case.find("skipped") is not None:
                    outcomes[identifier] = "skip"
                else:
                    outcomes[identifier] = "pass"
        return {"status": "ran", "pytest": version, "ids": identifiers, "outcomes": outcomes}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _summary(outcomes: Mapping[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--_worker", help=argparse.SUPPRESS)
    parser.add_argument("--_output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--modules", nargs="*", help="run only these test modules (stem names)")
    parser.add_argument("--tests-dir", type=Path, default=TESTS, help="directory holding test_*.py modules")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_MODULE_TIMEOUT_SECONDS)
    parser.add_argument("--python", default=sys.executable, help="interpreter used for test subprocesses")
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--quarantine", type=Path, default=DEFAULT_QUARANTINE)
    parser.add_argument("--strict", action="store_true", help="fail when the environment fingerprint differs")
    parser.add_argument("--update-baseline", action="store_true", help="delete fixed ids from the baseline")
    parser.add_argument("--allow-add", action="store_true", help="with --update-baseline: also add new failures")
    parser.add_argument("--reason", default="", help="required with --allow-add")
    parser.add_argument("--runs", type=int, default=1, help="repeat the run; ids failing only sometimes are flaky")
    parser.add_argument("--pytest", action="store_true", help="run the pytest-style modules instead")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--progress", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments._worker:
        return _worker(arguments._worker, arguments._output, arguments.tests_dir.resolve())

    if arguments.allow_add and not arguments.reason.strip():
        parser.error("--allow-add requires --reason")
    if arguments.allow_add and not arguments.update_baseline:
        parser.error("--allow-add is only valid with --update-baseline")

    fingerprint = environment_fingerprint()
    baseline_path = arguments.baseline or (DEFAULT_PYTEST_BASELINE if arguments.pytest else DEFAULT_BASELINE)
    baseline = read_baseline(baseline_path)
    quarantine = read_quarantine(arguments.quarantine)
    milestone = current_milestone()
    expired = expired_quarantine(quarantine, milestone)
    differences = fingerprint_differences(baseline.fingerprint, fingerprint)

    if arguments.pytest:
        result = run_pytest(arguments.python)
        if result["status"] == "not_run":
            report = {
                "schema_version": "value.backend-test-ratchet/v1",
                "suite": "pytest",
                "status": "not_run",
                "reason": result["reason"],
                "not_run_ids": result["ids"],
                "not_run_count": len(result["ids"]),
                "fingerprint": fingerprint,
                "fingerprint_differences": differences,
                "passed": True,
            }
            _emit(report, arguments.json_output)
            return 0
        runs = [result["outcomes"]]
    else:
        modules = arguments.modules or discover_modules(arguments.tests_dir)
        runs = []
        timings: dict[str, float] = {}
        wall = 0.0
        details: dict[str, str] = {}
        for _ in range(max(1, arguments.runs)):
            run = run_modules(
                modules,
                python=arguments.python,
                jobs=arguments.jobs,
                timeout=arguments.timeout,
                progress=arguments.progress,
                tests_dir=arguments.tests_dir.resolve(),
            )
            runs.append(run["outcomes"])
            timings = run["timings"]
            wall += run["wall_seconds"]
            details.update(run["details"])

    failing_sets = [failing_ids(outcomes) for outcomes in runs]
    always_failing = set.intersection(*failing_sets) if failing_sets else set()
    sometimes_failing = set.union(*failing_sets) - always_failing if failing_sets else set()
    observed = set().union(*(set(outcomes) for outcomes in runs))
    selected_modules = None if arguments.pytest or not arguments.modules else arguments.modules
    ratchet = compare(always_failing | sometimes_failing, observed, baseline, quarantine, selected_modules)

    if arguments.update_baseline:
        entries = {identifier: comment for identifier, comment in baseline.entries.items() if identifier not in ratchet["fixed_but_listed"]}
        added: list[str] = []
        if arguments.allow_add:
            stamp = _dt.date.today().isoformat()
            for identifier in ratchet["new_failures"]:
                entries[identifier] = f"{stamp}: {arguments.reason.strip()}"
                added.append(identifier)
        write_baseline(baseline_path, fingerprint, entries)
        removed = ratchet["fixed_but_listed"]
        print(json.dumps({"baseline": str(baseline_path), "removed": removed, "added": added}, indent=2))
        refused = [] if arguments.allow_add else ratchet["new_failures"]
        if refused:
            print("new failures were NOT added (use --allow-add --reason):", file=sys.stderr)
            for identifier in refused:
                print("  " + identifier, file=sys.stderr)
            return 1
        return 0

    errors: list[str] = []
    if ratchet["new_failures"]:
        errors.append(f"{len(ratchet['new_failures'])} new failure(s)")
    if ratchet["fixed_but_listed"]:
        errors.append(f"{len(ratchet['fixed_but_listed'])} fixed test(s) still listed in the baseline")
    if sometimes_failing - set(quarantine):
        errors.append(f"{len(sometimes_failing - set(quarantine))} flaky id(s) outside quarantine")
    if expired:
        errors.append(f"{len(expired)} quarantine entr(y/ies) expired at {milestone}")
    if differences and arguments.strict:
        errors.append("environment fingerprint differs from the baseline (--strict)")

    all_outcomes = runs[-1]
    report = {
        "schema_version": "value.backend-test-ratchet/v1",
        "suite": "pytest" if arguments.pytest else "unittest",
        "baseline": str(baseline_path.relative_to(ROOT)) if baseline_path.is_relative_to(ROOT) else str(baseline_path),
        "milestone": milestone,
        "fingerprint": fingerprint,
        "fingerprint_differences": differences,
        "counts": _summary(all_outcomes),
        "ids": len(all_outcomes),
        "failing": len(always_failing | sometimes_failing),
        "baseline_size": len(baseline.ids),
        "flaky": sorted(sometimes_failing),
        "expired_quarantine": expired,
        **ratchet,
        "errors": errors,
        "passed": not errors,
    }
    if not arguments.pytest:
        report["wall_seconds"] = round(wall, 3)
        report["slowest_modules"] = sorted(timings.items(), key=lambda item: -item[1])[:10]
        report["new_failure_details"] = {identifier: details.get(identifier, "") for identifier in ratchet["new_failures"]}
    _emit(report, arguments.json_output)
    return 0 if not errors else 1


def _emit(report: Mapping[str, Any], destination: Path | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=False)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text + "\n", encoding="utf-8")
    brief = {key: value for key, value in report.items() if key not in {"not_run_ids", "new_failure_details", "fingerprint"}}
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
