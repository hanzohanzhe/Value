"use client";

// The four research-task paths (P1 spec 6.1): cards on Home, the switch bar on
// the research guide (R3-07: only there, with the current task selected).
// Wording comes from the dictionaries (home.path.*).
import { useId } from "react";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";
import "./community-paths.css";

export type CommunityPath = "reproduce" | "data" | "module" | "function";

export type CommunityPathsProps = {
  activePath: CommunityPath | null;
  onSelect: (path: CommunityPath) => void;
};

/** The paths in order; their wording is `home.path.<id>.label|description|capability`. */
export const COMMUNITY_PATHS: ReadonlyArray<{ id: CommunityPath }> = [
  { id: "reproduce" }, { id: "data" }, { id: "module" }, { id: "function" },
];

export const pathKey = (id: CommunityPath, part: "label" | "description" | "capability") => ("home.path." + id + "." + part) as MessageKey;

export function CommunityHome({ activePath, onSelect }: CommunityPathsProps) {
  const t = useT();
  const descriptionId = useId();
  return (
    <section className="community-home" aria-label={t("home.tasksLabel")}>
      <div className="community-path-grid">
        {COMMUNITY_PATHS.map((path) => {
          const detailId = `${descriptionId}-${path.id}`;
          return (
            <button
              type="button"
              className="community-path-card"
              key={path.id}
              aria-label={t(pathKey(path.id, "label"))}
              aria-describedby={detailId}
              aria-pressed={activePath === path.id}
              onClick={() => onSelect(path.id)}
              data-community-path={path.id}
            >
              <span className="community-path-title" lang="en">{t(pathKey(path.id, "label"))}</span>
              <span className="community-path-description">{t(pathKey(path.id, "description"))}</span>
              <span className="community-path-capability" id={detailId}>
                <span>{t("home.path.supported")}</span>
                {t(pathKey(path.id, "capability"))}
              </span>
              <span className="community-path-open" aria-hidden="true">{t("home.path.open")}</span>
            </button>
          );
        })}
      </div>
      <p className="community-home-note">{t("home.path.note")}</p>
    </section>
  );
}

export function CommunityPathPicker({ activePath, onSelect }: CommunityPathsProps) {
  const t = useT();
  return (
    <nav className="community-path-picker" aria-label={t("home.tasksLabel")}>
      {COMMUNITY_PATHS.map((path) => (
        <button
          key={path.id}
          type="button"
          aria-pressed={activePath === path.id}
          onClick={() => onSelect(path.id)}
          data-community-path={path.id}
          lang="en"
        >
          {t(pathKey(path.id, "label"))}
        </button>
      ))}
    </nav>
  );
}
