"""Golden delta report of the P0 construction (plan X0 S13).

Two views, both computed from the committed golden files alone (no model
runs, no network, a few seconds):

* **Delta against revision 0.**  For every golden case the per-column
  difference between revision 0 (code equivalent to 35aadb3) and the latest
  revision.  Every row is attributed to the correction ids of the revisions
  whose recorded delta changed that column.
* **Dual-profile delta.**  For every doctoral case and the corrected case run
  on the same data pack and mode, the per-column difference between the two
  latest digests.  A row is attributed to the correction ids that changed the
  column on either side since revision 0 and, when the two cases already
  differed at revision 0, to ``REFERENCE_CONFIGURATION_ID``: the doctoral
  profile's reference configuration (decision Q3: legacy storage tariff,
  doctoral carbon-factor scenario), which is a configuration difference and
  not a correction.

Every row must be attributable (plan 3.7: "each row maps to a correction
id"); a row that is not - a column no revision recorded, or a revision that
names findings but no correction id - is listed under ``unattributed`` and
makes ``--check`` fail.  When only revision 0 exists (M0) both deltas are
empty.

Commands::

    delta_report.py                    # print the Markdown report
    delta_report.py --write            # write docs/release/P0_GOLDEN_DELTA.md
    delta_report.py --check            # exit 1 when a row is unattributed or the
                                       # committed report is out of date
    delta_report.py --json OUT         # full report with every row (not committed)

Numeric magnitudes of the approved doctoral trajectory re-baselines are in
``tests/golden/reports/<case>-r<k>.json`` (capture.py numeric-report); this
report lists which columns changed and why, not by how much.
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
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_validation import golden as golden_lib  # noqa: E402

SCHEMA_VERSION = "value.golden-delta-report/v1"
REFERENCE_CONFIGURATION_ID = "profile.reference-configuration"
REPORT_PATH = Path("docs/release/P0_GOLDEN_DELTA.md")
GOLDEN_DIR = Path("tests/golden")
CATALOGUE_DIR = Path("gridform_core/data/methodology/corrections")
LEDGER_PATH = Path("docs/release/VERSION_LEDGER.json")
ZONE_ORDER = ("trajectory", "accounting", "identity")
# Case-definition keys that do not describe the run configuration.
_NON_CONFIGURATION_KEYS = {"family", "tier", "title", "runtime_options"}


# --------------------------------------------------------------------------
# Loading


def load_cases(root: Path) -> dict[str, dict[str, Any]]:
    return json.loads((root / GOLDEN_DIR / "cases.json").read_text(encoding="utf-8"))["cases"]


def load_goldens(root: Path, cases: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    goldens: dict[str, dict[str, Any]] = {}
    for case_id, case in sorted(cases.items()):
        path = root / GOLDEN_DIR / str(case["family"]) / f"{case_id}.json"
        if path.is_file():
            goldens[case_id] = json.loads(path.read_text(encoding="utf-8"))
    return goldens


def load_correction_index(root: Path, goldens: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every correction id named by a golden revision, the methodology
    catalogue or VERSION_LEDGER, with where it is defined and in which golden
    families it was recorded."""

    index: dict[str, dict[str, Any]] = {}

    def entry(correction_id: str) -> dict[str, Any]:
        return index.setdefault(
            correction_id,
            {
                "id": correction_id,
                "package": correction_id.split(".", 1)[0],
                "catalogue_track": None,
                "findings": [],
                "description": "",
                "ledger_modules": [],
                "families": [],
                "golden_reason": "",
            },
        )

    catalogue = root / CATALOGUE_DIR
    if catalogue.is_dir():
        for path in sorted(catalogue.glob("*.json")):
            for row in json.loads(path.read_text(encoding="utf-8")).get("corrections", []):
                record = entry(str(row["id"]))
                record["catalogue_track"] = row.get("track")
                record["findings"] = sorted(set(record["findings"]) | set(row.get("findings") or []))
                record["description"] = str(row.get("description") or "")
    ledger = root / LEDGER_PATH
    if ledger.is_file():
        for module_id, module in sorted(json.loads(ledger.read_text(encoding="utf-8")).get("modules", {}).items()):
            for bump in module.get("bumps") or []:
                for correction_id in bump.get("correction_ids") or []:
                    record = entry(str(correction_id))
                    label = f"{module_id} {bump.get('from')}->{bump.get('to')}"
                    if label not in record["ledger_modules"]:
                        record["ledger_modules"].append(label)
                    record.setdefault("ledger_reason", str(bump.get("reason") or ""))
    catalogued = {correction_id for correction_id, record in index.items() if record["catalogue_track"]}
    # A revision may record several correction ids with the findings of all
    # of them (D5 r1 names twelve); findings and reasons are therefore taken
    # from the catalogue first, then from revisions naming the id alone.
    single_reason: dict[str, str] = {}
    shared_reason: dict[str, str] = {}
    for case_id, golden in sorted(goldens.items()):
        family = str(golden.get("family"))
        for revision in (golden.get("revisions") or [])[1:]:
            correction_ids = [str(value) for value in revision.get("correction_ids") or []]
            for correction_id in correction_ids:
                record = entry(correction_id)
                if family not in record["families"]:
                    record["families"].append(family)
                    record["families"].sort()
                reason = str(revision.get("reason") or "")
                if len(correction_ids) == 1:
                    single_reason.setdefault(correction_id, reason)
                    if correction_id not in catalogued:
                        record["findings"] = sorted(set(record["findings"]) | set(revision.get("findings") or []))
                else:
                    shared_reason.setdefault(correction_id, reason)
    for correction_id, record in index.items():
        record["golden_reason"] = single_reason.get(correction_id) or shared_reason.get(correction_id, "")
    return dict(sorted(index.items()))


