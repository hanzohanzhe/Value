"""A small, auditable example of replacing the VALUE PSM module.

This is an integration tutorial, not a scientifically recommended market model.
It changes a quantity offer while preserving the original marginal costs used in
the physical resource-cost ledger.  Storage remains centrally co-optimised by
the public perfect-foresight LP.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from gridform_core.perfect_foresight_psm import (
    PerfectForesightInputError,
    PerfectForesightPSM,
)


class ThermalQuantityOfferPSM(PerfectForesightPSM):
    """Offer 90% of each thermal resource's physical availability."""

    id = "example-thermal-quantity-offer-psm"
    version = "1.0.0"
    scientific_version = "tutorial-only-not-a-baseline"
    thermal_offer_fraction = 0.90

    def run(self, model_input):
        chronology = model_input.chronology
        if chronology is None:
            raise PerfectForesightInputError(
                f"{self.id} requires PSMInput.chronology; no file-path fallback is allowed."
            )

        original_hash = hashlib.sha256(
            json.dumps(
                chronology.to_dict(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        offered_resources = tuple(
            replace(
                resource,
                availability=tuple(
                    float(value) * self.thermal_offer_fraction
                    for value in resource.availability
                ),
                extensions={
                    **dict(resource.extensions),
                    "physical_availability": list(resource.availability),
                    "quantity_offer_fraction": self.thermal_offer_fraction,
                },
            )
            if resource.resource_type == "thermal"
            else resource
            for resource in chronology.resources
        )
        offered_chronology = replace(
            chronology,
            resources=offered_resources,
            extensions={
                **dict(chronology.extensions),
                "offer_policy": "thermal_quantity_fraction",
                "thermal_quantity_offer_fraction": self.thermal_offer_fraction,
                "source_chronology_sha256": original_hash,
            },
        )

        result = super().run(replace(model_input, chronology=offered_chronology))
        return replace(
            result,
            extensions={
                **dict(result.extensions),
                "external_module": {
                    "module_id": self.id,
                    "module_version": self.version,
                    "scientific_version": self.scientific_version,
                    "offer_dimension": "quantity",
                    "thermal_quantity_offer_fraction": self.thermal_offer_fraction,
                    "source_chronology_sha256": original_hash,
                    "clearing_engine": "value.perfect-foresight-single-node-lp/v1",
                    "scientific_status": "tutorial_only_not_a_baseline",
                },
            },
        )
