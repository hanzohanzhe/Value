import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// P1 frontend overhaul spec 2: one render test per shared component (W1).
const h = React.createElement;

test("Button: four variants, two sizes; loading disables and shows progress; disabled says why", async () => {
  const primary = await renderTsx("app/ui/Button.tsx", "Button", { variant: "primary", size: "sm", children: "Start Run" });
  assert.match(primary, /<button type="button" class="v-btn v-btn--primary v-btn--sm">/);
  for (const variant of ["secondary", "ghost", "danger"]) {
    assert.match(await renderTsx("app/ui/Button.tsx", "Button", { variant, children: "x" }), new RegExp(`v-btn--${variant} v-btn--md`));
  }
  const loading = await renderTsx("app/ui/Button.tsx", "Button", { variant: "primary", loading: true, children: "Saving" });
  assert.match(loading, /disabled=""/);
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /class="v-btn__spinner" aria-hidden="true"/);
  assert.equal(textOf(loading), "Saving Working");
  const disabled = await renderTsx("app/ui/Button.tsx", "Button", { disabled: true, disabledReason: "Select a Study first", title: "Run", children: "Run" });
  assert.match(disabled, /disabled="" title="Select a Study first"/);
  const enabled = await renderTsx("app/ui/Button.tsx", "Button", { disabledReason: "Select a Study first", title: "Run", children: "Run" });
  assert.match(enabled, /title="Run"/);
  assert.doesNotMatch(enabled, /disabled=""/);
});

test("IconButton always carries an aria-label", async () => {
  const html = await renderTsx("app/ui/Button.tsx", "IconButton", { label: "Close panel", icon: "×" });
  assert.match(html, /aria-label="Close panel"/);
  assert.match(html, /<span aria-hidden="true">×<\/span>/);
});

test("PageHeader is one line: an h2 that can take focus (the shell top bar holds the only h1, R-11), one sentence and actions", async () => {
  const html = await renderTsx("app/ui/PageHeader.tsx", "PageHeader", { title: "Runs", description: "Launch, follow and compare Runs.", actions: h("button", null, "New Run") });
  assert.match(html, /<header class="v-page-header">/);
  assert.match(html, /<h2 tabindex="-1">Runs<\/h2>/);
  assert.match(await renderTsx("app/ui/PageHeader.tsx", "PageHeader", { title: "Runs", headingLevel: 1 }), /<h1 tabindex="-1">Runs<\/h1>/);
  assert.match(html, /<p>Launch, follow and compare Runs\.<\/p>/);
  assert.match(html, /<div class="v-page-header__actions"><button>New Run<\/button><\/div>/);
});

test("Card has header, body and footer; Panel collapses with details/summary; Disclosure is native", async () => {
  const card = await renderTsx("app/ui/Card.tsx", "Card", { title: "Data pack", eyebrow: "Study input", actions: "Edit", footer: "Updated", children: "Body" });
  assert.match(card, /<section class="v-card"><header class="v-card__head">/);
  assert.match(card, /<h2 class="v-card__title">Data pack<\/h2>/);
  assert.match(card, /<div class="v-card__body">Body<\/div><footer class="v-card__foot">Updated<\/footer><\/section>/);
  const panel = await renderTsx("app/ui/Card.tsx", "Panel", { title: "Advanced", collapsible: true, defaultOpen: false, children: "Hidden" });
  assert.match(panel, /^<details class="v-card v-panel v-panel--collapsible"><summary class="v-card__head">/);
  assert.doesNotMatch(panel, /<details[^>]* open/);
  const open = await renderTsx("app/ui/Card.tsx", "Panel", { title: "Advanced", collapsible: true, children: "Shown" });
  assert.match(open, /<details class="v-card v-panel v-panel--collapsible" open="">/);
  const plain = await renderTsx("app/ui/Card.tsx", "Panel", { title: "Static", children: "x" });
  assert.match(plain, /^<section class="v-card v-panel">/);
  const disclosure = await renderTsx("app/ui/Card.tsx", "Disclosure", { summary: "Definitions", children: "text" });
  assert.match(disclosure, /^<details class="v-disclosure"><summary>/);
});

