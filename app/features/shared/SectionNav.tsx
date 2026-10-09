"use client";

import { useEffect, useRef, useState } from "react";
import { activeSection, stickyOffset, type SectionLink } from "./sectionNav.ts";
import "./section-nav.css";

/**
 * P1 W4b (spec 6.4, R3-22): the sticky in-page navigation of a long page.
 * It sits below whatever is sticky at the top of the viewport (the top bar on
 * wide screens, the menu bar on narrow ones), marks the section in view with
 * aria-current, and its links are plain fragment links (keyboard, middle
 * click and copy-link work; the browser does the scrolling).
 */
export default function SectionNav({ label, sections, className }: { label: string; sections: readonly SectionLink[]; className?: string }) {
  const nav = useRef<HTMLElement>(null);
  const [current, setCurrent] = useState(sections[0]?.id ?? "");
  useEffect(() => {
    const element = nav.current;
    if (!element) return;
    const page = element.parentElement;
    let frame = 0;
    const update = () => {
      frame = 0;
      const top = stickyOffset(document, window.innerWidth);
      element.style.top = `${top}px`;
      // Fragment jumps land below the top bar and this bar (scroll-margin-top).
      page?.style.setProperty("--section-nav-offset", `${top + element.getBoundingClientRect().height + 8}px`);
      const tops = sections.map((section) => ({ id: section.id, top: document.getElementById(section.id)?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY }));
      setCurrent(activeSection(tops, top + element.getBoundingClientRect().height + 16));
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => { window.removeEventListener("scroll", schedule); window.removeEventListener("resize", schedule); if (frame) window.cancelAnimationFrame(frame); };
  }, [sections]);
  return <nav ref={nav} className={`section-nav${className ? ` ${className}` : ""}`} aria-label={label}>
    <ul>{sections.map((section) => <li key={section.id}>
      <a href={`#${section.id}`} aria-current={current === section.id ? "location" : undefined}>{section.label}{section.count != null && <span className="section-nav-count">{section.count}</span>}</a>
    </li>)}</ul>
  </nav>;
}
