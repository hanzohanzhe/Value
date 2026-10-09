"use client";

// Modules (/modules). P1 W4b (spec 6.4, R3-22): a one-line page header, a
// sticky in-page navigation (Catalog, Disabled & quarantined, Author a module),
// the catalogue first and the author tools last; app/ui components and the
// dictionaries (modules.*). The quarantine alert stays above everything.
import { useMemo } from "react";
import ModuleAuthorWorkbench from "../features/modules/ModuleAuthorWorkbench";
import { Badge, modelDisplayName } from "../features/shared/presentation";
import ModuleQuarantinePanel from "../features/modules/ModuleQuarantinePanel";
import DisabledEntriesPanel from "../features/modules/DisabledEntriesPanel";
import { disabledEntries, installedModuleCard, moduleUsageNote } from "../features/modules/disabledEntries.ts";
import { MODULES_PAGE_SECTIONS, catalogBadge } from "../features/modules/modulesPage.ts";
import SectionNav from "../features/shared/SectionNav";
import { Button, EmptyState, FileDrop, PageHeader } from "../ui";
import { useT } from "../i18n/LocaleProvider";
import { useWorkbench } from "../features/shell/Workbench";

const BUILD_COMMAND = "py -3.10 scripts\\build_module_bundle.py --manifest value-module.json --source-root src --license LICENSE --output my-module.zip";
const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ block: "start", behavior: "smooth" });

