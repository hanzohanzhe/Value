"use client";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button.tsx";
import { useUiStrings } from "./useUiStrings.ts";
import "./Dialog.css";

/** Spec 2: a modal dialog on the native <dialog> - showModal() makes the rest
 * of the page inert (focus stays inside), Esc closes it, and focus returns to
 * the element that opened it. */
export function Dialog({ open, onClose, title, children, footer, closeLabel, className, initialFocus }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  closeLabel?: string;
  className?: string;
  /** CSS selector inside the dialog to focus first; defaults to the first control. */
  initialFocus?: string;
}) {
  const strings = useUiStrings();
  const closeText = closeLabel ?? strings.close;
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const id = useId();
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      node.showModal?.();
      const target = initialFocus ? node.querySelector<HTMLElement>(initialFocus) : null;
      target?.focus();
    } else if (!open && node.open) {
      node.close();
    }
  }, [open, initialFocus]);
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    const restore = () => { opener.current?.focus?.(); opener.current = null; };
    node.addEventListener("close", restore);
    return () => node.removeEventListener("close", restore);
  }, []);
  return <dialog
    ref={dialog}
    className={`v-dialog${className ? ` ${className}` : ""}`}
    aria-labelledby={`${id}-title`}
    onCancel={(event) => { event.preventDefault(); onClose(); }}
  >
    <header className="v-dialog__head">
      <h2 id={`${id}-title`} className="v-dialog__title">{title}</h2>
      <button type="button" className="v-dialog__close" aria-label={closeText} title={closeText} onClick={onClose}><span aria-hidden="true">×</span></button>
    </header>
    {children != null && <div className="v-dialog__body">{children}</div>}
    {footer != null && <footer className="v-dialog__foot">{footer}</footer>}
  </dialog>;
}

/** Spec 2: a confirmation whose text states the consequence; the confirm
 * button is danger-styled for irreversible actions. Reuse the wording the
 * repair rounds settled (quarantine, removal, deletion). */
export function Confirm({ open, title, consequence, confirmLabel, cancelLabel, danger = false, busy = false, onConfirm, onCancel, children }: {
  open: boolean;
  title: ReactNode;
  consequence: ReactNode;
  confirmLabel?: ReactNode;
  cancelLabel?: ReactNode;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}) {
  const strings = useUiStrings();
  return <Dialog open={open} onClose={onCancel} title={title} initialFocus=".v-dialog__cancel" footer={<>
    <Button variant="secondary" className="v-dialog__cancel" onClick={onCancel} disabled={busy}>{cancelLabel ?? strings.cancel}</Button>
    <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={busy}>{confirmLabel ?? strings.confirm}</Button>
  </>}>
    <p className="v-dialog__consequence">{consequence}</p>
    {children}
  </Dialog>;
}
