// S-F-中1 (R5, four-role swap-data report): the Data page resolves the data
// roles of the Study in context once per Study content. A workspace poll while
// a Run is going returns new Study objects with the same content (and a new
// linked_run_count when the Run starts); neither changes which data roles the
// Study needs, so neither may reset the resolution - that reset remounted the
// CSV mapping editor and dropped the staged file.

/** Presentation fields of a listed Study that do not change its data resolution. */
const PRESENTATION_ONLY_FIELDS = ["linked_run_count", "warnings"] as const;

/** The request body of POST projects/resolve-draft for this Study, or "" without one. */
export function studyResolutionKey(project: object | null | undefined): string {
  if (!project) return "";
  const copy: Record<string, unknown> = { ...(project as Record<string, unknown>) };
  for (const field of PRESENTATION_ONLY_FIELDS) delete copy[field];
  return JSON.stringify(copy);
}
