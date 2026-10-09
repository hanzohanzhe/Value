"""Historical identifiers that persisted state may still carry.

VALUE renamed its FORCE/Scheme C-era module ids and the annual orchestrator
engine label.  Runs, Studies and archives written before the rename are
immutable on disk, so readers normalise the old names here instead of
rewriting files.  This is the single map; do not add private copies.
"""

from __future__ import annotations

from typing import Mapping

CURRENT_ORCHESTRATOR_ENGINE = "value-annual-orchestrator/v2"

# Old execution_engine label -> current label (R2-08).
LEGACY_ENGINE_IDS: Mapping[str, str] = {
    "gridform-annual-orchestrator/v2": CURRENT_ORCHESTRATOR_ENGINE,
}

# Every engine label that denotes a run of the v2 annual application service.
ORCHESTRATOR_ENGINES = frozenset({CURRENT_ORCHESTRATOR_ENGINE, *LEGACY_ENGINE_IDS})

# Old module / extension id -> current id.  (The copperplate balancing class
# still reports ``force-copperplate-balancing`` at runtime; mapping it would
# change Study fingerprints, so it is left to the package that renames it.)
LEGACY_MODULE_IDS: Mapping[str, str] = {
    "force-staged-bid-at-cost-psm": "value-staged-bid-at-cost-psm",
    "force-zonal-redispatch-balancing": "value-zonal-redispatch-balancing",
    "force-representative-point-weather": "value-representative-point-weather",
    "storage-expansion-scheme-c": "value-storage-expansion-policy",
    "scheme-c-state-transition": "value-annual-state-transition",
    "force-zonal-redispatch-extension": "value-zonal-redispatch-extension",
}


def normalize_module_id(module_id: object) -> str:
    text = str(module_id)
    return LEGACY_MODULE_IDS.get(text, text)


def normalize_engine(engine: object) -> str:
    text = str(engine)
    return LEGACY_ENGINE_IDS.get(text, text)


def is_orchestrator_engine(engine: object) -> bool:
    return str(engine) in ORCHESTRATOR_ENGINES
