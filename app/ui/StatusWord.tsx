import { valueStateText, valueStateTone, type ValueStateKey, type ValueStateTone } from "../features/shared/valueStates.ts";
import "./StatusWord.css";

// Shape of the icon per tone, so the state is not told by colour alone.
const ICONS: Record<ValueStateTone, string> = { muted: "○", amber: "!", red: "×", blue: "…" };

/** Spec 2: the state word from valueStates.ts with its colour and an icon. */
export function StatusWord({ state, coveragePercent, title, className }: { state: ValueStateKey; coveragePercent?: number | null; title?: string; className?: string }) {
  const tone = valueStateTone(state);
  return <span className={`v-status v-status--${tone}${className ? ` ${className}` : ""}`} title={title} data-state={state}>
    {state !== "missing" && <span className="v-status__icon" aria-hidden="true">{ICONS[tone]}</span>}
    <span className="v-status__text">{valueStateText(state, coveragePercent)}</span>
  </span>;
}