export default function ModulesView() {
  const t = useT();
  const { setView, workspace, setSelectedProjectId, setSelectedRunId, moduleBundle, setModuleBundle, bundleInputGeneration, moduleTrust, setModuleTrust, moduleInstalling, moduleLifecycle, setPreflight, setNotice, refresh, quarantineBusy, entryErrors, disableQuarantined, rescanModules, enableEntry, removeEntry, installModule, changeModuleState } = useWorkbench();
  const entries = disabledEntries({ modules: workspace.module_installations, extensions: workspace.extension_installations, quarantine: workspace.module_quarantine });
  const modules = workspace.modules.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const sections = useMemo(() => MODULES_PAGE_SECTIONS.map((section) => ({
    id: section.id, label: t(section.label),
    count: section.id === "modules-catalog" ? workspace.modules.length : section.id === "modules-disabled" ? entries.length : undefined,
  })), [t, workspace.modules.length, entries.length]);
  const installReason = !moduleBundle ? t("modules.installer.needFile") : !moduleTrust ? t("modules.installer.needTrust") : undefined;
  return <div className="page modules-page">
    <PageHeader headingLevel={2} title={t("modules.page.title")} description={t("modules.page.description")} actions={<>
      <Badge tone="good">{catalogBadge(workspace.modules, t)}</Badge>
      <Button size="sm" className="modules-rescan value-new-control" disabled={Boolean(quarantineBusy)} loading={quarantineBusy === "rescan"} onClick={() => void rescanModules()}>{quarantineBusy === "rescan" ? t("modules.action.rescanning") : t("modules.page.rescan")}</Button>
    </>} />
    <ModuleQuarantinePanel report={workspace.module_quarantine} busy={quarantineBusy} onDisable={(row) => void disableQuarantined(row)} onRescan={() => void rescanModules()} />
    <SectionNav label={t("modules.nav.label")} sections={sections} />

    <section className="page-section" id="modules-catalog" aria-labelledby="modules-catalog-title">
      <header className="page-section-head"><div><span>{t("modules.catalog.eyebrow")}</span><h3 id="modules-catalog-title">{t("modules.catalog.title")}</h3></div></header>
      {workspace.module_installations.length > 0 && <section className="installed-modules" aria-labelledby="installed-modules-title">
        <header><div><span>{t("modules.installed.eyebrow")}</span><h3 id="installed-modules-title">{t("modules.installed.title")}</h3></div><Badge>{workspace.module_installations.length}</Badge></header>
        <div>{workspace.module_installations.map((installation) => {
          const projectReferences = workspace.projects.filter((project) => Object.values(project.modules).includes(installation.module_id));
          const card = installedModuleCard(installation, workspace.module_quarantine, workspace.module_source_changes, t);
          const usage = moduleUsageNote(card.state, projectReferences.length, t);
          const usedBy = projectReferences.length ? t("modules.installed.usedBy", { names: projectReferences.map((project) => project.name).join(", ") }) : undefined;
          return <article key={installation.module_id} data-state={card.state}>
            <div><b>{installation.name}</b><small>{installation.module_id} · {installation.slot.replaceAll("_", " ")} · {installation.module_version}</small></div>
            <span><small>{t("modules.installed.contract")}</small><code>{installation.contract_version}</code></span>
            <span><small>{t("modules.installed.sourceSha")}</small><code title={installation.source_sha256 ?? undefined}>{installation.source_sha256 ? `${installation.source_sha256.slice(0, 16)}…` : t("modules.installed.notRecorded")}</code>{card.sourceChange && <em className="installed-module-note caution value-new-control">{card.sourceChange}</em>}</span>
            <span><small>{t("modules.installed.conformance")}</small><b>{installation.conformance.status}</b></span>
            <span><small>{t("modules.installed.state")}</small><b className={`installed-module-state ${card.state} value-new-control`}>{card.stateText}</b></span>
            {card.offerToggle
              ? <Button size="sm" variant="ghost" disabled={moduleLifecycle === installation.module_id || (installation.enabled && projectReferences.length > 0)} disabledReason={usedBy} title={usedBy} loading={moduleLifecycle === installation.module_id} onClick={() => void changeModuleState(installation, !installation.enabled)}>{moduleLifecycle === installation.module_id ? t("modules.installed.updating") : t("modules.action.disable")}</Button>
              : <Button size="sm" variant="ghost" onClick={() => scrollTo("modules-disabled")}>{t("modules.installed.openDisabled")}</Button>}
            {usage && <p>{usage}</p>}
          </article>;
        })}</div>
      </section>}
      {modules.length ? <div className="module-list">{modules.map((module, index) => <article className="module-card" key={module.id}>
        <header><div className={`module-mark ${module.kind}`} aria-hidden="true">{String(index + 1).padStart(2, "0")}</div><div><span>{module.kind.toUpperCase()} · {module.slot.replaceAll("_", " ")} · {module.version}</span><h3>{modelDisplayName(module.name)}</h3></div><Badge tone={module.status === "ready" ? "good" : "warn"}>{module.origin === "local_bundle" ? t("modules.card.local", { status: module.status }) : module.status}</Badge></header>
        <p>{modelDisplayName(module.description)}</p>
        <div className="module-id"><span>{t("modules.card.implementation")}</span><code>{module.id}</code><small>{t("modules.card.contract", { version: module.contract_version ?? t("modules.card.contractNotRecorded") })}</small></div>
        {module.id === "value-bid-at-cost-psm" && <div className="compatibility-note">{t("modules.card.liveNote")}</div>}
        <details className="io"><summary>{t("modules.card.io")}</summary><div><span>{t("modules.card.inputs")}</span>{module.inputs.map((input) => <code key={input}>{input}</code>)}</div><i aria-hidden="true">→</i><div><span>{t("modules.card.outputs")}</span>{module.outputs.map((output) => <code key={output}>{output}</code>)}</div></details>
      </article>)}</div> : <EmptyState title={t("modules.catalog.empty")} />}
    </section>

    <section className="page-section" id="modules-disabled" aria-label={t("modules.nav.disabled")}>
      {entries.length
        ? <DisabledEntriesPanel entries={entries} busy={quarantineBusy} errors={entryErrors} onEnable={(entry) => void enableEntry(entry)} onRescan={() => void rescanModules()} onRemove={(entry) => void removeEntry(entry)} />
        : <><header className="page-section-head"><div><span>{t("modules.disabled.eyebrow")}</span><h3 id="disabled-entries-title">{t("modules.disabled.title")}</h3></div></header><EmptyState title={t("modules.disabled.none")} /></>}
    </section>

    <section className="page-section" id="modules-author" aria-labelledby="modules-author-title">
      <header className="page-section-head"><div><span>{t("modules.author.eyebrow")}</span><h3 id="modules-author-title">{t("modules.author.title")}</h3></div><p>{t("modules.author.description")}</p></header>
      <ModuleAuthorWorkbench modules={workspace.modules} projects={workspace.projects}
        onInstallRequest={() => scrollTo("module-installer")}
        onCreated={async ({ id, notes }) => {
          const refreshed = await refresh();
          setSelectedProjectId(id); setSelectedRunId(""); setPreflight(null); setView("run");
          const extra = notes?.length ? ` ${notes.join(" ")}` : "";
          setNotice((refreshed ? t("modules.notice.methodStudySaved") : t("modules.notice.methodStudySavedOffline")) + extra);
        }} />
      <section className="panel module-installer" id="module-installer" aria-labelledby="module-installer-title">
        <div className="module-installer-copy"><span>{t("modules.installer.eyebrow")}</span><h3 id="module-installer-title">{t("modules.installer.title")}</h3><p>{t("modules.installer.body")}</p><small>{t("modules.installer.caution")}</small></div>
        <div className="module-installer-form">
          <FileDrop key={`module-bundle-${bundleInputGeneration}`} className="module-file" label={t("modules.installer.file")} accept=".zip,application/zip" disabled={moduleInstalling} prompt={t("modules.installer.choose")} onFiles={(files) => setModuleBundle(files[0] ?? null)} />
          <label className="trust-check"><input type="checkbox" checked={moduleTrust} onChange={(event) => setModuleTrust(event.target.checked)} /><span>{t("modules.installer.trust")}</span></label>
          <Button variant="primary" disabled={!moduleBundle || !moduleTrust} disabledReason={installReason} loading={moduleInstalling} onClick={() => void installModule()}>{moduleInstalling ? t("modules.installer.installing") : t("modules.installer.install")}</Button>
          <details><summary>{t("modules.installer.developers")}</summary><code>{BUILD_COMMAND}</code></details>
        </div>
      </section>
    </section>
  </div>;
}
