import type { ReactNode } from "react";
import { UI_STRINGS } from "./strings.ts";
import "./Stepper.css";

export type StepState = "done" | "current" | "todo";
export type StepItem = { id: string; label: ReactNode; state: StepState; hint?: ReactNode };

/** Spec 2: the research-path step bar; the current step is selected
 * (aria-current="step") and steps may be buttons when `onSelect` is given. */
export function Stepper({ steps, onSelect, label = UI_STRINGS.steps }: { steps: readonly StepItem[]; onSelect?: (id: string) => void; label?: string }) {
  return <nav className="v-stepper" aria-label={label}>
    <ol>
      {steps.map((step, index) => {
        const body = <>
          <span className="v-stepper__mark" aria-hidden="true">{step.state === "done" ? "✓" : index + 1}</span>
          <span className="v-stepper__text"><b>{step.label}</b>{step.hint != null && <small>{step.hint}</small>}</span>
        </>;
        return <li key={step.id} className={`v-stepper__step is-${step.state}`} aria-current={step.state === "current" ? "step" : undefined}>
          {onSelect ? <button type="button" onClick={() => onSelect(step.id)}>{body}</button> : <span className="v-stepper__static">{body}</span>}
        </li>;
      })}
    </ol>
  </nav>;
}