test("Tabs follow the WAI-ARIA pattern: linked tab/tabpanel, roving tabindex", async () => {
  const html = await renderTsx("app/ui/Tabs.tsx", "Tabs", {
    idBase: "t", label: "Inspect sections", value: "events", onChange() {},
    tabs: [{ id: "items", label: "Items" }, { id: "events", label: "Events" }, { id: "raw", label: "Raw", disabled: true }],
    children: "event list",
  });
  assert.match(html, /role="tablist" aria-label="Inspect sections"/);
  assert.match(html, /role="tab" id="t-tab-items" aria-selected="false" aria-controls="t-panel-items" tabindex="-1"/);
  assert.match(html, /role="tab" id="t-tab-events" aria-selected="true" aria-controls="t-panel-events" tabindex="0"/);
  assert.match(html, /id="t-tab-raw"[^>]*disabled=""/);
  assert.match(html, /role="tabpanel" id="t-panel-events" aria-labelledby="t-tab-events" tabindex="0">event list</);
});

test("DataTable: caption, scoped headers, numeric alignment, labelled focusable scroll region", async () => {
  const html = await renderTsx("app/ui/DataTable.tsx", "DataTable", {
    caption: "Annual energy",
    rows: [{ id: "r1", tech: "Solar", mwh: "1,200" }, { id: "r2", tech: "Wind", mwh: "3,400" }],
    rowKey: (row) => row.id,
    columns: [
      { key: "tech", header: "Technology", rowHeader: true, render: (row) => row.tech },
      { key: "mwh", header: "Energy (MWh)", numeric: true, render: (row) => row.mwh },
    ],
  });
  assert.match(html, /^<div class="v-table-scroll" tabindex="0" role="region" aria-label="Annual energy">/);
  assert.match(html, /<caption>Annual energy<\/caption>/);
  assert.match(html, /<th scope="col">Technology<\/th><th scope="col" class="v-num">Energy \(MWh\)<\/th>/);
  assert.match(html, /<th scope="row">Solar<\/th><td class="v-num">1,200<\/td>/);
  const empty = await renderTsx("app/ui/DataTable.tsx", "DataTable", { caption: "x", rows: [], rowKey: (row) => row.id, columns: [], empty: h("p", null, "No rows yet") });
  assert.equal(empty, "<p>No rows yet</p>");
});

test("StatusWord takes word and colour from valueStates and adds an icon", async () => {
  const red = await renderTsx("app/ui/StatusWord.tsx", "StatusWord", { state: "invalid" });
  assert.match(red, /class="v-status v-status--red" data-state="invalid"/);
  assert.match(red, /class="v-status__icon" aria-hidden="true">×</);
  assert.equal(textOf(red), "× Invalid");
  assert.equal(textOf(await renderTsx("app/ui/StatusWord.tsx", "StatusWord", { state: "partial_year", coveragePercent: 16.6 })), "! Partial year · 16.6%");
  assert.equal(textOf(await renderTsx("app/ui/StatusWord.tsx", "StatusWord", { state: "missing" })), "—");
});

test("Callout: four tones with roles, one next step; EmptyState says why and what next", async () => {
  const danger = await renderTsx("app/ui/Callout.tsx", "Callout", { tone: "danger", title: "Energy balance failed", children: "Treat results as unverified.", action: { label: "Open Inspect", href: "/inspect" } });
  assert.match(danger, /class="v-callout v-callout--danger" role="alert"/);
  assert.match(danger, /<a class="v-callout__action" href="\/inspect">Open Inspect<\/a>/);
  assert.match(await renderTsx("app/ui/Callout.tsx", "Callout", { tone: "attention", title: "t" }), /role="alert"/);
  assert.match(await renderTsx("app/ui/Callout.tsx", "Callout", { tone: "info", title: "t" }), /role="status"/);
  assert.match(await renderTsx("app/ui/Callout.tsx", "Callout", { tone: "success", title: "t", action: { label: "Next", onClick() {} } }), /role="status".*<button type="button" class="v-callout__action">Next<\/button>/);
  const empty = await renderTsx("app/ui/Callout.tsx", "EmptyState", { title: "No Runs yet", children: "Runs appear after you start one.", action: { label: "Open Studies", href: "/studies" } });
  assert.equal(textOf(empty), "No Runs yet Runs appear after you start one. Open Studies");
});

