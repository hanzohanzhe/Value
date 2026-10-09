// Pure logic of the sticky in-page navigation (P1 W4b, spec 6.4, R3-22).

export type SectionLink = { id: string; label: string; count?: number | string };

type Box = { position: string; top: number; bottom: number; width: number };

/** How far below the viewport top a sticky page bar must sit: the bottom of
 * every element stuck to the top that spans the content column (the top bar on
 * wide screens, the menu bar on narrow ones). The sidebar is sticky too but is
 * a narrow column, so it is ignored. */
export function stickyOffsetFrom(boxes: readonly Box[], viewportWidth: number): number {
  let offset = 0;
  for (const box of boxes) {
    if (box.position !== "sticky" && box.position !== "fixed") continue;
    if (box.width < viewportWidth / 2) continue;
    if (box.top > 1) continue;
    offset = Math.max(offset, Math.round(Math.max(0, box.bottom)));
  }
  return offset;
}

export function stickyOffset(document: Document, viewportWidth: number): number {
  const boxes: Box[] = [];
  for (const selector of [".topbar", ".rail"]) {
    const element = document.querySelector(selector);
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    boxes.push({ position: getComputedStyle(element).position, top: rect.top, bottom: rect.bottom, width: rect.width });
  }
  return stickyOffsetFrom(boxes, viewportWidth);
}

/** The section in view: the last one whose top has passed the line under the
 * sticky bars; the first one before any has. */
export function activeSection(tops: readonly { id: string; top: number }[], line: number): string {
  let current = tops[0]?.id ?? "";
  for (const section of tops) if (section.top <= line) current = section.id;
  return current;
}
