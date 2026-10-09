"""Per-table x column golden of the P0-4 fixture ledgers (plan 4.4 S1).

P0-4 S4-S6 instrument the default PSM kernel (storage audit, surplus routing,
declared boundary) and must not move any trajectory.  This script freezes, at
the M0 HEAD, a digest of every table and every column of ``market.sqlite``
for each derived fixture in ``tests/p04_variants.py``, so later steps can
prove exactly which columns they changed (S4: only
``storage_state.charge_mwh``; S5: new tables only).

The digest is the shared golden digest (``gridform_validation.golden``,
integration rule C17): one record per ``market/market.sqlite::<table>.<column>``
key plus ``<table>.#rows``, each with its Q12 zone from
``tests/golden/zones.json`` and an exact and a ``%.9g`` hash.  Comparison is
exact on the reference platform (linux-x86_64, CPython 3.10, numpy 1.24.4)
and uses the ``%.9g`` hashes elsewhere.

Usage::

    python -B scripts/p04_capture_trajectory_golden.py capture [--plan-step TEXT]
                                                                 # writes the fixture (reference platform only)
    python -B scripts/p04_capture_trajectory_golden.py check     # exit 1 on any difference
    python -B scripts/p04_capture_trajectory_golden.py digest RUN_DIR

Each variant runs in its own interpreter (P7-02 process-global weather cache).

R4-1 (DECISIONS A26) re-captured the fixture once: the three thesis-kernel
corrections change the doctoral dispatch of every variant, so the M0 HEAD
capture (commit 56460e1, kept in git history) was replaced by a capture at
R4-1 (``plan_step`` says which).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_validation import golden  # noqa: E402
from tests import p04_variants  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "p04_trajectory_golden.json"
ZONES = ROOT / "tests" / "golden" / "zones.json"
SCHEMA_VERSION = "value.p04-trajectory-golden/v1"
LEDGER_ARTIFACT = "market/market.sqlite"
SOURCE_FILES = (
    "gridform_core/builtin/scheme_c_1000twh/runtime_compat/modular_simulation_model.py",
    "gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py",
    "gridform_core/market_ledger.py",
    "tests/p04_variants.py",
)


def zone_rules() -> golden.ZoneRules:
    return golden.ZoneRules.load(ZONES)


def digest_output(output_dir: Path, zones: golden.ZoneRules | None = None) -> dict[str, Any]:
    """Golden digest of the ``market.sqlite`` of one run output directory."""

    output_dir = Path(output_dir)
    if not (output_dir / LEDGER_ARTIFACT).is_file():
        raise FileNotFoundError(output_dir / LEDGER_ARTIFACT)
    full = golden.digest_run(output_dir, zones or zone_rules())
    prefix = f"{LEDGER_ARTIFACT}::"
    columns = {key: value for key, value in full["columns"].items() if key.startswith(prefix)}
    return {"schema_version": full["schema_version"], "platform": full["platform"], "columns": columns}


def comparison_mode() -> str:
    return golden.default_mode()


def compare(expected: Mapping[str, Any], actual: Mapping[str, Any], mode: str | None = None) -> list[dict[str, str]]:
    """Per-column differences (key, kind, zone, section); empty when identical."""

    return [item.to_dict() for item in golden.compare_digests(expected, actual, mode or comparison_mode())]


def source_hashes(root: Path = ROOT) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def head_commit() -> str | None:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def run_variants(names: Sequence[str], workdir: Path, *, workers: int = 4) -> dict[str, Path]:
    """Run each variant in its own interpreter; return name -> run output dir."""

    def one(name: str) -> tuple[str, Path]:
        output = Path(workdir) / name
        p04_variants.run_variant(name, output)
        return name, output

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return dict(pool.map(one, names))


def capture(names: Sequence[str], workers: int, plan_step: str = "P0-4 S1 (M0 HEAD capture)") -> dict[str, Any]:
    zones = zone_rules()
    with tempfile.TemporaryDirectory(prefix="value-p04-golden-") as scratch:
        outputs = run_variants(names, Path(scratch), workers=workers)
        variants = {name: digest_output(outputs[name], zones) for name in names}
    return {
        "schema_version": SCHEMA_VERSION,
        "digest_schema_version": golden.SCHEMA_VERSION,
        "plan_step": plan_step,
        "captured_at_commit": head_commit(),
        "platform": golden.reference_platform(),
        "reference_platform": golden.REFERENCE_PLATFORM,
        "source_sha256": source_hashes(),
        "mode": p04_variants.DEFAULT_MODE,
        "base_project": p04_variants.BASE_PROJECT.relative_to(ROOT).as_posix(),
        "base_pack": p04_variants.BASE_PACK.relative_to(ROOT).as_posix(),
        "artifact": LEDGER_ARTIFACT,
        "variants": variants,
    }


def check(fixture: Mapping[str, Any], names: Sequence[str], workers: int, mode: str | None = None) -> dict[str, list[dict[str, str]]]:
    zones = zone_rules()
    with tempfile.TemporaryDirectory(prefix="value-p04-golden-") as scratch:
        outputs = run_variants(names, Path(scratch), workers=workers)
        return {
            name: compare(fixture["variants"][name], digest_output(outputs[name], zones), mode)
            for name in names
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "check"):
        item = sub.add_parser(command)
        item.add_argument("--variants", nargs="*", default=sorted(p04_variants.VARIANTS))
        item.add_argument("--workers", type=int, default=4)
        item.add_argument("--fixture", type=Path, default=FIXTURE)
        if command == "capture":
            item.add_argument("--plan-step", default="P0-4 S1 (M0 HEAD capture)")
    digest = sub.add_parser("digest")
    digest.add_argument("output_dir", type=Path)
    arguments = parser.parse_args(argv)

    if arguments.command == "digest":
        print(json.dumps(digest_output(arguments.output_dir), indent=2, sort_keys=True))
        return 0
    if arguments.command == "capture":
        if golden.default_mode() != "exact":
            sys.stderr.write(f"refusing to capture off the reference platform: {golden.reference_platform()}\n")
            return 2
        payload = capture(arguments.variants, arguments.workers, arguments.plan_step)
        arguments.fixture.parent.mkdir(parents=True, exist_ok=True)
        arguments.fixture.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {arguments.fixture} ({len(payload['variants'])} variants)")
        return 0
    fixture = json.loads(arguments.fixture.read_text(encoding="utf-8"))
    differences = check(fixture, arguments.variants, arguments.workers)
    print(json.dumps({"mode": comparison_mode(), "differences": differences}, indent=2, sort_keys=True))
    return 1 if any(differences.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