# --------------------------------------------------------------------------
# Deltas


@dataclass
class Row:
    key: str
    kind: str
    zone: str
    section: str
    correction_ids: list[str] = field(default_factory=list)
    revisions: dict[str, list[int]] = field(default_factory=dict)
    unattributed_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "zone": self.zone,
            "section": self.section,
            "correction_ids": self.correction_ids,
            "revisions": self.revisions,
        }
        if self.unattributed_reason:
            payload["unattributed_reason"] = self.unattributed_reason
        return payload


def _touching_revisions(golden: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    """Column key -> the revisions (1..n) whose recorded delta changed it."""

    touched: dict[str, list[Mapping[str, Any]]] = {}
    for revision in (golden.get("revisions") or [])[1:]:
        for difference in (revision.get("delta") or {}).get("differences") or []:
            touched.setdefault(str(difference["key"]), []).append(revision)
    return touched


def _attribute(row: Row, side: str, revisions: Sequence[Mapping[str, Any]]) -> None:
    ids = set(row.correction_ids)
    for revision in revisions:
        ids |= set(revision.get("correction_ids") or [])
    row.correction_ids = sorted(ids)
    if revisions:
        row.revisions[side] = [int(revision.get("revision", -1)) for revision in revisions]


def _summarise(rows: Iterable[Row]) -> dict[str, Any]:
    rows = list(rows)
    by_zone = {zone: 0 for zone in ZONE_ORDER}
    by_correction: dict[str, dict[str, int]] = {}
    for row in rows:
        by_zone[row.zone] = by_zone.get(row.zone, 0) + 1
        for correction_id in row.correction_ids:
            counts = by_correction.setdefault(correction_id, {zone: 0 for zone in ZONE_ORDER})
            counts[row.zone] = counts.get(row.zone, 0) + 1
    unattributed = [row for row in rows if row.unattributed_reason]
    return {
        "count": len(rows),
        "by_zone": by_zone,
        "by_correction": dict(sorted(by_correction.items())),
        "unattributed": len(unattributed),
    }


def revision_zero_delta(golden: Mapping[str, Any]) -> list[Row]:
    """Rows of the latest digest that differ from revision 0, attributed."""

    revisions = golden.get("revisions") or []
    if len(revisions) < 2:
        return []
    pinned = golden_lib.pinned_zones(golden)
    differences = golden_lib.compare_digests(revisions[0]["digest"], revisions[-1]["digest"], "exact", pinned)
    touched = _touching_revisions(golden)
    rows: list[Row] = []
    for difference in differences:
        row = Row(difference.key, difference.kind, difference.zone, difference.section)
        _attribute(row, "self", touched.get(difference.key, []))
        if not touched.get(difference.key):
            row.unattributed_reason = "no revision recorded a change of this column"
        elif not row.correction_ids:
            row.unattributed_reason = "the revisions that changed it name findings but no correction id"
        rows.append(row)
    return rows


def case_configuration(case: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in case.items() if key not in _NON_CONFIGURATION_KEYS}


def configuration_difference(doctoral: Mapping[str, Any], corrected: Mapping[str, Any]) -> dict[str, Any]:
    """What a doctoral case sets that its corrected partner does not (and vice
    versa), apart from family, tier, title and trace level."""

    left = case_configuration(doctoral)
    right = case_configuration(corrected)
    difference: dict[str, Any] = {}
    for section in ("modules", "parameters"):
        a = dict(left.get(section) or {})
        b = dict(right.get(section) or {})
        changed = {
            key: {"doctoral": a.get(key), "corrected": b.get(key)}
            for key in sorted(set(a) | set(b))
            if a.get(key) != b.get(key)
        }
        if changed:
            difference[section] = changed
    for key in sorted((set(left) | set(right)) - {"modules", "parameters"}):
        if left.get(key) != right.get(key):
            difference[key] = {"doctoral": left.get(key), "corrected": right.get(key)}
    return difference


def profile_pairs(cases: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, str]]:
    """(doctoral case, corrected case) on the same data pack and mode.

    Among several corrected candidates the one with the fewest configuration
    differences wins (for D1 that is C4, legacy storage tariff on both
    sides); a doctoral case without a partner (D5, the GBP1 research pack) is
    reported as unpaired."""

    pairs: list[tuple[str, str]] = []
    for doctoral_id, doctoral in sorted(cases.items()):
        if doctoral.get("family") != "doctoral" or "pack" not in doctoral:
            continue
        candidates = [
            corrected_id
            for corrected_id, corrected in sorted(cases.items())
            if corrected.get("family") == "corrected"
            and corrected.get("pack") == doctoral.get("pack")
            and corrected.get("mode") == doctoral.get("mode")
            and corrected.get("network_variant") == doctoral.get("network_variant")
        ]
        if not candidates:
            continue

        def weight(corrected_id: str) -> tuple[int, str]:
            difference = configuration_difference(doctoral, cases[corrected_id])
            size = sum(len(value) if section in ("modules", "parameters") else 1 for section, value in difference.items())
            return (size, corrected_id)

        pairs.append((doctoral_id, min(candidates, key=weight)))
    return pairs


