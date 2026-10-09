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
* a quarantine entry has expired (``expires=Mk`` is valid through Mk;
  ``expires=host`` marks a permanent host quarantine), or
* ``--strict`` is given and the environment fingerprint differs.

Ids listed in ``tests/baselines/quarantine.txt`` are reported but never take
part in the ratchet.  ``--update-baseline`` may only delete entries; adding
entries requires ``--allow-add --reason "..."``.

``--pytest`` runs the pytest-style modules against a separate baseline.  When
pytest is not importable those ids are reported as ``not_run``.

Test interpreter: ``--python`` (default: the gate venv's interpreter when
``VALUE_GATE_VENV`` names one, otherwise this interpreter).  The gate venv is
the managed install's Python with only ``requirements/value-test-py310.lock``
(pytest, pypdf and their dependencies) added; the environment fingerprint
always describes the test interpreter, not the orchestrating one.

Every subprocess runs with ``-B``, ``PYTHONDONTWRITEBYTECODE=1`` and private
``PYTHONPYCACHEPREFIX``/``VALUE_DATA_HOME``/``HOME``/``TMPDIR`` directories
created with ``mkdtemp`` and removed afterwards.

Network guard: the first ``PYTHONPATH`` entry of every test subprocess holds a
generated ``sitecustomize.py`` that installs ``scripts/value_test_netguard.py``
in the worker and in every Python child that inherits the environment, and
``NODE_OPTIONS`` preloads ``scripts/value-test-netguard.mjs`` in node children.  Any
connect/bind to a local host on the live install's ports 8766/8800 is refused
and logged with the running test id; a run with any such attempt fails
(``forbidden_port_attempts``), whatever the baseline says.

The milestone that decides quarantine expiry is ``tests/baselines/milestone.txt``.
``--milestone`` overrides it for tests of this script only; the override is
recorded in the report (``milestone_source``) and p0_gate fails on it.
"""

from __future__ import annotations

# P0 rule (P0_CONVENTIONS section 2): never write bytecode, even when started
# without -B; the managed install's runtime is read-only and must stay
# byte-identical.  Inherited by every subprocess through the environment.
import os as _os
import sys as _sys

_sys.dont_write_bytecode = True
_os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import ast
import concurrent.futures
import datetime as _dt
import hashlib
import importlib
import importlib.util
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
TEST_LOCK = ROOT / "requirements" / "value-test-py310.lock"
GATE_VENV_ENV = "VALUE_GATE_VENV"
FAILING_OUTCOMES = frozenset({"fail", "error", "unexpected_success"})
MILESTONES = tuple(f"M{index}" for index in range(0, 9))
# ``expires=host``: permanent host quarantine.  Only for failures caused by a
# property of this host that no P0 package can change (the author's private
# Windows R0 source tree, Windows-only tools, the live install holding port
# 8766, the free-disk reserve).  Everything else expires at a milestone.
HOST_EXPIRY = "host"
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
    # A gate venv's own executable lives outside the install; its base prefix
    # (``<install>/runtime/python``) still identifies the install.
    for start in (Path(sys.executable).resolve(), Path(sys.base_prefix).resolve() / "bin"):
        for parent in start.parents:
            if parent.name == "runtime" and (parent.parent / "app").exists():
                return parent.parent
    return None


def gate_venv_python(environ: Mapping[str, str] | None = None) -> str | None:
    """The interpreter of the venv named by ``VALUE_GATE_VENV`` (``None`` if unset or absent)."""

    venv = (environ if environ is not None else os.environ).get(GATE_VENV_ENV, "").strip()
    if not venv:
        return None
    for candidate in (Path(venv) / "bin" / "python", Path(venv) / "Scripts" / "python.exe"):
        if candidate.is_file():
            return str(candidate)
    return None


def default_test_python() -> str:
    return gate_venv_python() or sys.executable


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


NETGUARD_SOURCE = ROOT / "scripts" / "value_test_netguard.py"
NODE_NETGUARD_SOURCE = ROOT / "scripts" / "value-test-netguard.mjs"
NETGUARD_DIR = "netguard"
NETGUARD_LOG = "netguard.log"


def install_netguard(scratch: Path) -> Path:
    """Write the guard module and its ``sitecustomize.py`` into ``scratch/netguard``."""

    folder = scratch / NETGUARD_DIR
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(NETGUARD_SOURCE, folder / "value_test_netguard.py")
    guard = _netguard_module()
    (folder / "sitecustomize.py").write_text(guard.SITECUSTOMIZE, encoding="utf-8")
    return folder


def _netguard_module():
    spec = importlib.util.spec_from_file_location("value_test_netguard_runner", NETGUARD_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def forbidden_port_attempts(scratch: Path) -> list[dict[str, Any]]:
    """Refused attempts logged by the network guard of one hermetic scratch."""

    return _netguard_module().read_log(scratch / NETGUARD_LOG)


def hermetic_environment(scratch: Path, base: Mapping[str, str] | None = None, *, python_root: Path = ROOT) -> dict[str, str]:
    """Return a subprocess environment whose writable state lives in ``scratch``.

    ``PYTHONPATH`` is the network-guard directory followed by ``python_root``.
    """

    environment = dict(base if base is not None else os.environ)
    for name in ("home", "tmp", "data", "pycache", "xdg-cache", "xdg-config", "xdg-data"):
        (scratch / name).mkdir(parents=True, exist_ok=True)
    guard = install_netguard(scratch)
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
            "PYTHONPATH": os.pathsep.join([str(guard), str(python_root)]),
            "PYTHONIOENCODING": "utf-8",
            "VALUE_TEST_NETGUARD_LOG": str(scratch / NETGUARD_LOG),
        }
    )
    environment.pop("PYTHONSTARTUP", None)
    environment.pop("VALUE_TEST_NETGUARD_TEST", None)
    node_guard = f"--import={NODE_NETGUARD_SOURCE.resolve().as_uri()}"
    options = environment.get("NODE_OPTIONS", "")
    if node_guard not in options.split():
        environment["NODE_OPTIONS"] = f"{options} {node_guard}".strip()
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


_INTERPRETER_PROBE = """
import json, platform, sys
from importlib import metadata
def version(name):
    try:
        return metadata.version(name)
    except Exception:
        return None
