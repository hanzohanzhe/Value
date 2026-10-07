// R3-N4 (four-role report, round R2): saved Studies may share a name (the
// backend allows it); the research journey warns before a second one is made.

/** True when `name` (trimmed, case-insensitive) is already the name of a saved Study. */
export function studyNameTaken(studies: readonly { name: string }[], name: string): boolean {
  const wanted = name.trim().toLowerCase();
  return Boolean(wanted) && studies.some((study) => study.name.trim().toLowerCase() === wanted);
}
