export type Value101StudyDraft = {
  schema_version: string;
  id: string;
  name: string;
  data_pack_id: string;
  start_year: number;
  end_year: number;
  purpose: string;
  modules: Record<string, string>;
  selected_extensions: string[];
  extension_parameters: Record<string, unknown>;
  maturity_acknowledgements: Record<string, string>;
  parameters: Record<string, unknown>;
  runtime_options: Record<string, unknown>;
  extensions?: Record<string, unknown>;
  revision_number?: number;
  revision_sha256?: string;
};

export type Value101NetworkPairIdentity = {
  schema_version: string;
  ahead_inputs_identical: boolean;
  ahead_schedule_comparison: string;
  only_network_delivery_changed: boolean;
  controlled_dimensions: string[];
  changed_scientific_paths: string[];
  same_national_demand_authority: boolean;
  network_method: string;
};

export type Value101NetworkPair = {
  schema_version: string;
  identity: Value101NetworkPairIdentity;
  studies: {
    copperplate: Value101StudyDraft;
    constrained: Value101StudyDraft;
  };
  run_started: false;
};

export type Value101Concept = {
  id: string;
  label: string;
  plain_language: string;
};

export type Value101ModuleIdentity = {
  id: string;
  name: string;
  slot: string;
  version: string;
  contract_version?: string;
  description?: string;
  implementation?: string;
  inputs: string[];
  outputs: string[];
  order?: number;
};

export type Value101TutorialDescriptor = {
  schema_version: string;
  id: string;
  name: string;
  summary: string;
  run_modes: { one_day: "value_101_day"; complete_two_year: "two_year" };
  study: Value101StudyDraft;
  pack_ids: string[];
  concepts: Value101Concept[];
  availability: {
    packs: { pack_id: string; installed: boolean }[];
    all_packs_installed: boolean;
    corrective_action: string | null;
    optional_network_pack?: {
      pack_id: string;
      installed: boolean;
      required_for_core_course: false;
    };
  };
  scientific_boundary: {
    label: string;
    country: "SYNTHETIC";
    timezone: "UTC";
    teaching_only: boolean;
    period_hours: number;
    one_day_periods: number;
    periods_per_year: number;
    years: number;
    annual_economics_eligible: boolean;
    scientific_baseline_eligible: boolean;
    excluded_claims: string[];
  };
};

export type Value101StepId =
  | "building-blocks"
  | "baseline"
  | "market-day"
  | "market-evidence"
  | "annual-run"
  | "annual-evidence"
  | "research-model"
  | "network";

export type LearnTarget = "data" | "models" | "projects" | "run" | "marketReplay" | "curtailment" | "networkRedispatch" | "audit" | "extend";

export const VALUE_101_FALLBACK: Value101TutorialDescriptor = {
  schema_version: "value.tutorial/v1",
  id: "value-101",
  name: "VALUE 101 — a synthetic annual teaching system",
  summary: "Learn one market day, then run the complete two-year VALUE PSM-CEM chain.",
  run_modes: { one_day: "value_101_day", complete_two_year: "two_year" },
  study: {
    schema_version: "value.project/v1",
    id: "value-101-baseline",
    name: "VALUE 101 baseline",
    data_pack_id: "value-101-baseline-v1",
    start_year: 2025,
    end_year: 2026,
    purpose: "VALUE 101 synthetic annual teaching model",
    modules: {
      psm: "value-bid-at-cost-psm",
      storage_cost: "dynamic-annual-storage-cost",
      investment: "agent-investment",
      pipeline: "planning-pipeline",
      vre_cap: "vre-expansion-cap",
      storage_cap: "value-storage-expansion-policy",
      transition: "value-annual-state-transition",
    },
    selected_extensions: [],
    extension_parameters: {},
    maturity_acknowledgements: {},
    parameters: { "planning.defer_spread_years": 0 },
    runtime_options: {
      "runtime.market_trace_level": "summary",
      "runtime.checkpoint_enabled": true,
    },
  },
  concepts: [
    { id: "data", label: "Data", plain_language: "Demand, weather, assets, costs and planning records supplied to a Study." },
    { id: "modules", label: "Modules", plain_language: "Replaceable implementations of clearing, storage pricing, investment, planning and transition." },
    { id: "study", label: "Study", plain_language: "A saved combination of years, one data pack and selected model modules." },
    { id: "run", label: "Run", plain_language: "An immutable execution of one saved Study revision." },
    { id: "evidence", label: "Results", plain_language: "Dispatch, bids, storage, unused VRE, cost, carbon and planning artifacts written by the model." },
  ],
  pack_ids: ["value-101-baseline-v1"],
  availability: {
    packs: [
      { pack_id: "value-101-baseline-v1", installed: false },
    ],
    all_packs_installed: false,
    corrective_action: "Waiting for the local model service to confirm the bundled VALUE 101 packs.",
    optional_network_pack: {
      pack_id: "value-101-network-v1",
      installed: false,
      required_for_core_course: false,
    },
  },
  scientific_boundary: {
    label: "Synthetic annual model: not evidence about Great Britain",
    country: "SYNTHETIC",
    timezone: "UTC",
    teaching_only: true,
    period_hours: 0.5,
    one_day_periods: 48,
    periods_per_year: 17_520,
    years: 2,
    annual_economics_eligible: true,
    scientific_baseline_eligible: false,
    excluded_claims: [
      "Great Britain annual system cost",
      "national capacity pathway",
      "real network or hydrology result",
    ],
  },
};

export const VALUE_101_PROGRESS_KEY = "value.101.progress.v1";
