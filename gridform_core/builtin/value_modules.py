"""Public VALUE module entry points.

The underlying implementations are copied from the doctoral reproduction code,
but Studies and module manifests bind only to these product-neutral entry points.
"""

from dataclasses import replace

from ..module_context import ImmutableContextResolver, RunStaticContext, YearContext
from .scheme_c_1000twh.copperplate_balancing import CopperplateBalancing
from .scheme_c_1000twh.runtime_compat.storage_cost import (
    DynamicStorageCostDefinition,
    SchemeCLegacyStorageCostDefinition,
    UserFormulaStorageCostDefinition,
)
from .scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM
from .scheme_c_1000twh.staged_psm import StagedBidAtCostPSM
from .scheme_c_1000twh.v2_module_definitions import (
    SchemeCAgentInvestmentDefinition,
    SchemeCPlanningPipelineDefinition,
    SchemeCStateTransitionDefinition,
    SchemeCStorageExpansionPolicyDefinition,
    SchemeCVREExpansionPolicyDefinition,
)
from ..value_runtime_adapter import finalize_value_runtime_artifacts, public_value_payload


class ValueBidAtCostPSM(SchemeCNativePSM):
    id = "value-bid-at-cost-psm"

    def run(self, model_input):
        result = super().run(model_input)
        if self._context is not None:
            finalize_value_runtime_artifacts(self._context.output_dir)
        return replace(result, extensions=public_value_payload(result.extensions))


class ValueStagedBidAtCostPSM(StagedBidAtCostPSM):
    id = "value-staged-bid-at-cost-psm"

    def configure(
        self,
        run_context: RunStaticContext,
        resolver: ImmutableContextResolver,
    ) -> None:
        super().configure(run_context, resolver)

    def start_year(self, year_context: YearContext) -> None:
        super().start_year(year_context)

    def run(self, model_input):
        result = super().run(model_input)
        if self._output_dir is not None:
            finalize_value_runtime_artifacts(self._output_dir)
        return replace(result, extensions=public_value_payload(result.extensions))


class ValueCopperplateBalancing(CopperplateBalancing):
    id = "value-copperplate-balancing"


class ValueLegacyStorageCost(SchemeCLegacyStorageCostDefinition):
    id = "value-legacy-storage-tariff"


class ValueStorageExpansionPolicy(SchemeCStorageExpansionPolicyDefinition):
    id = "value-storage-expansion-policy"


class ValueAnnualStateTransition(SchemeCStateTransitionDefinition):
    id = "value-annual-state-transition"


ValueDynamicStorageCost = DynamicStorageCostDefinition
ValueUserFormulaStorageCost = UserFormulaStorageCostDefinition
ValueAgentInvestment = SchemeCAgentInvestmentDefinition
ValuePlanningPipeline = SchemeCPlanningPipelineDefinition
ValueVREExpansionPolicy = SchemeCVREExpansionPolicyDefinition

__all__ = [
    "ValueAgentInvestment",
    "ValueAnnualStateTransition",
    "ValueBidAtCostPSM",
    "ValueCopperplateBalancing",
    "ValueDynamicStorageCost",
    "ValueLegacyStorageCost",
    "ValuePlanningPipeline",
    "ValueStagedBidAtCostPSM",
    "ValueStorageExpansionPolicy",
    "ValueUserFormulaStorageCost",
    "ValueVREExpansionPolicy",
]