names = json.loads(sys.argv[1])
sys.stdout.write(json.dumps({
    "python": platform.python_version(),
    "implementation": platform.python_implementation(),
    "platform": f"{sys.platform}-{platform.machine()}",
    "versions": {name: version(name) for name in names},
}))
"""


def _same_interpreter(python: str | None) -> bool:
    # A venv's python is a symlink to the base interpreter: compare the paths
    # as given, never resolved, or the venv would look like its base.
    return python is None or os.path.abspath(python) == os.path.abspath(sys.executable)


def interpreter_facts(python: str | None, packages: Iterable[str]) -> dict[str, Any]:
    """Python/platform facts and distribution versions as seen by ``python``."""

    names = sorted(set(packages))
    if _same_interpreter(python):
        return {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": f"{sys.platform}-{platform.machine()}",
            "versions": {name: _distribution_version(name) for name in names},
        }
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [str(python), "-B", "-c", _INTERPRETER_PROBE, json.dumps(names)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, cwd=ROOT,
    )
    if completed.returncode != 0:
        raise SystemExit(f"test interpreter {python} cannot be probed: {completed.stderr[-500:]}")
    return json.loads(completed.stdout)


def read_test_lock(path: Path = TEST_LOCK) -> dict[str, str]:
    """``name -> version`` of the ``name==version`` lines of a lock file."""

    pins: dict[str, str] = {}
    if not path.is_file():
        return pins
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name, separator, version = line.partition("==")
        if not separator:
            raise ValueError(f"{path}: not an exact pin: {raw!r}")
        pins[name.strip()] = version.strip()
    return pins


def locked_package_mismatches(python: str | None = None, lock: Path = TEST_LOCK) -> dict[str, list[Any]]:
    """Locked test packages whose installed version differs (``[locked, installed]``)."""

    pins = read_test_lock(lock)
    if not pins:
        return {"<lock>": [str(lock), "missing or empty"]}
    versions = interpreter_facts(python, pins)["versions"]
    return {name: [locked, versions.get(name)] for name, locked in sorted(pins.items()) if versions.get(name) != locked}


def environment_fingerprint(root: Path = ROOT, python: str | None = None) -> dict[str, Any]:
    """Fingerprint of the test interpreter ``python`` (default: this one)."""

    facts = interpreter_facts(python, FINGERPRINT_PACKAGES)
    fingerprint: dict[str, Any] = {
        "python": facts["python"],
        "implementation": facts["implementation"],
        "platform": facts["platform"],
    }
    for package in FINGERPRINT_PACKAGES:
        fingerprint[package] = facts["versions"].get(package)
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
    """The milestone in ``tests/baselines/milestone.txt`` (environment ignored)."""

    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or "M0"
    return "M0"


def read_quarantine(path: Path) -> dict[str, dict[str, str]]:
    """Parse ``id | reason=... | owner=... | expires=M3|host`` lines.

    ``expires=Mk`` means *valid through* milestone Mk: the entry fails the run
    once ``tests/baselines/milestone.txt`` is later than Mk.  ``expires=host`` never expires (permanent host quarantine).
    """

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
        if fields["expires"] not in MILESTONES and fields["expires"] != HOST_EXPIRY:
            raise ValueError(f"quarantine entry {parts[0]!r} has unknown milestone {fields['expires']!r}")
        if _never_baselined(parts[0]):
            raise ValueError(f"quarantine entry {parts[0]!r}: golden-family tests are never quarantined")
        entries[parts[0]] = fields
    return entries


def expired_quarantine(entries: Mapping[str, Mapping[str, str]], milestone: str) -> list[str]:
    if milestone not in MILESTONES:
        raise ValueError(f"unknown milestone {milestone!r}")
    position = MILESTONES.index(milestone)
    return sorted(
        identifier
        for identifier, fields in entries.items()
        if fields["expires"] != HOST_EXPIRY and MILESTONES.index(fields["expires"]) < position
    )


# --------------------------------------------------------------------------
# Discovery


NEVER_BASELINED_MODULE_PREFIX = "test_golden"


def _never_baselined(identifier: str) -> bool:
    """Golden-family tests guard the doctoral freeze; they can never be silenced."""

    for prefix in ("IMPORT:", "CRASH:", "TIMEOUT:"):
        if identifier.startswith(prefix):
            identifier = identifier[len(prefix):]
    return identifier.split(".", 1)[0].startswith(NEVER_BASELINED_MODULE_PREFIX)


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
    try:
        import value_test_netguard as guard  # on PYTHONPATH via hermetic_environment
    except ImportError:  # worker started outside the hermetic environment
        guard = None
    else:
        guard.install()
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
        def startTest(self, test: Any) -> None:  # noqa: N802
            if guard is not None:
                guard.set_current_test(_normalise_test_id(test))
            super().startTest(test)

        def stopTest(self, test: Any) -> None:  # noqa: N802
            super().stopTest(test)
            if guard is not None:
                guard.set_current_test(None)

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
            payload = {
                "module": module,
                "outcomes": {f"TIMEOUT:{module}": "error"},
                "details": {f"TIMEOUT:{module}": f"module exceeded {timeout} s"},
                "seconds": round(time.monotonic() - started, 3),
            }
        else:
            if output.is_file():
                payload = json.loads(output.read_text(encoding="utf-8"))
                if completed.returncode != 0:
                    payload["outcomes"][f"CRASH:{module}"] = "error"
                    payload["details"][f"CRASH:{module}"] = (completed.stderr or "")[-2000:]
            else:
                payload = {
                    "module": module,
                    "outcomes": {f"CRASH:{module}": "error"},
                    "details": {f"CRASH:{module}": (completed.stderr or completed.stdout or "")[-2000:]},
                    "seconds": round(time.monotonic() - started, 3),
                }
        payload["forbidden_port_attempts"] = [dict(row, module=module) for row in forbidden_port_attempts(scratch)]
        return payload
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
    attempts: list[dict[str, Any]] = []
    for payload in results:
        outcomes.update(payload["outcomes"])
        details.update(payload.get("details", {}))
        timings[payload["module"]] = payload["seconds"]
        attempts.extend(payload.get("forbidden_port_attempts", []))
    return {
        "outcomes": dict(sorted(outcomes.items())),
        "details": details,
        "timings": dict(sorted(timings.items())),
        "wall_seconds": round(time.monotonic() - started, 3),
        "forbidden_port_attempts": sorted(attempts, key=lambda row: (row.get("module", ""), row.get("test", ""), row.get("op", ""))),
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


def junit_identifier(classname: str, name: str, root: Path = ROOT) -> str:
    """pytest node id from a junit ``classname``/``name`` pair.

    ``tests.data_workbench.test_x.SomeTests`` names the module
    ``tests/data_workbench/test_x.py`` and the class ``SomeTests``: the longest
    dotted prefix that is a file is the module, the rest are classes.
    """

    parts = classname.split(".") if classname else []
    for split in range(len(parts), 0, -1):
        module = "/".join(parts[:split]) + ".py"
        if (root / module).is_file():
            return "::".join([module, *parts[split:], name])
    return f"{'/'.join(parts)}.py::{name}"


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
        attempts = forbidden_port_attempts(scratch)
        outcomes: dict[str, str] = {}
        if report.is_file():
            for case in element_tree.parse(report).iter("testcase"):
                identifier = junit_identifier(case.get("classname", ""), case.get("name", ""))
                if case.find("failure") is not None:
                    outcomes[identifier] = "fail"
                elif case.find("error") is not None:
                    outcomes[identifier] = "error"
                elif case.find("skipped") is not None:
                    outcomes[identifier] = "skip"
                else:
                    outcomes[identifier] = "pass"
        return {"status": "ran", "pytest": version, "ids": identifiers, "outcomes": outcomes, "forbidden_port_attempts": attempts}
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
    parser.add_argument("--python", default=None,
                        help=f"interpreter used for test subprocesses (default: ${GATE_VENV_ENV}/bin/python if set, else this one)")
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
    parser.add_argument("--milestone", choices=MILESTONES,
                        help="tests of this script only: override tests/baselines/milestone.txt (recorded; p0_gate fails on it)")
    arguments = parser.parse_args(argv)

    if arguments._worker:
        return _worker(arguments._worker, arguments._output, arguments.tests_dir.resolve())

    if arguments.allow_add and not arguments.reason.strip():
        parser.error("--allow-add requires --reason")
    if arguments.allow_add and not arguments.update_baseline:
        parser.error("--allow-add is only valid with --update-baseline")

    arguments.python = arguments.python or default_test_python()
    fingerprint = environment_fingerprint(python=arguments.python)
    baseline_path = arguments.baseline or (DEFAULT_PYTEST_BASELINE if arguments.pytest else DEFAULT_BASELINE)
    baseline = read_baseline(baseline_path)
    quarantine = read_quarantine(arguments.quarantine)
    milestone = arguments.milestone or current_milestone()
    milestone_source = "--milestone" if arguments.milestone else MILESTONE_FILE.relative_to(ROOT).as_posix()
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
                "python": arguments.python,
                "fingerprint": fingerprint,
                "fingerprint_differences": differences,
                "passed": True,
            }
            _emit(report, arguments.json_output)
            return 0
        runs = [result["outcomes"]]
        attempts = result.get("forbidden_port_attempts", [])
    else:
        modules = arguments.modules or discover_modules(arguments.tests_dir)
        runs = []
        timings: dict[str, float] = {}
        wall = 0.0
        details: dict[str, str] = {}
        attempts = []
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
            attempts.extend(run["forbidden_port_attempts"])

    failing_sets = [failing_ids(outcomes) for outcomes in runs]
    always_failing = set.intersection(*failing_sets) if failing_sets else set()
    sometimes_failing = set.union(*failing_sets) - always_failing if failing_sets else set()
    observed = set().union(*(set(outcomes) for outcomes in runs))
    selected_modules = None if arguments.pytest or not arguments.modules else arguments.modules
    ratchet = compare(always_failing | sometimes_failing, observed, baseline, quarantine, selected_modules)

    if arguments.update_baseline:
        entries = {identifier: comment for identifier, comment in baseline.entries.items() if identifier not in ratchet["fixed_but_listed"]}
        added: list[str] = []
        never = [identifier for identifier in ratchet["new_failures"] if _never_baselined(identifier)]
        if arguments.allow_add:
            stamp = _dt.date.today().isoformat()
            for identifier in ratchet["new_failures"]:
                if identifier in never:
                    continue
                entries[identifier] = f"{stamp}: {arguments.reason.strip()}"
                added.append(identifier)
        write_baseline(baseline_path, fingerprint, entries)
        removed = ratchet["fixed_but_listed"]
        print(json.dumps({"baseline": str(baseline_path), "removed": removed, "added": added}, indent=2))
        refused = never if arguments.allow_add else ratchet["new_failures"]
        if never:
            print("golden-family tests guard the doctoral freeze and are never baselined:", file=sys.stderr)
        if refused:
            print("new failures were NOT added (use --allow-add --reason):", file=sys.stderr)
            for identifier in refused:
                print("  " + identifier, file=sys.stderr)
            return 1
        if attempts:
            print(f"{len(attempts)} refused attempt(s) to reach the live VALUE ports; fix the tests:", file=sys.stderr)
            for row in attempts:
                print(f"  {row.get('test')} {row.get('op')} {row.get('host')}:{row.get('port')}", file=sys.stderr)
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
    if attempts:
        tests = sorted({str(row.get("test")) for row in attempts})
        errors.append(
            f"{len(attempts)} attempt(s) by {len(tests)} test(s) to reach the live VALUE ports "
            f"{'/'.join(str(port) for port in _netguard_module().DEFAULT_FORBIDDEN_PORTS)} (refused; never baselined)"
        )

    all_outcomes = runs[-1]
    report = {
        "schema_version": "value.backend-test-ratchet/v1",
        "suite": "pytest" if arguments.pytest else "unittest",
        "baseline": str(baseline_path.relative_to(ROOT)) if baseline_path.is_relative_to(ROOT) else str(baseline_path),
        "milestone": milestone,
        "milestone_source": milestone_source,
        "python": arguments.python,
        "fingerprint": fingerprint,
        "fingerprint_differences": differences,
        "counts": _summary(all_outcomes),
        "ids": len(all_outcomes),
        "failing": len(always_failing | sometimes_failing),
        "baseline_size": len(baseline.ids),
        "flaky": sorted(sometimes_failing),
        "expired_quarantine": expired,
        "forbidden_port_attempts": attempts,
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