test("Fields have label, hint and error wired with aria; NumberField shows an empty box for null, never 0", async () => {
  const text = await renderTsx("app/ui/Field.tsx", "TextField", { label: "Study name", hint: "Letters and spaces", error: "Already used", value: "VALUE 101", onChange() {} });
  const id = /<label class="v-field__label" for="([^"]+)">/.exec(text)[1];
  const input = /<input [^>]*>/.exec(text)[0];
  for (const attribute of [`id="${id}"`, `class="v-input"`, `value="VALUE 101"`, `aria-describedby="${id}-hint ${id}-error"`, `aria-invalid="true"`]) assert.ok(input.includes(attribute), `${attribute} in ${input}`);
  assert.match(text, /<p class="v-field__error" id="[^"]+-error">Already used<\/p>/);
  const select = await renderTsx("app/ui/Field.tsx", "Select", { label: "Year", value: "2026", onChange() {}, options: [{ value: "2025", label: "2025" }, { value: "2026", label: "2026" }] });
  assert.match(select, /<select id="[^"]+" class="v-input v-select"/);
  assert.match(select, /<option value="2026" selected="">2026<\/option>/);
  const empty = await renderTsx("app/ui/Field.tsx", "NumberField", { label: "Discount", value: null, onChange() {}, min: 0, max: 1, unit: "fraction" });
  const box = /<input [^>]*>/.exec(empty)[0];
  for (const attribute of [`type="text"`, `inputMode="decimal"`, `value=""`]) assert.ok(box.includes(attribute), `${attribute} in ${box}`);
  assert.doesNotMatch(empty, /value="0"/);
  assert.match(empty, /<span class="v-number__unit">fraction<\/span>/);
  const outOfRange = await renderTsx("app/ui/Field.tsx", "NumberField", { label: "Discount", value: 3, onChange() {}, min: 0, max: 1 });
  assert.match(outOfRange, /value="3"/);
  assert.match(outOfRange, /aria-invalid="true"/);
  assert.match(outOfRange, /class="v-field__error"[^>]*>Must be at most 1</);
});

test("FileDrop opens from the keyboard (role=button, tabindex 0) and looks disabled when disabled", async () => {
  const html = await renderTsx("app/ui/FileDrop.tsx", "FileDrop", { label: "Demand CSV", hint: "UTF-8, half-hourly", accept: ".csv", onFiles() {} });
  assert.match(html, /class="v-filedrop__zone" role="button" tabindex="0"/);
  assert.match(html, /type="file" tabindex="-1" aria-hidden="true" accept=".csv"/);
  assert.match(textOf(html), /Choose a file or drop it here No file chosen/);
  const disabled = await renderTsx("app/ui/FileDrop.tsx", "FileDrop", { label: "Demand CSV", disabled: true, disabledReason: "Select a data pack first", onFiles() {} });
  assert.match(disabled, /class="v-filedrop is-disabled"/);
  assert.match(disabled, /tabindex="-1" aria-disabled="true"[^>]*title="Select a data pack first"/);
});

test("Hash shows 12 characters, the full value in the title and a copy button", async () => {
  const value = "sha256:0123456789abcdef0123456789abcdef";
  const html = await renderTsx("app/ui/Hash.tsx", "Hash", { value, label: "Study identity" });
  assert.match(html, new RegExp(`<code title="${value}" aria-label="Study identity: ${value}">sha256:0123456789ab…</code>`));
  assert.match(html, /<button type="button" class="v-hash__copy"[^>]*>Copy<\/button>/);
});

