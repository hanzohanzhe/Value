// Which data pack the "Draft data pack" selector falls back to (R4, four-role
// report R-低6). A pack recovered from a Run's frozen inputs, or a network
// overlay, is never chosen by default: after a strict replay the recovered
// copy sorted first by name and replaced the user's working pack on reload.

export type DraftPackCandidate = { id: string; complete?: boolean; data_pack_type?: string; frozen_recovery_origin?: unknown };

export function isRecoveredPack(pack: DraftPackCandidate): boolean {
  return Boolean(pack.frozen_recovery_origin);
}

/** Keep the current selection when it still exists; otherwise the first complete working pack. */
export function defaultDraftPackId(packs: readonly DraftPackCandidate[], current: string): string {
  if (packs.some((pack) => pack.id === current)) return current;
  const working = packs.filter((pack) => !isRecoveredPack(pack) && pack.data_pack_type !== "network_overlay");
  return working.find((pack) => pack.complete)?.id
    ?? packs.find((pack) => pack.complete && !isRecoveredPack(pack))?.id
    ?? working[0]?.id
    ?? packs[0]?.id
    ?? "";
}
