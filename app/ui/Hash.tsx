"use client";
import { useState } from "react";
import { useUiStrings } from "./useUiStrings.ts";
import { shortHash } from "./hashText.ts";
export { shortHash, HASH_PREFIX_LENGTH } from "./hashText.ts";
import "./Hash.css";

/** Spec 2: a hash or long ID shown as its first 12 characters, the full value
 * in the title and a copy button. */
export function Hash({ value, label, copyLabel, className }: { value: string; label?: string; copyLabel?: string; className?: string }) {
  const strings = useUiStrings();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("failed");
    }
  }
  const status = state === "copied" ? strings.copied : state === "failed" ? strings.copyFailed : "";
  return <span className={`v-hash${className ? ` ${className}` : ""}`}>
    <code title={value} aria-label={label ? `${label}: ${value}` : value}>{shortHash(value)}</code>
    <button type="button" className="v-hash__copy" onClick={() => void copy()} title={`${strings.copyFullValue}: ${value}`}>{copyLabel ?? strings.copy}</button>
    <span className="v-hash__status" role="status" aria-live="polite">{status}</span>
  </span>;
}
