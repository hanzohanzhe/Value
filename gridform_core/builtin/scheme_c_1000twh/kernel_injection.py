"""Per-period site and firm availability injected into the retained kernel (P0-5b S5/S8).

Under the corrected profile ``SchemeCNativePSM`` builds ``KernelSiteInputs``
from the same shared arrays the canonical adapter uses
(``site_weather.site_cf_by_source`` and ``firm_availability``) and passes them
through the module runtime (``runtime.kernel_site_inputs``).  The kernel then
sets, every period,

* ``capacity_limit = capacity_multiplier x unit x cf[p]`` for each
  representative VRE agent (unit 20 MW for wind, 1 for solar: the kernel's own
  ``piecewise_limit*`` scaling), replacing its ``IterLimit`` weather clock;
* ``capacity_limit = base_capacity x availability[p]`` for the ``Nuclear`` and
  ``Hydro_natural_flow`` agents.

Without an injection (the doctoral profile, unit sessions) nothing changes.
The weather cache key (``weather_cache_key``) applies to every profile.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

METHOD_ID = "value.kernel-site-inputs/v1"
WIND_UNIT = 20.0


@dataclass(frozen=True)
class KernelSiteInputs:
    vre_cf: Mapping[str, np.ndarray]          # kernel generator name -> per-period CF (0..1)
    firm_availability: Mapping[str, np.ndarray]  # "Nuclear" / "Hydro_natural_flow" -> per-period 0..1
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class _Bound:
    vre: list
    firm: list


def weather_cache_key(*paths: str) -> tuple:
    key = []
    for path in paths:
        real = os.path.realpath(str(path))
        try:
            stat = os.stat(real)
            key.append((real, stat.st_size, stat.st_mtime_ns))
        except OSError:
            key.append((real, None, None))
    return tuple(key)


def unit_scale(name: str) -> float:
    return 1.0 if str(name).startswith("solar") else WIND_UNIT


def active_site_inputs(runtime: object, generators: Any, periods: int) -> _Bound | None:
    inputs = getattr(runtime, "kernel_site_inputs", None) if runtime is not None else None
    if inputs is None:
        return None
    by_name = {str(getattr(generator, "name", "")): generator for generator in generators}
    vre, firm = [], []
    for name, values in inputs.vre_cf.items():
        if len(values) < periods:
            raise ValueError(f"Injected site CF for {name} is shorter than the {periods}-period run")
        generator = by_name.get(name)
        if generator is not None:
            vre.append((generator, unit_scale(name), np.asarray(values, dtype=float)))
    for name, values in inputs.firm_availability.items():
        if len(values) < periods:
            raise ValueError(f"Injected availability for {name} is shorter than the {periods}-period run")
        generator = by_name.get(name)
        if generator is not None:
            firm.append((generator, float(generator.capacity_limit), np.asarray(values, dtype=float)))
    return _Bound(vre, firm)


def assign_period(bound: _Bound, period: int) -> None:
    for generator, scale, values in bound.vre:
        generator.capacity_limit = generator.capacity_multiplier * scale * float(values[period])
    for generator, base, values in bound.firm:
        generator.capacity_limit = base * float(values[period])
