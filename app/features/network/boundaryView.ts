// Boundary limits and flow direction on the network page (P1 spec 6.5; the
// display part of F3-13). The ledger records a corridor limit as energy per
// model period (forward_limit_mw x period_hours); the page shows it as the
// power limit in MW. Pure view logic: the recorded values are not changed.

/** A per-period energy limit (MWh in one period) as a power limit in MW; null when missing. */
export function limitMw(mwhPerPeriod: number | null | undefined, periodHours: number | null | undefined): number | null {
  if (typeof mwhPerPeriod !== "number" || !Number.isFinite(mwhPerPeriod)) return null;
  const hours = typeof periodHours === "number" && Number.isFinite(periodHours) && periodHours > 0 ? periodHours : null;
  return hours == null ? null : mwhPerPeriod / hours;
}

export type FlowDirection = "forward" | "reverse" | "none";

/** The direction of a signed corridor transfer: positive is the network pack's declared forward direction. */
export function flowDirection(transferMwh: number | null | undefined): FlowDirection | null {
  if (typeof transferMwh !== "number" || !Number.isFinite(transferMwh)) return null;
  return transferMwh > 0 ? "forward" : transferMwh < 0 ? "reverse" : "none";
}

/** The arrow shown before a transfer's absolute value. */
export const FLOW_ARROWS: Readonly<Record<FlowDirection, string>> = { forward: "→", reverse: "←", none: "·" };