def dual_profile_delta(doctoral: Mapping[str, Any], corrected: Mapping[str, Any]) -> list[Row]:
    """Rows where the latest doctoral and corrected digests differ."""

    pinned_doctoral = golden_lib.pinned_zones(doctoral)
    pinned_corrected = golden_lib.pinned_zones(corrected)
    pinned = dict(pinned_corrected)
    for key, zone in pinned_doctoral.items():
        pinned[key] = golden_lib._stricter(pinned.get(key, zone), zone)
    doctoral_revisions = doctoral.get("revisions") or []
    corrected_revisions = corrected.get("revisions") or []
    differences = golden_lib.compare_digests(doctoral_revisions[-1]["digest"], corrected_revisions[-1]["digest"], "exact", pinned)
    baseline = {
        row.key
        for row in golden_lib.compare_digests(doctoral_revisions[0]["digest"], corrected_revisions[0]["digest"], "exact", pinned)
    }
    touched_doctoral = _touching_revisions(doctoral)
    touched_corrected = _touching_revisions(corrected)
    rows: list[Row] = []
    for difference in differences:
        row = Row(difference.key, difference.kind, difference.zone, difference.section)
        _attribute(row, "doctoral", touched_doctoral.get(difference.key, []))
        _attribute(row, "corrected", touched_corrected.get(difference.key, []))
        if difference.key in baseline:
            row.correction_ids = sorted(set(row.correction_ids) | {REFERENCE_CONFIGURATION_ID})
        if not row.correction_ids:
            touched_any = touched_doctoral.get(difference.key) or touched_corrected.get(difference.key)
            row.unattributed_reason = (
                "the revisions that changed it name findings but no correction id"
                if touched_any
                else "identical at revision 0 and no revision recorded a change of this column"
            )
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Report


