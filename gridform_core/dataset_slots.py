"""Stable semantic data-contract slots of the base VALUE data pack.

Kept apart from ``catalog`` so importing the slots never builds the module
registry (P0-2, worker import chain).  ``gridform_core.catalog`` re-exports
``DATASET_SLOTS`` unchanged.  Changing this list changes the content hash
pinned in tests/test_catalog_lazy.py; update it in the same commit (C27).
"""

DATASET_SLOTS = [
    {"role": "fleet.generators", "group": "PSM", "label": "Existing generator fleet", "formats": ["json"], "required": True},
    {"role": "demand.forecast", "group": "PSM", "label": "Forecast demand profile", "formats": ["csv", "parquet"], "required": True, "unit": "MW", "interval_minutes": 30},
    {"role": "demand.real", "group": "PSM", "label": "Real demand profile", "formats": ["csv", "parquet"], "required": True, "unit": "MW", "interval_minutes": 30},
    {"role": "weather.wind", "group": "PSM", "label": "Wind weather field", "formats": ["nc", "zarr"], "required": True},
    {"role": "weather.solar", "group": "PSM", "label": "Solar weather field", "formats": ["nc", "zarr"], "required": True},
    {"role": "market.france.profile", "group": "PSM", "label": "France import availability", "formats": ["csv"], "required": True},
    {"role": "market.france.price", "group": "PSM", "label": "France external price", "formats": ["csv"], "required": True},
    {"role": "market.belgium.profile", "group": "PSM", "label": "Belgium import availability", "formats": ["csv"], "required": True},
    {"role": "market.belgium.price", "group": "PSM", "label": "Belgium external price", "formats": ["csv"], "required": True},
    {"role": "market.netherlands.profile", "group": "PSM", "label": "Netherlands import availability", "formats": ["csv"], "required": True},
    {"role": "market.netherlands.price", "group": "PSM", "label": "Netherlands external price", "formats": ["csv"], "required": True},
    {"role": "market.norway.profile", "group": "PSM", "label": "Norway import availability", "formats": ["csv"], "required": True},
    {"role": "market.norway.price", "group": "PSM", "label": "Norway external price", "formats": ["csv"], "required": True},
    {"role": "market.ireland.profile", "group": "PSM", "label": "Ireland import availability", "formats": ["csv"], "required": True},
    {"role": "market.ireland.price", "group": "PSM", "label": "Ireland external price", "formats": ["csv"], "required": True},
    {"role": "profiles.vre_solar", "group": "CEM", "label": "System-average solar profile", "formats": ["csv"], "required": True},
    {"role": "profiles.vre_onshore", "group": "CEM", "label": "System-average onshore profile", "formats": ["csv"], "required": True},
    {"role": "profiles.vre_offshore", "group": "CEM", "label": "System-average offshore profile", "formats": ["csv"], "required": True},
    {"role": "projects.repd", "group": "CEM", "label": "Normalized planning projects", "formats": ["csv", "parquet"], "required": True},
    {"role": "source.repd_raw", "group": "CEM", "label": "Raw UK REPD source", "formats": ["csv"], "required": True},
    {"role": "costs.capital", "group": "CEM", "label": "Technology capital costs", "formats": ["csv", "json"], "required": True, "unit": "GBP/MW"},
    {"role": "policy.support", "group": "CEM", "label": "Policy and support mechanisms", "formats": ["csv", "json", "xlsx"], "required": True},
    {"role": "planning.timelines", "group": "CEM", "label": "Planning stage timelines", "formats": ["csv", "json"], "required": True},
    {"role": "planning.success_rates", "group": "CEM", "label": "Regional technology success rates", "formats": ["csv", "json"], "required": True},
    {"role": "config.model_parameters", "group": "CEM", "label": "VALUE investment and policy parameters", "formats": ["json"], "required": True},
]
