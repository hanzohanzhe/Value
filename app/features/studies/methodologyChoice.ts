// The Methodology choice of a Study (spec 7, plan X0 S12; DECISIONS Q2, Q3, Q13).
// The catalogue comes from GET /api/methodology/profiles; the server's draft
// resolution and preflight remain the authority on whether a combination is
// supported (one whitelist check, C16). This module only pre-disables what the
// catalogue already rules out and applies a frozen profile's reference preset.

export const PROFILE_PARAMETER = "methodology.profile";

export type PackEntry = { id: string; label?: string; pack_class?: string; manifest_sha256?: string | string[] };
export type MethodologyProfile = {
  id: string;
  version?: string;
  label: string;
  note?: string;
  frozen: boolean;
  default: boolean;
  supported_modules?: "*" | Record<string, string[]>;
  supported_extensions?: "*" | string[];
  supported_data_packs?: "*" | PackEntry[];
  external_code_policy?: string;
  reference_configuration?: { modules?: Record<string, string>; parameters?: Record<string, unknown> };
};
export type MethodologyCatalogue = { schema_version?: string; default_profile_id: string; catalogue_sha256?: string; profiles: MethodologyProfile[] };

export const DOCTORAL_OPTION_DESCRIPTION = "Locks thesis-era reference settings: legacy storage tariff, doctoral carbon factors, thesis-era modules and data packs only. External code is not allowed.";

export function isMethodologyCatalogue(value: unknown): value is MethodologyCatalogue {
  if (!value || typeof value !== "object") return false;
  const catalogue = value as MethodologyCatalogue;
  return typeof catalogue.default_profile_id === "string" && Array.isArray(catalogue.profiles)
    && catalogue.profiles.every((profile) => profile && typeof profile.id === "string" && typeof profile.label === "string");
}

/** Spec 7 option labels: the default profile and the frozen reproduction profile. */
export function profileOptionLabel(profile: MethodologyProfile): string {
  if (profile.default) return "Corrected (default)";
  if (profile.frozen) return "Doctoral reproduction";
  return profile.label;
}

export function profileOptionDescription(profile: MethodologyProfile): string | null {
  return profile.frozen ? DOCTORAL_OPTION_DESCRIPTION : null;
}

/** The profile a draft uses: its explicit parameter, else the catalogue default. */
export function selectedProfileId(parameters: Record<string, unknown>, catalogue: MethodologyCatalogue | null | undefined): string | null {
  const explicit = parameters[PROFILE_PARAMETER];
  if (typeof explicit === "string" && explicit) return explicit;
  return catalogue?.default_profile_id ?? null;
}

export function findProfile(catalogue: MethodologyCatalogue | null | undefined, id: string | null | undefined): MethodologyProfile | undefined {
  return id ? catalogue?.profiles.find((profile) => profile.id === id) : undefined;
}

export type Availability = { available: true } | { available: false; reason: string };

function profileName(profile: MethodologyProfile): string {
  return profileOptionLabel(profile);
}

/** A data pack is pre-disabled only when its id is not listed at all; pinned-content checks stay on the server. */
export function dataPackAvailability(profile: MethodologyProfile | undefined, packId: string): Availability {
  const packs = profile?.supported_data_packs;
  if (!profile || packs === undefined || packs === "*") return { available: true };
  if (packs.some((entry) => entry.id === "*" || entry.id === packId)) return { available: true };
  const listed = packs.map((entry) => entry.label ?? entry.id).join(", ");
  return { available: false, reason: `${profileName(profile)} uses thesis-era data packs only (${listed}).` };
}

export function extensionAvailability(profile: MethodologyProfile | undefined, extensionId: string): Availability {
  const extensions = profile?.supported_extensions;
  if (!profile || extensions === undefined || extensions === "*" || extensions.includes(extensionId)) return { available: true };
  return { available: false, reason: `${profileName(profile)} does not run optional extensions or external code.` };
}

/** Module options carry the server's verdict for the selected profile (draft resolution). */
export function moduleAvailability(option: { methodology_supported?: boolean; methodology_reason?: string | null }, profile: MethodologyProfile | undefined): Availability {
  if (option.methodology_supported !== false) return { available: true };
  return { available: false, reason: option.methodology_reason ?? `Not part of ${profile ? profileName(profile) : "the selected methodology"}.` };
}

/**
 * The draft after choosing a profile (Q3: a frozen profile writes its reference
 * configuration explicitly; a module preset replaces only a slot the draft
 * already uses). Leaving a frozen profile removes only the parameter
 * overrides that still equal its reference values; modules stay as they are.
 */
export function applyProfileChoice(
  draft: { parameters: Record<string, unknown>; modules: Record<string, string> },
  profileId: string,
  catalogue: MethodologyCatalogue,
): { parameters: Record<string, unknown>; modules: Record<string, string> } {
  const parameters = { ...draft.parameters };
  const modules = { ...draft.modules };
  for (const profile of catalogue.profiles) {
    if (!profile.frozen || profile.id === profileId) continue;
    for (const [key, value] of Object.entries(profile.reference_configuration?.parameters ?? {})) {
      if (parameters[key] === value) delete parameters[key];
    }
  }
  const chosen = findProfile(catalogue, profileId);
  parameters[PROFILE_PARAMETER] = profileId;
  if (chosen?.frozen) {
    Object.assign(parameters, chosen.reference_configuration?.parameters ?? {});
    for (const [slot, moduleId] of Object.entries(chosen.reference_configuration?.modules ?? {})) {
      if (slot in modules) modules[slot] = moduleId;
    }
  }
  return { parameters, modules };
}

/**
 * R4 R-低7: the badge of a step-2 domain card. A formulation the selected
 * methodology does not admit reads "not available with this methodology"
 * (as an inadmissible data pack does in step 1), not its maturity "ready".
 */
export function domainBadgeText(maturity: string, methodologyAvailable: boolean): string {
  return methodologyAvailable ? maturity.replaceAll("_", " ") : "not available with this methodology";
}

/**
 * R5 R-中1: the methodology a saved Study runs under, for pages that show a
 * Study before it runs (research journey, Runs "What will run"). The label is
 * the composer's option label; without the catalogue the recorded id is shown,
 * and a Study without an explicit choice uses the default profile.
 */
export function studyMethodologyText(parameters: Record<string, unknown> | null | undefined, catalogue: MethodologyCatalogue | null | undefined): { label: string; profileId: string | null; frozen: boolean } {
  const profileId = selectedProfileId(parameters ?? {}, catalogue);
  const profile = findProfile(catalogue, profileId);
  if (profile) return { label: profileOptionLabel(profile), profileId, frozen: profile.frozen };
  return { label: profileId ?? "Default methodology", profileId, frozen: false };
}
