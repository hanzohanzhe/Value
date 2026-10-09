"use client";

import { apiFetch } from "../../lib/api.ts";
import { Fragment, useEffect, useId, useRef, useState } from "react";
import "./community-paths.css";
import { useT } from "../../i18n/LocaleProvider";

export const README_URL = "/README.md";

export type ReadMePanelProps = {
  open: boolean;
  onClose: () => void;
};

type ReadMeBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; headers: string[]; rows: string[][] };

type ReadMeState =
  | { status: "idle" | "loading" | "error" }
  | { status: "ready"; blocks: ReadMeBlock[] };

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

/** A deliberately small, text-only Markdown reader. Raw HTML and links remain text. */
export function parseReadMe(source: string): ReadMeBlock[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReadMeBlock[] = [];
  const heading = /^(#{1,3})\s+(.+)$/;
  const list = /^(?:\d+\.|[-*])\s+/;
  const separator = /^\|?(?:\s*:?-{3,}:?\s*\|)+\s*$/;
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    const title = line.match(heading);
    if (title) {
      blocks.push({ kind: "heading", level: title[1].length, text: title[2] });
      index += 1;
    } else if (line.startsWith("|") && separator.test((lines[index + 1] || "").trim())) {
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push({ kind: "table", headers, rows });
    } else if (list.test(line)) {
      const ordered = /^\d+\./.test(line);
      const sameList = ordered ? /^\d+\.\s+/ : /^[-*]\s+/;
      const items: string[] = [];
      while (index < lines.length && sameList.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(sameList, ""));
        index += 1;
      }
      blocks.push({ kind: "list", ordered, items });
    } else {
      const paragraph = [line];
      index += 1;
      while (index < lines.length && lines[index].trim()
        && !heading.test(lines[index].trim())
        && !list.test(lines[index].trim())
        && !lines[index].trim().startsWith("|")) {
        paragraph.push(lines[index].trim());
        index += 1;
      }
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    }
  }
  return blocks;
}

function InlineText({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>
  )}</>;
}

function ReadMeContent({ blocks }: { blocks: ReadMeBlock[] }) {
  return <div className="value-readme-content">{blocks.map((block, index) => {
    if (block.kind === "heading") {
      const Heading = block.level === 1 ? "h2" : block.level === 2 ? "h3" : "h4";
      return <Heading key={index}><InlineText text={block.text} /></Heading>;
    }
    if (block.kind === "list") {
      const List = block.ordered ? "ol" : "ul";
      return <List key={index}>{block.items.map((item, itemIndex) =>
        <li key={itemIndex}><InlineText text={item} /></li>
      )}</List>;
    }
    if (block.kind === "table") {
      return <table key={index}>
        <thead><tr>{block.headers.map((cell, cellIndex) =>
          <th key={cellIndex} scope="col"><InlineText text={cell} /></th>
        )}</tr></thead>
        <tbody>{block.rows.map((row, rowIndex) => <tr key={rowIndex}>
          {block.headers.map((_, cellIndex) =>
            <td key={cellIndex}><InlineText text={row[cellIndex] || ""} /></td>
          )}
        </tr>)}</tbody>
      </table>;
    }
    return <p key={index}><InlineText text={block.text} /></p>;
  })}</div>;
}

export function ReadMePanel({ open, onClose }: ReadMePanelProps) {
  const t = useT();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [content, setContent] = useState<ReadMeState>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let active = true;
    // Defer until after setup so an abandoned Strict Mode effect starts no request.
    void Promise.resolve().then(async () => {
      if (!active) return;
      setContent({ status: "loading" });
      try {
        const response = await apiFetch(README_URL, { signal: controller.signal, cache: "no-cache" });
        // A missing asset can be served as a successful app-shell fallback.
        if (!response.ok || response.headers.get("content-type")?.includes("text/html")) {
          throw new Error("Read me unavailable");
        }
        const source = await response.text();
        if (!source.trim()) throw new Error("Read me is empty");
        if (active) setContent({ status: "ready", blocks: parseReadMe(source) });
      } catch {
        if (active) setContent({ status: "error" });
      }
    });
    return () => { active = false; controller.abort(); };
  }, [open, attempt]);

  return (
    <dialog
      ref={dialogRef}
      className="value-readme-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <header className="value-readme-header">
        <h2 id={titleId}>{t("readme.title")}</h2>
        <button type="button" className="value-readme-close" onClick={onClose} aria-label={t("readme.closeLabel")}>{t("readme.close")}</button>
      </header>
      <div className="value-readme-body">
        {/* R3M-7 (round R2): the status line exists only while the Read me is being read. */}
        {content.status === "loading" && <p role="status">{t("readme.loading")}</p>}
        {content.status === "error" && <div className="value-readme-error" role="alert">
          <p>{t("readme.error")}</p>
          <button type="button" className="secondary" onClick={() => {
            setContent({ status: "loading" });
            setAttempt((value) => value + 1);
          }}>{t("readme.retry")}</button>
          <a href={README_URL} target="_blank" rel="noreferrer">{t("readme.original")}</a>
        </div>}
        {content.status === "ready" && <ReadMeContent blocks={content.blocks} />}
      </div>
    </dialog>
  );
}

export default ReadMePanel;