def build_report(root: Path = ROOT) -> dict[str, Any]:
    cases = load_cases(root)
    goldens = load_goldens(root, cases)
    index = load_correction_index(root, goldens)
    case_reports: dict[str, Any] = {}
    for case_id, golden in goldens.items():
        rows = revision_zero_delta(golden)
        revisions = golden.get("revisions") or []
        case_reports[case_id] = {
            "family": golden.get("family"),
            "title": cases[case_id].get("title"),
            "tier": cases[case_id].get("tier"),
            "latest_revision": len(revisions) - 1,
            "revision_correction_ids": {
                str(revision.get("revision")): list(revision.get("correction_ids") or []) for revision in revisions[1:]
            },
            "summary": _summarise(rows),
            "rows": [row.to_dict() for row in rows],
        }
    pair_reports: list[dict[str, Any]] = []
    for doctoral_id, corrected_id in profile_pairs(cases):
        if doctoral_id not in goldens or corrected_id not in goldens:
            continue
        rows = dual_profile_delta(goldens[doctoral_id], goldens[corrected_id])
        pair_reports.append(
            {
                "doctoral": doctoral_id,
                "corrected": corrected_id,
                "configuration_difference": configuration_difference(cases[doctoral_id], cases[corrected_id]),
                "summary": _summarise(rows),
                "rows": [row.to_dict() for row in rows],
            }
        )
    paired = {pair["doctoral"] for pair in pair_reports}
    unpaired = sorted(case_id for case_id, case in cases.items() if case.get("family") == "doctoral" and case_id not in paired)
    unknown = sorted(
        {
            correction_id
            for report in list(case_reports.values()) + pair_reports
            for correction_id in report["summary"]["by_correction"]
            if correction_id != REFERENCE_CONFIGURATION_ID and correction_id not in index
        }
    )
    unattributed = sum(report["summary"]["unattributed"] for report in list(case_reports.values()) + pair_reports)
    return {
        "schema_version": SCHEMA_VERSION,
        "reference_configuration_id": REFERENCE_CONFIGURATION_ID,
        "cases": case_reports,
        "profile_pairs": pair_reports,
        "unpaired_doctoral_cases": unpaired,
        "missing_golden_files": sorted(set(cases) - set(goldens)),
        "corrections": index,
        "unknown_correction_ids": unknown,
        "unattributed_rows": unattributed,
    }


