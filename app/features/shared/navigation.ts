export type View = "journey" | "learn" | "overview" | "data" | "models" | "projects" | "runCentre" | "run" | "marketReplay" | "curtailment" | "networkRedispatch" | "systems" | "audit" | "extend" | "compare";

/** One page: its index, and the dictionary keys of its label and note (P1 spec 3). */
export type NavView = { id: View; index: string; label: `nav.${View}.label`; note: `nav.${View}.note` };

const navView = (id: View, index: string): NavView => ({ id, index, label: `nav.${id}.label`, note: `nav.${id}.note` });

// P1 spec 5.1/5.2 (W3): every page has a route; the index is the page's place
// in the sidebar (the icon of the collapsed rail), the Run pages are numbered
// under Runs.  W4c (spec 5.1): "runCentre" is the Run centre (/runs) and
// "run" one Run's annual results (/runs/[runId]); both are numbered 08.
export const NAV_VIEWS: readonly NavView[] = [
  navView("overview", "01"),
  navView("learn", "02"),
  navView("journey", "03"),
  navView("projects", "04"),
  navView("data", "05"),
  navView("models", "06"),
  navView("extend", "07"),
  navView("runCentre", "08"),
  navView("run", "08"),
  navView("marketReplay", "08A"),
  navView("curtailment", "08B"),
  navView("networkRedispatch", "08C"),
  navView("systems", "08D"),
  navView("compare", "09"),
  navView("audit", "10"),
];

/** Spec 5.2: the sidebar's three groups. */
export const NAV_GROUPS: readonly { label: "nav.group.start" | "nav.group.work" | "nav.group.results"; ids: readonly View[] }[] = [
  { label: "nav.group.start", ids: ["overview", "learn", "journey"] },
  { label: "nav.group.work", ids: ["projects", "data", "models", "extend"] },
  { label: "nav.group.results", ids: ["runCentre", "compare", "audit"] },
];

/** The entries of the Run section bar (/runs/[runId]/*), in order. R3-16 (W4c): one
 * network entry; its page links to the DC network, expansion and water results (systems). */
export const RUN_SECTION_NAV: readonly View[] = ["run", "marketReplay", "curtailment", "networkRedispatch"];

/** Every page of one Run: the section bar's entries and the optional-domain results. */
export const RUN_PAGE_VIEWS: readonly View[] = [...RUN_SECTION_NAV, "systems"];

/** The Run section bar entry that is current on a Run page (systems belongs to the network entry). */
export function runSectionEntry(view: View): View {
  return view === "systems" ? "networkRedispatch" : view;
}

/** The sidebar entry that is current on a page: a Run page belongs to Runs (the Run centre). */
export function railView(view: View): View {
  return (RUN_PAGE_VIEWS as readonly View[]).includes(view) ? "runCentre" : view;
}

export function findNavView(id: View): NavView {
  return NAV_VIEWS.find((item) => item.id === id) ?? NAV_VIEWS[0];
}

/** R-3 (P1-polish): the sidebar group a page belongs to (a Run page belongs to Runs, in Results); the top bar's breadcrumb names it. */
export function navGroupLabel(view: View): (typeof NAV_GROUPS)[number]["label"] {
  const entry = railView(view);
  return (NAV_GROUPS.find((group) => group.ids.includes(entry)) ?? NAV_GROUPS[0]).label;
}
