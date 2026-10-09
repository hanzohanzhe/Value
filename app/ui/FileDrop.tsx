"use client";
import { useId, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { formatBytes } from "../features/shared/presentation.tsx";
import { useUiStrings } from "./useUiStrings.ts";
import "./FileDrop.css";

/** Spec 2: a file box that opens with Enter or Space, accepts a dropped file,
 * looks disabled when disabled, and shows the chosen file's name and size. */
export function FileDrop({ label, hint, accept, disabled = false, disabledReason, multiple = false, onFiles, prompt, emptyText, className }: {
  label: ReactNode;
  hint?: ReactNode;
  accept?: string;
  disabled?: boolean;
  disabledReason?: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
  prompt?: ReactNode;
  emptyText?: ReactNode;
  className?: string;
}) {
  const strings = useUiStrings();
  const input = useRef<HTMLInputElement>(null);
  const id = useId();
  const [files, setFiles] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  function choose(list: FileList | null) {
    const chosen = list ? Array.from(list) : [];
    if (!chosen.length) return;
    setFiles(chosen);
    onFiles(chosen);
  }
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.current?.click();
    }
  }
  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setOver(false);
    if (!disabled) choose(event.dataTransfer.files);
  }
  return <div className={`v-filedrop${disabled ? " is-disabled" : ""}${over ? " is-over" : ""}${className ? ` ${className}` : ""}`}>
    <span className="v-filedrop__label" id={`${id}-label`}>{label}</span>
    <div
      className="v-filedrop__zone"
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || undefined}
      aria-labelledby={`${id}-label ${id}-prompt`}
      aria-describedby={hint != null ? `${id}-hint` : undefined}
      title={disabled ? disabledReason : undefined}
      onClick={() => { if (!disabled) input.current?.click(); }}
      onKeyDown={onKeyDown}
      onDragOver={(event) => { event.preventDefault(); if (!disabled) setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <span className="v-filedrop__prompt" id={`${id}-prompt`}>{prompt ?? strings.chooseFile}</span>
      <span className="v-filedrop__files" aria-live="polite">
        {files.length ? files.map((file) => <span key={`${file.name}-${file.size}-${file.lastModified}`} className="v-filedrop__file"><b>{file.name}</b> <small>{formatBytes(file.size)}</small></span>) : <small>{emptyText ?? strings.noFileChosen}</small>}
      </span>
    </div>
    <input ref={input} className="v-visually-hidden" type="file" tabIndex={-1} aria-hidden="true" accept={accept} multiple={multiple} disabled={disabled} onChange={(event) => { choose(event.target.files); event.target.value = ""; }} />
    {hint != null && <p className="v-field__hint" id={`${id}-hint`}>{hint}</p>}
  </div>;
}
