"use client";
import { useEffect, type ReactNode } from "react";
import { useUiStrings } from "./useUiStrings.ts";
import "./Toast.css";

export type ToastTone = "success" | "error" | "info";
const ICONS: Record<ToastTone, string> = { success: "✓", error: "×", info: "i" };

/** Spec 2: success and failure look different (style and icon). Failure is
 * assertive and stays until dismissed; success/info are polite and may close
 * themselves after `autoDismissMs`. */
export function Toast({ tone, children, onDismiss, autoDismissMs = 6000, dismissLabel }: {
  tone: ToastTone;
  children: ReactNode;
  onDismiss?: () => void;
  autoDismissMs?: number | null;
  dismissLabel?: string;
}) {
  const strings = useUiStrings();
  const dismissText = dismissLabel ?? strings.dismiss;
  const autoClose = tone !== "error" && onDismiss && autoDismissMs != null && autoDismissMs > 0;
  useEffect(() => {
    if (!autoClose) return;
    const timer = window.setTimeout(() => onDismiss?.(), autoDismissMs ?? 0);
    return () => window.clearTimeout(timer);
  }, [autoClose, autoDismissMs, onDismiss]);
  return <div className={`v-toast v-toast--${tone}`} role={tone === "error" ? "alert" : "status"} aria-live={tone === "error" ? "assertive" : "polite"}>
    <span className="v-toast__icon" aria-hidden="true">{ICONS[tone]}</span>
    <div className="v-toast__text">{children}</div>
    {onDismiss && <button type="button" className="v-toast__dismiss" aria-label={dismissText} title={dismissText} onClick={onDismiss}><span aria-hidden="true">×</span></button>}
  </div>;
}

/** Fixed stack the page renders its toasts into (bottom right, above content). */
export function ToastStack({ children }: { children: ReactNode }) {
  return <div className="v-toast-stack">{children}</div>;
}