def attribution_errors(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for case_id, case in report["cases"].items():
        for row in case["rows"]:
            if row.get("unattributed_reason"):
                errors.append(f"{case_id} vs revision 0: {row['key']}: {row['unattributed_reason']}")
    for pair in report["profile_pairs"]:
        for row in pair["rows"]:
            if row.get("unattributed_reason"):
                errors.append(f"{pair['doctoral']} vs {pair['corrected']}: {row['key']}: {row['unattributed_reason']}")
    for correction_id in report["unknown_correction_ids"]:
        errors.append(f"correction id {correction_id} is not defined anywhere")
    return errors


def _counts(summary: Mapping[str, Any]) -> str:
    zones = summary["by_zone"]
    return " | ".join(str(zones.get(zone, 0)) for zone in ZONE_ORDER)


def _cell(counts: Mapping[str, int] | None) -> str:
    if not counts:
        return ""
    return "/".join(str(counts.get(zone, 0)) for zone in ZONE_ORDER)


def _short(text: str, limit: int = 150) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _source(record: Mapping[str, Any]) -> str:
    if record.get("catalogue_track"):
        return f"catalogue ({record['catalogue_track']})"
    if record.get("ledger_modules"):
        return "VERSION_LEDGER"
    return "golden revision"


def _value(value: Any) -> str:
    return "—" if value is None else f"`{value}`"


def render_markdown(report: Mapping[str, Any]) -> str:
    cases = report["cases"]
    lines = [
        "# P0 golden delta report",
        "",
        "Generated by `scripts/golden/delta_report.py --write` (plan X0 S13) from the committed",
        "golden files; do not edit by hand. `delta_report.py --check` (and",
        "`tests/test_golden_delta_report.py`) fail when a row cannot be attributed to a correction",
        "id or when this file is out of date. `delta_report.py --json <file>` writes every row.",
        "",
        "Counts are columns (artifact × column digests), written trajectory / accounting / identity",
        "(decision Q12). Identity columns are code, module and context hashes and version strings;",
        "the gate reports them but does not block on them. Magnitudes of the approved doctoral",
        "trajectory re-baselines are in `tests/golden/reports/` (`D4-r9.json`, `D5-r1.json`).",
        "",
        "## 1 Delta against revision 0 (35aadb3)",
        "",
        "| Case | Family | Tier | Title | Latest revision | Trajectory | Accounting | Identity | Unattributed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for case_id, case in cases.items():
        lines.append(
            f"| {case_id} | {case['family']} | {case['tier']} | {case['title']} | r{case['latest_revision']} | "
            f"{_counts(case['summary'])} | {case['summary']['unattributed']} |"
        )
    frozen = [case_id for case_id, case in cases.items() if case["family"] == "doctoral" and not case["summary"]["by_zone"]["trajectory"]]
    rebased = [case_id for case_id, case in cases.items() if case["family"] == "doctoral" and case["summary"]["by_zone"]["trajectory"]]
    lines += [
        "",
        "Doctoral trajectory columns change only under the universal corrections the author approved",
        "(`tests/golden/doctoral_trajectory_rebaselines.json`: P6-24, P6-02, P6-03, P6-04 and",
        "P4-01-thermal), each re-baselined once per case with a numeric report. Doctoral cases whose",
        f"trajectory columns are bit-identical to revision 0: {', '.join(frozen) or 'none'}; re-baselined:",
        f"{', '.join(rebased) or 'none'}. A revision that names several correction ids (D5 r1, the",
        "corrected M5 merge revisions) attributes each of its columns to all of them.",
        "",
        "### 1.1 Columns per correction id (trajectory/accounting/identity)",
        "",
        "A column changed by several revisions is counted under each of their correction ids.",
        "",
    ]
    ids = sorted({correction_id for case in cases.values() for correction_id in case["summary"]["by_correction"]})
    case_ids = list(cases)
    lines.append("| Correction id | " + " | ".join(case_ids) + " |")
    lines.append("|---|" + "---|" * len(case_ids))
    for correction_id in ids:
        lines.append(
            f"| `{correction_id}` | "
            + " | ".join(_cell(cases[case_id]["summary"]["by_correction"].get(correction_id)) for case_id in case_ids)
            + " |"
        )
    lines += [
        "",
        "## 2 Dual-profile delta (doctoral vs corrected, latest revisions)",
        "",
        "Each doctoral case is paired with the corrected case on the same data pack and mode with the",
        "fewest configuration differences. `" + REFERENCE_CONFIGURATION_ID + "` marks columns that already",
        "differed at revision 0: the doctoral reference configuration (decision Q3) and, where the",
        "corrected partner uses another storage-cost module, that module. It is a configuration",
        "difference, not a correction.",
        "",
        "| Doctoral | Corrected | Configuration difference | Trajectory | Accounting | Identity | Unattributed |",
        "|---|---|---|---|---|---|---|",
    ]
    for pair in report["profile_pairs"]:
        difference = pair["configuration_difference"]
        parts = []
        for section in ("modules", "parameters"):
            for key, values in (difference.get(section) or {}).items():
                parts.append(f"{key}: {_value(values['doctoral'])} vs {_value(values['corrected'])}")
        for key, values in difference.items():
            if key not in ("modules", "parameters"):
                parts.append(f"{key}: {_value(values['doctoral'])} vs {_value(values['corrected'])}")
        lines.append(
            f"| {pair['doctoral']} | {pair['corrected']} | {'; '.join(parts) or 'none'} | "
            f"{_counts(pair['summary'])} | {pair['summary']['unattributed']} |"
        )
    if report["unpaired_doctoral_cases"]:
        lines += [
            "",
            "Doctoral cases without a corrected partner on the same pack and mode: "
            + ", ".join(report["unpaired_doctoral_cases"])
            + ". (D5 runs the GBP1 research",
            "pack, which has no corrected golden case; its before/after comparison is a construction",
            "document outside the public source.)",
        ]
    lines += ["", "### 2.1 Columns per attribution (trajectory/accounting/identity)", ""]
    pair_ids = sorted({correction_id for pair in report["profile_pairs"] for correction_id in pair["summary"]["by_correction"]})
    labels = [f"{pair['doctoral']}↔{pair['corrected']}" for pair in report["profile_pairs"]]
    lines.append("| Attribution | " + " | ".join(labels) + " |")
    lines.append("|---|" + "---|" * len(labels))
    for correction_id in pair_ids:
        lines.append(
            f"| `{correction_id}` | "
            + " | ".join(_cell(pair["summary"]["by_correction"].get(correction_id)) for pair in report["profile_pairs"])
            + " |"
        )
    lines += [
        "",
        "## 3 Correction ids",
        "",
        "Source: `catalogue` = `gridform_core/data/methodology/corrections/*.json` (track `universal`",
        "applies to both profiles, `profile_gated` to the corrected profile only); `VERSION_LEDGER` =",
        "a module version bump in `docs/release/VERSION_LEDGER.json`; `golden revision` = recorded",
        "only as a golden revision reason. Families: the golden families with a revision naming the id.",
        "",
        "| Correction id | Source | Families | Findings | Module bumps | Description |",
        "|---|---|---|---|---|---|",
    ]
    for correction_id, record in report["corrections"].items():
        description = record.get("description") or record.get("golden_reason") or record.get("ledger_reason") or ""
        lines.append(
            f"| `{correction_id}` | {_source(record)} | {', '.join(record['families']) or '—'} | "
            f"{', '.join(record['findings']) or '—'} | {'; '.join(record['ledger_modules']) or '—'} | "
            f"{_short(description).replace('|', '/')} |"
        )
    lines += [
        "",
        "## 4 Attribution check",
        "",
        f"Unattributed rows: {report['unattributed_rows']}. Undefined correction ids: "
        f"{len(report['unknown_correction_ids'])}. Missing golden files: "
        f"{', '.join(report['missing_golden_files']) or 'none'}.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help=f"write {REPORT_PATH}")
    parser.add_argument("--check", action="store_true", help="fail on unattributed rows or a stale committed report")
    parser.add_argument("--json", type=Path, help="write the full report with every row to this file")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    report = build_report(root)
    markdown = render_markdown(report)
    if arguments.json:
        arguments.json.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    target = root / REPORT_PATH
    if arguments.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8", newline="\n")
    errors = attribution_errors(report)
    if arguments.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != markdown:
            errors.append(f"{REPORT_PATH} is out of date; run scripts/golden/delta_report.py --write")
        for error in errors:
            print(f"delta_report: {error}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "status": "failed" if errors else "passed",
                    "unattributed_rows": report["unattributed_rows"],
                    "errors": len(errors),
                }
            )
        )
        return 1 if errors else 0
    if not arguments.write and not arguments.json:
        sys.stdout.write(markdown)
    for error in errors:
        print(f"delta_report: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
