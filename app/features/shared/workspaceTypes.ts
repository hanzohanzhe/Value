import type { Module, ModuleSlot, Extension, Slot, DataPack, ModuleInstallation, ExtensionInstallation, Project, StudyTrashEntry } from "../studies/types";
import type { ModelRun, RecoveryCapability } from "../runs/types";

export type RuntimeCapability = {
  capability: string; available: boolean; python: string; supported_python: string[];
  missing_imports: string[]; corrective_action?: string | null;
};
export type Workspace = {
  architecture_version: string; frontend_contract_version?: string; modules: Module[]; module_slots: ModuleSlot[];
  extensions: Extension[]; dataset_slots: Slot[]; data_packs: DataPack[];
  module_installations: ModuleInstallation[]; extension_installations: ExtensionInstallation[]; projects: Project[]; study_trash: StudyTrashEntry[]; runs: ModelRun[]; runtime: {
    python: string; compatible: boolean; selected_capability?: string;
    capabilities?: Record<string, RuntimeCapability>;
    recovery?: RecoveryCapability;
  };
};
