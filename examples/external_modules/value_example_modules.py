"""Visible external-module fixtures; these are tests, not scientific baselines."""

from __future__ import annotations

from dataclasses import replace

from gridform_core.builtin.scheme_c_1000twh.runtime_compat.storage_cost import (
    DynamicStorageCostDefinition,
)
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCAgentInvestmentDefinition,
    SchemeCPlanningPipelineDefinition,
    SchemeCStateTransitionDefinition,
    SchemeCStorageExpansionPolicyDefinition,
    SchemeCVREExpansionPolicyDefinition,
)
from gridform_core.perfect_foresight_psm import PerfectForesightPSM


class ExampleMarkedPSM(PerfectForesightPSM):
    """Delegate to the public LP and add a £123.45 execution marker."""

    id = "example-marked-perfect-foresight-psm"
    version = "1.0.0"

    def run(self, model_input):
        result = super().run(model_input)
        marker = 123.45
        periods = list(result.period_summaries)
        periods[0] = replace(
            periods[0],
            physical_resource_cost_gbp=periods[0].physical_resource_cost_gbp + marker,
        )
        operating_components = dict(
            result.extensions.get("physical_operating_cost_components_gbp") or {}
        )
        operating_components["external_fixture_marker"] = marker
        return replace(
            result,
            module_id=self.id,
            module_version=self.version,
            total_system_cost_gbp=result.total_system_cost_gbp + marker,
            total_operational_cost_gbp=result.total_operational_cost_gbp + marker,
            period_summaries=tuple(periods),
            extensions={
                **dict(result.extensions),
                "physical_operating_cost_components_gbp": operating_components,
                "external_fixture_executed": True,
                "external_fixture_cost_marker_gbp": marker,
            },
        )


class ExampleInvestment(SchemeCAgentInvestmentDefinition):
    id = "example-agent-investment"
    version = "1.0.0"

    def decide(self, run, state, market, headroom):
        value = super().decide(run, state, market, headroom)
        return replace(value, module_id=self.id, extensions={
            **dict(value.extensions), "example_investment_executed": True,
        })


class ExamplePipeline(SchemeCPlanningPipelineDefinition):
    id = "example-planning-pipeline"
    version = "1.0.0"

    def advance_year(self, run, state):
        value = super().advance_year(run, state)
        operating = replace(value.operating_state, extensions={
            **dict(value.operating_state.extensions), "example_pipeline_advance_executed": True,
        })
        return replace(value, operating_state=operating)

    def admit_projects(self, run, state, proposals):
        value = super().admit_projects(run, state, proposals)
        return replace(value, next_pipeline=tuple(value.next_pipeline))


class ExampleVRECap(SchemeCVREExpansionPolicyDefinition):
    id = "example-vre-cap"
    version = "1.0.0"

    def evaluate(self, run, state, market):
        value = super().evaluate(run, state, market)
        return replace(value, module_id=self.id, extensions={
            **dict(value.extensions), "example_vre_cap_executed": True,
        })


class ExampleStorageCap(SchemeCStorageExpansionPolicyDefinition):
    id = "example-storage-cap"
    version = "1.0.0"

    def evaluate(self, run, state, market):
        value = super().evaluate(run, state, market)
        return replace(value, module_id=self.id, extensions={
            **dict(value.extensions), "example_storage_cap_executed": True,
        })


class ExampleTransition(SchemeCStateTransitionDefinition):
    id = "example-state-transition"
    version = "1.0.0"

    def apply(self, run, current_state, planning, investment):
        value = super().apply(run, current_state, planning, investment)
        return replace(value, extensions={
            **dict(value.extensions), "example_transition_executed": True,
        })


class ExampleStorageCost(DynamicStorageCostDefinition):
    id = "example-storage-cost"
    version = "1.0.0"
    scientific_version = "example-only-not-a-baseline"