test("Metric shows value, unit and basis; a missing value shows the state word, never 0", async () => {
  const html = await renderTsx("app/ui/Metric.tsx", "Metric", { label: "Unused VRE", value: 1234.567, unit: "MWh", basis: "PSM boundary · 2025" });
  assert.equal(textOf(html), "Unused VRE 1,234.57 MWh PSM boundary · 2025");
  const missing = await renderTsx("app/ui/Metric.tsx", "Metric", { label: "Shortfall", value: null, unit: "MWh" });
  assert.equal(textOf(missing), "Shortfall ○ Not recorded");
  assert.doesNotMatch(textOf(missing), /\b0\b|MWh/);
  assert.equal(textOf(await renderTsx("app/ui/Metric.tsx", "Metric", { label: "x", value: Number.NaN, missingState: "not_modelled" })), "x ○ Not modelled");
  assert.equal(textOf(await renderTsx("app/ui/Metric.tsx", "Metric", { label: "Zero", value: 0, unit: "MWh" })), "Zero 0 MWh");
});

test("Dialog is a native dialog labelled by its title; Confirm states the consequence", async () => {
  const html = await renderTsx("app/ui/Dialog.tsx", "Confirm", { open: false, title: "Delete Run?", consequence: "The Run folder is removed from disk. This cannot be undone.", confirmLabel: "Delete Run", danger: true, onConfirm() {}, onCancel() {} });
  const id = /<dialog class="v-dialog" aria-labelledby="([^"]+)">/.exec(html)[1];
  assert.match(html, new RegExp(`<h2 id="${id}" class="v-dialog__title">Delete Run\\?</h2>`));
  assert.match(html, /<button type="button" class="v-dialog__close" aria-label="Close"/);
  assert.match(html, /<p class="v-dialog__consequence">The Run folder is removed from disk\. This cannot be undone\.<\/p>/);
  assert.match(html, /class="v-btn v-btn--danger v-btn--md"><span class="v-btn__label">Delete Run<\/span>/);
  assert.match(html, /class="v-btn v-btn--secondary v-btn--md v-dialog__cancel"><span class="v-btn__label">Cancel<\/span>/);
});

test("Toast: success is polite, failure is assertive with its own style and icon", async () => {
  const ok = await renderTsx("app/ui/Toast.tsx", "Toast", { tone: "success", children: "Study saved" });
  assert.match(ok, /class="v-toast v-toast--success" role="status" aria-live="polite"/);
  assert.match(ok, /class="v-toast__icon" aria-hidden="true">✓</);
  const error = await renderTsx("app/ui/Toast.tsx", "Toast", { tone: "error", children: "Save failed", onDismiss() {} });
  assert.match(error, /class="v-toast v-toast--error" role="alert" aria-live="assertive"/);
  assert.match(error, /class="v-toast__icon" aria-hidden="true">×</);
  assert.match(error, /aria-label="Dismiss"/);
});

test("Skeleton is a status with hidden text; Stepper marks the current step", async () => {
  const skeleton = await renderTsx("app/ui/Skeleton.tsx", "Skeleton", { lines: 2 });
  assert.match(skeleton, /role="status"/);
  assert.equal((skeleton.match(/v-skeleton__line/g) ?? []).length, 2);
  assert.equal(textOf(skeleton), "Loading");
  const stepper = await renderTsx("app/ui/Stepper.tsx", "Stepper", { steps: [{ id: "a", label: "Choose data", state: "done" }, { id: "b", label: "Run", state: "current" }, { id: "c", label: "Compare", state: "todo" }] });
  assert.match(stepper, /<nav class="v-stepper" aria-label="Steps">/);
  assert.match(stepper, /<li class="v-stepper__step is-current" aria-current="step">/);
  assert.equal((stepper.match(/aria-current/g) ?? []).length, 1);
  assert.equal(textOf(stepper), "✓ Choose data 2 Run 3 Compare");
});
