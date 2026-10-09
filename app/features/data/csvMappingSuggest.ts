// F4-13 (P1 W4b, spec 6.3): after a CSV is staged, a canonical column whose
// name matches one source header is pre-selected as a suggestion. The user
// still checks every column (the hint stays until the column is changed) and
// confirms the whole review before anything is committed. Pure logic.
//
// Review W4b (major): the editor sets the suggested column's source unit to the
// canonical unit, so a header that names a different unit (capacity_kw for a
// MW column, demand_mw for an MWh column) must never be suggested: that would
// be a 1000x or 2x input error with no conversion. A header is suggested only
// when it states no unit or states exactly the canonical unit.

// Unit spellings found in header suffixes or brackets, normalised to one token.
const UNIT_ALIASES: Readonly<Record<string, string>> = {
  gbppermwh: "gbp/mwh", gbpmwh: "gbp/mwh", eurpermwh: "eur/mwh", eurmwh: "eur/mwh",
  gbpperkwh: "gbp/kwh", gbpkwh: "gbp/kwh", mwhperperiod: "mwh/period", mwhperiod: "mwh/period",
  mwelec: "mw", mwe: "mw", mw: "mw", kw: "kw", gw: "gw", mwh: "mwh", kwh: "kwh", gwh: "gwh", twh: "twh",
  mvar: "mvar", gbp: "gbp", eur: "eur", percent: "%", pct: "%",
};
// Longest spellings first, so "demand_mwh" ends in mwh rather than in an unrelated shorter unit.
const UNIT_SUFFIX = new RegExp(`(${Object.keys(UNIT_ALIASES).sort((a, b) => b.length - a.length).join("|")})$`);
const UNKNOWN_ANNOTATION = "?";

function squash(text: string): string { return text.toLowerCase().replace(/%/g, "percent").replace(/[^a-z0-9]+/g, ""); }

/** A canonical unit (as the data contract spells it, e.g. "MW", "GBP/MWh") as a comparable token, or null. */
export function unitToken(unit: string | null | undefined): string | null {
  if (unit === null || unit === undefined) return null;
  const key = squash(String(unit).replace(/\//g, "per"));
  return key ? UNIT_ALIASES[key] ?? key : null;
}

export interface HeaderParts {
  /** Lower case, separators removed, bracket contents kept: two headers with the same full form are the same header. */
  full: string;
  /** The name without bracketed annotations and without a unit suffix. */
  stem: string;
  /** Units the header states (suffix or brackets); "?" for a bracketed annotation that is not a known unit. */
  units: string[];
}

export function headerParts(name: string): HeaderParts {
  const text = String(name ?? "");
  const units: string[] = [];
  for (const match of text.matchAll(/\(([^)]*)\)|\[([^\]]*)\]/g)) {
    const inner = squash((match[1] ?? match[2] ?? "").replace(/\//g, "per"));
    if (inner) units.push(UNIT_ALIASES[inner] ?? UNKNOWN_ANNOTATION);
  }
  const base = squash(text.replace(/\([^)]*\)|\[[^\]]*\]/g, ""));
  const suffix = UNIT_SUFFIX.exec(base);
  let stem = base;
  if (suffix && suffix.index > 0) { stem = base.slice(0, suffix.index); units.push(UNIT_ALIASES[suffix[1]]); }
  return { full: squash(text), stem, units };
}

/** Whether a source header's stated units allow it to be read as the target unit with no conversion. */
function unitsAgree(sourceUnits: readonly string[], target: string | null): boolean {
  if (target === null) return sourceUnits.every((unit) => unit === UNKNOWN_ANNOTATION);
  return sourceUnits.every((unit) => unit === target);
}

/**
 * For each canonical target, the one source header with the same name (after
 * normalising case and separators) whose stated unit, if any, is the target's
 * canonical unit; "" when there is none or the match is ambiguous. A source
 * header is suggested for at most one target. `targetUnits[i]` is the
 * contract's target_unit; without it the unit stated in the target name is used.
 */
export function suggestSourceColumns(targets: readonly string[], sources: readonly string[], targetUnits?: readonly (string | null)[]): string[] {
  const sourceParts = sources.map((source) => ({ source, parts: headerParts(source) }));
  const candidates = targets.map((target, index) => {
    const parts = headerParts(target);
    const declared = targetUnits ? unitToken(targetUnits[index]) : null;
    const nameUnit = parts.units.find((unit) => unit !== UNKNOWN_ANNOTATION) ?? null;
    const unit = declared ?? nameUnit;
    if (!parts.stem) return "";
    // A header spelled exactly like the target may repeat its non-unit annotations; its stated units must still agree.
    const matches = sourceParts.filter(({ parts: other }) => other.stem === parts.stem
      && (unitsAgree(other.units, unit) || (other.full === parts.full && unitsAgree(other.units.filter((item) => item !== UNKNOWN_ANNOTATION), unit))));
    return matches.length === 1 ? matches[0].source : "";
  });
  const uses = new Map<string, number>();
  for (const source of candidates) if (source) uses.set(source, (uses.get(source) ?? 0) + 1);
  return candidates.map((source) => (source && uses.get(source) === 1 ? source : ""));
}
