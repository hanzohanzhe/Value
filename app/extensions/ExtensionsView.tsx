"use client";

// Extensions (/extensions). P1 W4b (spec 6.4): a one-line page header, a
// sticky in-page navigation (Catalogue, Install, Author an extension), the
// catalogue first and the author workbench last; app/ui components and the
// dictionaries (extensions.*). The data adapter guide moved to /data (D-W3-5).
import { useMemo } from "react";
import ExtensionAuthorWorkbench from "../features/extensions/ExtensionAuthorWorkbench";
import { uniqueStudyName } from "../features/studies/draftName.ts";
import { Badge } from "../features/shared/presentation";
import { extensionSourceChangeNote } from "../features/modules/disabledEntries.ts";
import { EXTENSIONS_PAGE_SECTIONS } from "../features/modules/modulesPage.ts";
import SectionNav from "../features/shared/SectionNav";
import { Button, EmptyState, FileDrop, Hash, PageHeader } from "../ui";
import { useT } from "../i18n/LocaleProvider";
import { useWorkbench } from "../features/shell/Workbench";

const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ block: "start", behavior: "smooth" });

export default function ExtensionsView() {
  const t = useT();
  const { setView, workspace, bundleInputGeneration, extensionBundle, setExtensionBundle, extensionTrust, setExtensionTrust, extensionInstalling, extensionLifecycle, setPreflight, setNotice, setDataContextId, setEditingBaseRevision, setEditingProjectId, setProjectForm, selectedProject, loadStudyIntoForm, installExtension, changeExtensionState } = useWorkbench();
  const sections = useMemo(() => EXTENSIONS_PAGE_SECTIONS.map((section) => ({
    id: section.id, label: t(section.label), count: section.id === "extensions-catalogue" ? workspace.extensions.length : undefined,
  })), [t, workspace.extensions.length]);
  const installReason = !extensionBundle ? t("extensions.installer.needFile") : !extensionTrust ? t("extensions.installer.needTrust") : undefined;
  return <div className="page extensions-page">
    <PageHeader headingLevel={2} title={t("extensions.page.title")} description={t("extensions.page.description")} />
    <SectionNav label={t("extensions.nav.label")} sections={sections} />

    <section className="page-section extension-catalogue" id="extensions-catalogue" aria-labelledby="extensions-catalogue-title">
      <header><div><span>{t("extensions.catalogue.eyebrow")}</span><h3 id="extensions-catalogue-title">{t("extensions.catalogue.title")}</h3></div><Badge>{workspace.extensions.length}</Badge></header>
      {workspace.extensions.length ? <div>{workspace.extensions.map((extension) => {
        const installation = workspace.extension_installations.find((item) => item.extension_id === extension.id && item.version === extension.version);
        const projectReferences = workspace.projects.filter((project) => project.selected_extensions?.includes(extension.id));
        const sourceNote = installation ? extensionSourceChangeNote(extension.id, workspace.extension_source_changes, t) : null;
        const usedBy = projectReferences.length ? t("extensions.catalogue.usedBy", { names: projectReferences.map((project) => project.name).join(", ") }) : undefined;
        const required = extension.data_roles.filter((role) => role.required).length;
        return <article key={extension.id}>
          <header><div><b>{extension.name}</b><small>{extension.id} · {extension.version} · {extension.namespace}</small></div><Badge tone={extension.maturity === "ready" ? "good" : "warn"}>{extension.maturity.replaceAll("_", " ")}</Badge></header>
          <p><strong>{t("extensions.catalogue.provides")}</strong> {extension.provided_capabilities.join(" · ") || t("extensions.catalogue.noCapability")}</p>
          <p><strong>{t("extensions.catalogue.requires")}</strong> {extension.required_capabilities.join(" · ") || t("extensions.catalogue.noAdditional")}</p>
          <div>
            <span><small>{t("extensions.catalogue.conditionalData")}</small><b>{t("extensions.catalogue.roles", { required, optional: extension.data_roles.length - required })}</b></span>
            <span><small>{t("extensions.catalogue.composed")}</small><b>{extension.composed_module_ids.join(", ") || t("extensions.catalogue.none")}</b></span>
            <span><small>{t("extensions.catalogue.licence")}</small><b>{extension.licence} · <Hash value={extension.manifest_sha256} /></b></span>
            <span><small>{t("extensions.catalogue.origin")}</small><b>{extension.origin.replaceAll("_", " ")} · {extension.enabled ? t("extensions.catalogue.enabled") : t("extensions.catalogue.disabled")}</b></span>
          </div>
          {sourceNote && <em className="installed-module-note caution value-new-control">{sourceNote}</em>}
          {installation && <footer>
            <details className="extension-boundary"><summary>{t("extensions.catalogue.boundary")}</summary><code>{installation.installation_boundary}</code></details>
            <Hash value={installation.bundle_sha256} />
            <Button size="sm" variant="ghost" disabled={extensionLifecycle === extension.id || (installation.enabled && projectReferences.length > 0)} disabledReason={usedBy} title={usedBy} loading={extensionLifecycle === extension.id} onClick={() => void changeExtensionState(installation, !installation.enabled)}>{extensionLifecycle === extension.id ? t("extensions.catalogue.updating") : installation.enabled ? t("extensions.catalogue.disable") : t("extensions.catalogue.enable")}</Button>
          </footer>}
          {projectReferences.length > 0 && <em>{t("extensions.catalogue.referenced", { count: projectReferences.length })}</em>}
        </article>;
      })}</div> : <EmptyState title={t("extensions.catalogue.empty")} />}
    </section>

    <section className="page-section" id="extensions-install" aria-labelledby="extension-installer-title">
      <section className="panel extension-installer" id="extension-installer">
        <div className="module-installer-copy"><span>{t("extensions.installer.eyebrow")}</span><h3 id="extension-installer-title">{t("extensions.installer.title")}</h3><p>{t("extensions.installer.body")}</p><small>{t("extensions.installer.levels")}</small></div>
        <div className="module-installer-form">
          <FileDrop key={`extension-bundle-${bundleInputGeneration}`} className="module-file" label={t("extensions.installer.file")} accept=".zip,application/zip" disabled={extensionInstalling} prompt={t("extensions.installer.choose")} onFiles={(files) => setExtensionBundle(files[0] ?? null)} />
          <label className="trust-check"><input type="checkbox" checked={extensionTrust} onChange={(event) => setExtensionTrust(event.target.checked)} /><span>{t("extensions.installer.trust")}</span></label>
          <Button variant="primary" disabled={!extensionBundle || !extensionTrust} disabledReason={installReason} loading={extensionInstalling} onClick={() => void installExtension()}>{extensionInstalling ? t("extensions.installer.installing") : t("extensions.installer.install")}</Button>
        </div>
      </section>
    </section>

    <section className="page-section" id="extensions-author" aria-label={t("extensions.nav.author")}>
      <ExtensionAuthorWorkbench extensions={workspace.extensions} modules={workspace.modules}
        onInstallRequest={() => scrollTo("extension-installer")}
        onOpenStudies={() => {
          // R4 F-中4: the draft copies the selected saved Study (years, modules,
          // parameters, run options), so adding the extension is the only change.
          const base = selectedProject && !selectedProject.extensions?.frozen_recovery ? selectedProject : undefined;
          setEditingProjectId(undefined); setEditingBaseRevision(undefined); setDataContextId("draft");
          // R5 F-中2: a second draft from the same baseline gets "… 2", so its
          // derived Study ID does not collide with the first draft's Study.
          if (base) loadStudyIntoForm(base, uniqueStudyName(`${base.name} · extension study`, workspace.projects));
          else setProjectForm(current => ({ ...current, name: uniqueStudyName(`${current.name || "New"} · extension study`, workspace.projects), maturity_acknowledgements: {} }));
          setPreflight(null); setView("projects");
          setNotice(base
            ? t("extensions.notice.draftFromStudy", { name: base.name, revision: base.revision_number ?? 0 })
            : t("extensions.notice.draftFromEditor"));
        }} />
    </section>
  </div>;
}
