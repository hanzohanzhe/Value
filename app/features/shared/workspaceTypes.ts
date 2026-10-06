import type { Module, ModuleSlot, Extension, Slot, DataPack, ModuleInstallation, ExtensionInstallation, Project, StudyTrashEntry } from "../studies/types";
import type { ModelRun, RecoveryCapability } from "../runs/types";
import type { QuarantineReport } from "../modules/ModuleQuarantinePanel";

export type RuntimeCapability = {
  capability: string; available: boolean; python: string; supported_python: string[];
  missing_imports: string[]; corrective_action?: string | null;
};
export type Workspace = {
  architecture_version: string; frontend_contract_version?: string; modules: Module[]; module_slots: ModuleSlot[];
  extensions: Extension[]; dataset_slots: Slot[]; data_packs: DataPack[];
  module_installations: ModuleInstallation[]; extension_installations: ExtensionInstallation[]; projects: Project[]; study_trash: StudyTrashEntry[]; runs: ModelRun[];
  /** P0-2: quarantined external modules/extensions and damaged install records. */
  module_quarantine?: QuarantineReport;
  /** M-D2 (round R1-5): installed modules whose source was edited in place since install. */
  module_source_changes?: { module_id: string; installed_sha256: string; current_sha256: string }[];
  runtime: {
    python: string; compatible: boolean; selected_capability?: string;
    capabilities?: Record<string, RuntimeCapability>;
    recovery?: RecoveryCapability;
  };
};
