"""Authoritative scientific/runtime parameter registry for VALUE v2."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from .errors import ParameterError
from .errors import warning_event
from .builtin.scheme_c_1000twh.runtime_compat.storage_cost import compile_storage_formula
from .cost_ledger import CEM_SYSTEM_COST_DEFINITION
from .methodology import PROFILE_PARAMETER, default_profile_id, profile_ids


class ParameterValidationError(ParameterError, ValueError):
    pass


@dataclass(frozen=True)
class ParameterDefinition:
    id: str
    group: str
    value_type: str
    default: object
    category: str
    visibility: str
    scientific_effect: str
    module_owner: str
    unit: str | None = None
    allowed_values: tuple[object, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    data_pack_role: str | None = None
    data_pack_path: str | None = None
    experimental: bool = False

    @property
    def source_precedence(self) -> tuple[str, ...]:
        if self.category == "fixed":
            return ("module_fixed",)
        if self.category == "runtime":
            return ("runtime_default", "run_option")
        values = ["module_default"]
        if self.data_pack_role:
            values.append("data_pack")
        values.append("project_override")
        return tuple(values)

    def api_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["source_precedence"] = list(self.source_precedence)
        return value


PARAMETERS: tuple[ParameterDefinition, ...] = (
    # Fixed assumptions define this VALUE PSM version.
    ParameterDefinition("model.topology", "Model card", "enum", "single_gb_node", "fixed", "fixed", "No internal GB transmission constraints.", "value-bid-at-cost-psm", allowed_values=("single_gb_node",)),
    ParameterDefinition("model.interconnectors", "Model card", "enum", "boundary_import_offers", "fixed", "fixed", "External imports bid at the GB market boundary; they are not internal lines.", "value-bid-at-cost-psm", allowed_values=("boundary_import_offers",)),
    ParameterDefinition("clock.period_hours", "Model card", "float", 0.5, "fixed", "fixed", "Physical duration represented by a normal dispatch period.", "value-bid-at-cost-psm", unit="hours", minimum=0.5, maximum=0.5),
    ParameterDefinition("clock.full_year_periods", "Model card", "integer", 17_520, "fixed", "fixed", "Half-hour periods in a full model year.", "value-bid-at-cost-psm", unit="periods/year", minimum=17_520, maximum=17_520),
    ParameterDefinition("market.dispatch_formulation", "Model card", "enum", "bid_at_cost_continuous_no_commitment", "fixed", "fixed", "Continuous bid-at-cost dispatch without commitment, ramp or minimum-output constraints.", "value-bid-at-cost-psm", allowed_values=("bid_at_cost_continuous_no_commitment",)),
    ParameterDefinition("storage.virtual_pool_energy_mwh", "Model card", "float", 1_000_000_000.0, "fixed", "fixed", "Non-binding diagnostic virtual storage-pool energy sentinel.", "value-storage-expansion-policy", unit="MWh", minimum=1_000_000_000.0, maximum=1_000_000_000.0),
    ParameterDefinition("storage.virtual_pool_power_mw", "Model card", "float", 1_000_000_000.0, "fixed", "fixed", "Non-binding diagnostic virtual storage-pool power sentinel.", "value-storage-expansion-policy", unit="MW", minimum=1_000_000_000.0, maximum=1_000_000_000.0),
    ParameterDefinition("runtime.python_minor", "Model card", "enum", "3.10", "fixed", "fixed", "Only Python minor currently backed by VALUE native numerical evidence; retained VALUE reference comparison is a separate 3.10 capability.", "value-bid-at-cost-psm", allowed_values=("3.10",)),
    ParameterDefinition("cost.system_boundary", "Model card", "enum", CEM_SYSTEM_COST_DEFINITION, "fixed", "fixed", "VALUE CEM physical resource cost: annualised active-fleet CAPEX/FOM plus physical operation, storage degradation and reliability cost, divided by demand served for the headline intensity.", "value-cost-ledger", allowed_values=(CEM_SYSTEM_COST_DEFINITION,)),
    ParameterDefinition("fleet.repd_initial_snapshot", "Model card", "boolean", True, "fixed", "fixed", "Refreshes initial VRE and battery stock from the REPD operating snapshot.", "value-canonical-planning-input-v1"),
    ParameterDefinition("planning.uncertain_as_model_decision", "Model card", "boolean", False, "fixed", "fixed", "Uncertain REPD projects remain external projects in retained VALUE.", "value-canonical-planning-input-v1"),
    ParameterDefinition("expansion.storage_cap_method", "Model card", "enum", "value_simulation_trace", "fixed", "fixed", "VALUE storage-headroom calculation.", "value-storage-expansion-policy", allowed_values=("value_simulation_trace",)),

    # The methodology profile (X0 S8). Default and allowed values come only
    # from gridform_core/data/methodology/profiles.json (one source of truth).
    ParameterDefinition(PROFILE_PARAMETER, "Methodology", "enum", default_profile_id(), "scientific", "basic", "Methodology profile: the corrected default, or the frozen doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2, with declared deviations). Part of the run's method identity, not of its configuration.", "application", allowed_values=profile_ids()),

    # Editable scientific settings. Current production defaults are preserved.
    ParameterDefinition("planning.success_mode", "Planning", "enum", "expected", "scientific", "advanced", "Expected-capacity or seeded stochastic planning success. Legacy expected/stochastic values remain accepted aliases.", "planning-pipeline", allowed_values=("expected", "stochastic", "expected_capacity", "seeded_stochastic")),
    ParameterDefinition("planning.random_seed", "Planning", "integer", 0, "scientific", "advanced", "Seed namespace for stochastic planning success draws.", "planning-pipeline", minimum=0, maximum=2_147_483_647),
    ParameterDefinition("planning.include_uncertain_projects", "Planning", "boolean", True, "scientific", "advanced", "Includes REPD statuses with uncertain timelines.", "value-canonical-planning-input-v1"),
    ParameterDefinition("planning.zombie_filter_enabled", "Planning", "boolean", True, "scientific", "advanced", "Removes terminal, stagnant and schedule-overdue REPD projects.", "value-canonical-planning-input-v1", data_pack_role="config.model_parameters", data_pack_path="repd_filtering.apply_zombie_filter"),
    ParameterDefinition("planning.zombie_status_stale_year", "Planning", "integer", 2015, "scientific", "advanced", "Latest acceptable year of recorded REPD status progress.", "value-canonical-planning-input-v1", unit="year", minimum=1990, maximum=2100, data_pack_role="config.model_parameters", data_pack_path="repd_filtering.zombie_status_stale_year"),
    ParameterDefinition("planning.construction_grace_years", "Planning", "integer", 2, "scientific", "advanced", "Grace after median construction timing before schedule-zombie exclusion.", "value-canonical-planning-input-v1", unit="years", minimum=0, maximum=20),
    ParameterDefinition("planning.minimum_project_size_mw", "Planning", "float", 1.0, "scientific", "advanced", "Smallest REPD project eligible for the pipeline.", "value-canonical-planning-input-v1", unit="MW", minimum=0.0, maximum=10_000.0, data_pack_role="config.model_parameters", data_pack_path="repd_filtering.minimum_project_size_mw"),
    ParameterDefinition("planning.max_completion_year", "Planning", "integer", 2040, "scientific", "advanced", "Latest project completion year admitted from REPD.", "value-canonical-planning-input-v1", unit="year", minimum=2025, maximum=2200, data_pack_role="config.model_parameters", data_pack_path="repd_filtering.max_completion_year"),
    ParameterDefinition("planning.timeline_statistic", "Planning", "enum", "median", "scientific", "advanced", "Selects the supported mean or median planning timeline statistic.", "value-canonical-planning-input-v1", allowed_values=("median", "mean")),
    ParameterDefinition("planning.defer_spread_years", "Planning", "integer", 3, "scientific", "advanced", "Deterministic spread applied when start-year stock is deferred.", "value-canonical-planning-input-v1", unit="years", minimum=0, maximum=20),
    ParameterDefinition("planning.repd_battery_assignment", "Planning", "enum", "value_proportional_split", "scientific", "advanced", "Assigns generic REPD Battery MW to fixed-duration storage technologies when the source has no project-level duration.", "value-canonical-planning-input-v1", allowed_values=("value_proportional_split", "all_1c", "all_0.5c", "all_0.25c", "exclude_untyped")),
    ParameterDefinition("expansion.vre_cap_fraction", "Expansion", "float", 0.20, "scientific", "advanced", "Fraction of calculated VRE headroom available to annual expansion.", "vre-expansion-cap", unit="fraction", minimum=0.0, maximum=1.0),
    ParameterDefinition("expansion.storage_cap_fraction", "Expansion", "float", 0.20, "scientific", "advanced", "Fraction used by the selected storage expansion-cap calculation.", "value-storage-expansion-policy", unit="fraction", minimum=0.0, maximum=1.0, data_pack_role="config.model_parameters", data_pack_path="storage_cap_fraction"),
    ParameterDefinition("expansion.storage_credit_method", "Expansion", "enum", "value_capacity_credit", "scientific", "advanced", "Supported capacity-credit treatment for storage expansion.", "value-storage-expansion-policy", allowed_values=("value_capacity_credit",)),
    ParameterDefinition("network.expansion.annual_budget_gbp", "Network expansion", "float", 0.0, "scientific", "advanced", "Shared annual system CAPEX budget for the optional transmission expansion module; zero disables endogenous proposals.", "reference-transmission-expansion", unit="GBP/year", minimum=0.0, maximum=1.0e13, experimental=True),
    ParameterDefinition("network.expansion.group_budget_gbp", "Network expansion", "float", 1.0e13, "scientific", "advanced", "Shared annual CAPEX budget applied once to each declared candidate budget group.", "reference-transmission-expansion", unit="GBP/year", minimum=0.0, maximum=1.0e13, experimental=True),
    ParameterDefinition("network.expansion.random_seed", "Network expansion", "integer", 0, "scientific", "advanced", "Seed namespace for physical transmission-project planning success; circuits are never probability-weighted fractions.", "reference-transmission-expansion", minimum=0, maximum=2_147_483_647, experimental=True),
    ParameterDefinition("scenario.id", "Scenario", "enum", "existing_decarb_base", "scientific", "basic", "Selects the VALUE policy/decarbonisation scenario.", "value-annual-state-transition", allowed_values=("existing_decarb_base", "subsidy_as_usual", "government_target")),
    ParameterDefinition("market.bid_multiplier", "Market experiment", "float", 1.0, "scientific", "advanced", "Experimental multiplier on cost-based offers; values other than one are not strict bid-at-cost.", "value-bid-at-cost-psm", unit="multiplier", minimum=0.01, maximum=10.0, data_pack_role="config.model_parameters", data_pack_path="simulation_parameters.bidding_factor", experimental=True),
    ParameterDefinition("market.dec_multiplier", "Market experiment", "float", 1.0, "scientific", "advanced", "Multiplier on the avoided running cost that a fuel unit or import returns when it is decremented in staged balancing; must not exceed market.bid_multiplier.", "value-staged-bid-at-cost-psm", unit="multiplier", minimum=0.0, maximum=10.0, experimental=True),
    ParameterDefinition("market.policy_support_gbp_per_mwh_by_technology", "Market experiment", "string", "{}", "scientific", "advanced", "JSON object {technology: GBP/MWh} of output-based support a decremented asset loses (CfD strike minus reference, ROC value); technologies not listed are merchant (0).", "value-staged-bid-at-cost-psm", unit="GBP/MWh", experimental=True),
    ParameterDefinition("network.inflexible_dec_premium_gbp_per_mwh_by_technology", "Market experiment", "string", '{"nuclear":100.0}', "scientific", "advanced", "JSON object {technology: GBP/MWh} of the extra price an inflexible unit asks to be decremented; nuclear uses the shared down-regulation table value by default.", "value-staged-bid-at-cost-psm", unit="GBP/MWh", experimental=True),
    ParameterDefinition("market.perfect_foresight_terminal_soc_rule", "Market experiment", "enum", "cyclic", "scientific", "advanced", "Terminal storage state for the optional perfect-foresight PSM.", "value-perfect-foresight-lp", allowed_values=("cyclic", "fixed", "free")),
    ParameterDefinition("market.voll_gbp_per_mwh", "Market experiment", "float", 10000.0, "scientific", "advanced", "Value of lost load charged to involuntary demand curtailment.", "value-perfect-foresight-lp", unit="GBP/MWh", minimum=0.0, maximum=1000000.0),
    ParameterDefinition("carbon.factor_scenario", "Carbon accounting", "enum", "value_current_authoritative_v1", "scientific", "advanced", "Pins the carbon-factor dataset, variants and accounting boundary used by the annual carbon ledger.", "application", allowed_values=("value_current_authoritative_v1", "doctoral_reproduction_2026_07_18")),
    ParameterDefinition("terminal.policy", "Terminal horizon", "enum", "report_only", "scientific", "advanced", "Reports, advances planning-only tail years, or extends the complete model under a distinct project revision.", "application", allowed_values=("report_only", "pipeline_tail", "full_extension")),
    ParameterDefinition("fleet.valuation_discount_rate", "Terminal horizon", "float", 0.05, "scientific", "advanced", "Discount rate for informational model remaining-capital value; the value never enters dispatch or system cost.", "application", unit="fraction", minimum=0.0, maximum=1.0),
    ParameterDefinition("storage.cost.discount_rate", "Storage cost", "float", 0.05, "scientific", "advanced", "Real discount rate used by dynamic annual-average cost recovery.", "dynamic-annual-storage-cost", unit="fraction", minimum=0.0, maximum=1.0),
    ParameterDefinition("storage.cost.utilisation_floor_fraction", "Storage cost", "float", 0.0, "scientific", "advanced", "Optional floor relative to full-utilisation design sales for later-year recovery; the first year always uses full utilisation.", "dynamic-annual-storage-cost", unit="fraction", minimum=0.0, maximum=1.0),
    ParameterDefinition("storage.cost.custom_formula", "Storage cost", "string", "cycle_depreciation_gbp_per_mwh + dwell_periods * holding_recovery_gbp_per_mwh_period", "scientific", "advanced", "Arithmetic-only custom storage bid formula over approved variables.", "user-formula-storage-cost"),

    # Runtime/output settings do not define the scientific scenario.
    ParameterDefinition("runtime.checkpoint_enabled", "Output/runtime", "boolean", True, "runtime", "runtime", "Allows durable annual restart checkpoints.", "application"),
    ParameterDefinition("runtime.market_trace_level", "Output/runtime", "enum", "summary", "runtime", "runtime", "Controls period-level market evidence volume.", "value-bid-at-cost-psm", allowed_values=("off", "summary", "full")),
    ParameterDefinition("runtime.market_balance_diagnostic", "Output/runtime", "boolean", False, "runtime", "runtime", "Writes the verbose per-period balance-composition diagnostic only when explicitly enabled.", "value-bid-at-cost-psm"),
    ParameterDefinition("runtime.energy_balance_strict", "Output/runtime", "boolean", False, "runtime", "runtime", "Stops a run at the first period whose declared energy-balance residual exceeds the numerical tolerance; by default the imbalance is recorded and reported (P0-4).", "value-bid-at-cost-psm"),
    ParameterDefinition("runtime.market_export_format", "Output/runtime", "enum", "sqlite", "runtime", "runtime", "Keeps SQLite as the canonical ledger and optionally creates post-run Parquet files.", "value-bid-at-cost-psm", allowed_values=("sqlite", "parquet")),
    ParameterDefinition("runtime.generation_trace_level", "Output/runtime", "enum", "off", "runtime", "runtime", "Controls generation trace volume.", "value-bid-at-cost-psm", allowed_values=("off", "summary", "full")),
    ParameterDefinition("runtime.console_verbosity", "Output/runtime", "enum", "normal", "runtime", "runtime", "Controls console logging only.", "application", allowed_values=("quiet", "normal", "debug")),
    ParameterDefinition("runtime.artifact_batch_size", "Output/runtime", "integer", 500, "runtime", "runtime", "Batch size for durable evidence writers.", "application", unit="rows", minimum=1, maximum=100_000),
    ParameterDefinition("runtime.ensemble_max_parallel_children", "Output/runtime", "integer", 1, "runtime", "runtime", "Bounded child-run concurrency for an explicitly declared ensemble.", "application", minimum=1, maximum=16),
)

REGISTRY = {definition.id: definition for definition in PARAMETERS}
ALIASES = {
    "scenario": "scenario.id",
    "success_mode": "planning.success_mode",
    "random_seed": "planning.random_seed",
}


def parameter_schema() -> dict[str, object]:
    return {
        "schema_version": "value.parameter-registry/v1",
        "parameters": [item.api_dict() for item in PARAMETERS],
    }


def _binding_json(pack_root: Path, role: str, cache: dict[str, object]) -> object:
    if role in cache:
        return cache[role]
    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    binding = manifest.get("bindings", {}).get(role)
    if not binding:
        raise ParameterValidationError(f"Data Pack does not bind {role}")
    path = (pack_root / str(binding["uri"])).resolve()
    try:
        path.relative_to(pack_root.resolve())
    except ValueError as exc:
        raise ParameterValidationError(f"Data Pack binding {role} escapes its root") from exc
    try:
        cache[role] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParameterValidationError(
            f"Data Pack binding {role} is not readable valid JSON: {exc}"
        ) from exc
    return cache[role]


def _dotted(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ParameterValidationError(f"Data Pack parameter path is missing: {path}")
        current = current[part]
    return current


def _validated(definition: ParameterDefinition, value: object) -> object:
    kind = definition.value_type
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ParameterValidationError(f"{definition.id} must be a boolean")
        converted = value
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ParameterValidationError(f"{definition.id} must be an integer")
        converted = int(value)
    elif kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParameterValidationError(f"{definition.id} must be a number")
        converted = float(value)
    elif kind in {"enum", "string"}:
        if not isinstance(value, str):
            raise ParameterValidationError(f"{definition.id} must be a string")
        converted = value
    else:
        raise ParameterValidationError(f"Unsupported registry type {kind}")
    if definition.allowed_values and converted not in definition.allowed_values:
        allowed = ", ".join(str(item) for item in definition.allowed_values)
        raise ParameterValidationError(f"{definition.id} must be one of: {allowed}")
    if definition.minimum is not None and float(converted) < definition.minimum:  # type: ignore[arg-type]
        raise ParameterValidationError(f"{definition.id} must be >= {definition.minimum}")
    if definition.maximum is not None and float(converted) > definition.maximum:  # type: ignore[arg-type]
        raise ParameterValidationError(f"{definition.id} must be <= {definition.maximum}")
    return converted


@dataclass(frozen=True)
class SchemeCScientificParameters:
    values: Mapping[str, object]

    def get(self, parameter_id: str) -> object:
        return self.values[parameter_id]


@dataclass(frozen=True)
class SchemeCRuntimeOptions:
    values: Mapping[str, object]
    periods_per_year: int


@dataclass(frozen=True)
class ResolvedParameterSet:
    scientific: SchemeCScientificParameters
    runtime: SchemeCRuntimeOptions
    sources: Mapping[str, Mapping[str, object]]
    warnings: tuple[str, ...]
    warning_events: tuple[Mapping[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "value.resolved-parameters/v1",
            "scientific_parameters": dict(self.scientific.values),
            "runtime_options": {
                **self.runtime.values,
                "runtime.periods_per_year": self.runtime.periods_per_year,
                "runtime.full_year": self.runtime.periods_per_year == 17_520,
            },
            "sources": {key: dict(value) for key, value in self.sources.items()},
            "warnings": list(self.warnings),
            "warning_events": [dict(item) for item in self.warning_events],
        }


def resolve_scheme_c_parameters(
    pack_root: Path,
    project_overrides: Mapping[str, object] | None = None,
    runtime_overrides: Mapping[str, object] | None = None,
    *,
    periods_per_year: int = 17_520,
) -> ResolvedParameterSet:
    project_values = {
        ALIASES.get(str(key), str(key)): value
        for key, value in dict(project_overrides or {}).items()
    }
    runtime_values = {
        ALIASES.get(str(key), str(key)): value
        for key, value in dict(runtime_overrides or {}).items()
    }
    unknown = (set(project_values) | set(runtime_values)).difference(REGISTRY)
    if unknown:
        raise ParameterValidationError("Unknown parameter(s): " + ", ".join(sorted(unknown)))
    for key in project_values:
        definition = REGISTRY[key]
        if definition.category == "fixed":
            raise ParameterValidationError(f"{key} is fixed by the VALUE module version")
        if definition.category == "runtime":
            raise ParameterValidationError(f"{key} belongs in runtime_options, not parameters")
    for key in runtime_values:
        if REGISTRY[key].category != "runtime":
            raise ParameterValidationError(f"{key} is scientific and belongs in parameters")
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int):
        raise ParameterValidationError("periods_per_year must be an integer")
    if periods_per_year < 1 or periods_per_year > 17_520:
        raise ParameterValidationError("periods_per_year must be between 1 and 17520")

    scientific: dict[str, object] = {}
    runtime: dict[str, object] = {}
    sources: dict[str, dict[str, object]] = {}
    pack_cache: dict[str, object] = {}
    for definition in PARAMETERS:
        value = definition.default
        source = "module_fixed" if definition.category == "fixed" else "module_default"
        if definition.category == "runtime":
            if definition.id in runtime_values:
                value, source = runtime_values[definition.id], "run_option"
        else:
            if definition.data_pack_role:
                value = _dotted(
                    _binding_json(pack_root, definition.data_pack_role, pack_cache),
                    str(definition.data_pack_path),
                )
                source = "data_pack"
            if definition.id in project_values:
                value, source = project_values[definition.id], "project_override"
        value = _validated(definition, value)
        target = runtime if definition.category == "runtime" else scientific
        target[definition.id] = value
        sources[definition.id] = {
            "source": source,
            "data_pack_role": definition.data_pack_role,
            "project_override": definition.id in project_values,
        }

    warnings: list[str] = []
    warning_events: list[Mapping[str, str]] = []
    if float(scientific["market.bid_multiplier"]) != 1.0:
        warnings.append(
            "market.bid_multiplier is experimental; this run cannot be described as strict bid-at-cost"
        )
        warning_events.append(warning_event(
            "GF_PARAMETER_EXPERIMENTAL_BID_MULTIPLIER",
            "parameter",
            "The bid multiplier is experimental; this run is not strict bid-at-cost.",
        ))
    compile_storage_formula(str(scientific["storage.cost.custom_formula"]))
    from .network_method_rules import NetworkMethodRulesError, dec_pricing_inputs

    try:
        dec_pricing_inputs(scientific)
    except NetworkMethodRulesError as exc:
        raise ParameterValidationError(str(exc)) from exc
    return ResolvedParameterSet(
        SchemeCScientificParameters(scientific),
        SchemeCRuntimeOptions(runtime, periods_per_year),
        sources,
        tuple(warnings),
        tuple(warning_events),
    )


class SchemeCLegacyParameterAdapter:
    """The only translation point from typed v2 parameters to VALUE globals."""

    def __init__(self, resolved: ResolvedParameterSet) -> None:
        self.resolved = resolved

    def environment(self, *, start_year: int) -> dict[str, str]:
        p, r = self.resolved.scientific.values, self.resolved.runtime.values
        mode = "lottery" if p["planning.success_mode"] == "stochastic" else "expected"
        return {
            "PLANNING_USE_MEDIAN": "1" if p["planning.timeline_statistic"] == "median" else "0",
            "PIPELINE_DEFER_SPREAD_YEARS": str(p["planning.defer_spread_years"]),
            "REPD_ZOMBIE_STATUS_STALE_YEAR": str(p["planning.zombie_status_stale_year"]),
            "REPD_ZOMBIE_SNAPSHOT_YEAR": str(start_year),
            "REPD_ZOMBIE_CONSTRUCTION_GRACE_YEARS": str(p["planning.construction_grace_years"]),
            "REPD_INCLUDE_UNCERTAIN_PROJECTS": "1" if p["planning.include_uncertain_projects"] else "0",
            "APPLY_REPD_INITIAL_SNAPSHOT": "1" if p["fleet.repd_initial_snapshot"] else "0",
            "REPD_UNCERTAIN_AS_MODEL_DECISION": "1" if p["planning.uncertain_as_model_decision"] else "0",
            "STORAGE_EXPANSION_CAP_FRACTION": str(p["expansion.storage_cap_fraction"]),
            "STORAGE_CAP_CREDIT_MODE": {
                "value_capacity_credit": "scheme_c",
            }.get(str(p["expansion.storage_credit_method"]), str(p["expansion.storage_credit_method"])),
            "STORAGE_CAP_METHOD": {
                "value_simulation_trace": "scheme_c_sim_trace",
            }.get(str(p["expansion.storage_cap_method"]), str(p["expansion.storage_cap_method"])),
            "STORAGE_VIRTUAL_POOL_ENERGY_MWH": str(p["storage.virtual_pool_energy_mwh"]),
            "STORAGE_VIRTUAL_POOL_POWER_MW": str(p["storage.virtual_pool_power_mw"]),
            "MODEL_SUCCESS_MODE": mode,
            "MODEL_SUCCESS_RANDOM_SEED": str(p["planning.random_seed"]),
            "PHYSICAL_PERIOD_HOURS": str(p["clock.period_hours"]),
            "SCENARIO_V2": "1",
            "DECARB_V2_SCENARIO": str(p["scenario.id"]),
            "DECARB_SCENARIO": f"{p['scenario.id']}_2025_2035",
            "ENABLE_CHECKPOINT": "1" if r["runtime.checkpoint_enabled"] else "0",
            # The old per-row CSV trace is permanently disabled. The typed
            # SQLite ledger receives the selected level at the module boundary.
            "SAVE_MARKET_TRACE": "0",
            "MARKET_LEDGER_LEVEL": str(r["runtime.market_trace_level"]),
            "MARKET_BALANCE_DIAGNOSTIC": (
                "1" if r["runtime.market_balance_diagnostic"] else "0"
            ),
            "MARKET_EXPORT_FORMAT": str(r["runtime.market_export_format"]),
            "ENERGY_BALANCE_STRICT": "1" if r["runtime.energy_balance_strict"] else "0",
            "SAVE_GENERATION_TRACE": "0" if r["runtime.generation_trace_level"] == "off" else "1",
        }

    def apply_config(self, config: object) -> None:
        p = self.resolved.scientific.values
        config.simulation_parameters["bidding_factor"] = float(p["market.bid_multiplier"])
        config.repd_filtering["apply_zombie_filter"] = bool(p["planning.zombie_filter_enabled"])
        config.repd_filtering["include_uncertain_projects"] = bool(p["planning.include_uncertain_projects"])
        config.repd_filtering["zombie_status_stale_year"] = int(p["planning.zombie_status_stale_year"])
        config.repd_filtering["minimum_project_size_mw"] = float(p["planning.minimum_project_size_mw"])
        config.repd_filtering["max_completion_year"] = int(p["planning.max_completion_year"])


def scheme_c_model_card(resolved: ResolvedParameterSet | None = None) -> dict[str, object]:
    fixed = {
        item.id: (resolved.scientific.values[item.id] if resolved else item.default)
        for item in PARAMETERS
        if item.category == "fixed"
    }
    return {
        "schema_version": "value.model-card/v1",
        "module_id": "value-bid-at-cost-psm",
        "title": "VALUE live bid-at-cost PSM model card",
        "fixed_assumptions": fixed,
        "strict_bid_at_cost": (
            True if resolved is None else float(resolved.scientific.values["market.bid_multiplier"]) == 1.0
        ),
        "notes": [
            "Interconnectors are external import offers, not internal transmission lines.",
            "Changing a fixed assumption requires a new module version.",
            "Short diagnostic runs verify wiring and do not publish annual economics.",
            "The VALUE CEM resource-cost headline is distinct from the historical VALUE cost metric.",
        ],
    }
