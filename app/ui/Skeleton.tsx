import { UI_STRINGS } from "./strings.ts";
import "./Skeleton.css";

/** Spec 2: placeholder lines for the first load of a view only. */
export function Skeleton({ lines = 3, label = UI_STRINGS.loading }: { lines?: number; label?: string }) {
  return <div className="v-skeleton" role="status" aria-live="polite">
    <span className="v-visually-hidden">{label}</span>
    {Array.from({ length: Math.max(1, lines) }, (_, index) => <span key={index} className="v-skeleton__line" aria-hidden="true" />)}
  </div>;
}
