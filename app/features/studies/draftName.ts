// R5 F-中2 (four-role add-feature report): the server derives a new Study's
// ID from its name (backend/server.py `slug`). A second independent draft
// opened from the same baseline kept the same default name, so saving it hit
// the existing Study and was refused. The draft name is made unique up front.

/** The Study ID the server derives from a name: mirrors backend/server.py `slug(value, "project")`. */
export function studyIdFromName(name: string): string {
  const safe = name.trim().replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return safe.slice(0, 64) || "project";
}

/** `name`, or `name 2`, `name 3`, … : the first whose derived ID no listed Study uses. */
export function uniqueStudyName(name: string, projects: readonly { id: string }[]): string {
  const taken = new Set(projects.map((project) => project.id));
  if (!taken.has(studyIdFromName(name))) return name;
  // A suffix past the 64-character ID limit would be cut off, so a long name
  // is shortened before the number is appended.
  for (let index = 2; index < 1000; index += 1) {
    const suffix = ` ${index}`;
    let base = name;
    while (base.length > 1 && !studyIdFromName(`${base}${suffix}`).endsWith(`-${index}`)) {
      base = base.slice(0, -1).trimEnd();
    }
    const candidate = `${base}${suffix}`;
    if (!taken.has(studyIdFromName(candidate))) return candidate;
  }
  return name;
}
