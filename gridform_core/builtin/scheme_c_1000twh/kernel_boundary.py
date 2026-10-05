"""Interconnector input of the retained kernel (P0-5a; findings P6-24, P6-03, P6-01, P6-02).

At 35aadb3 ``run_simulation`` read the ten boundary files itself (profiles
flattened with ``header=0``, prices as the first column with NaN -> 0),
wrapped every series in ``IterLimit_new`` - which serves each row twice, so
period p received row p // 2 (P6-24) - and fed three Connection objects with
another country's files.  Decisions Q9/A3 and A5 correct this in both
profiles:

* a configured run injects ``KernelBoundary`` (built here from the shared
  declarative reader, ``data_method.read_boundary``) through the module
  runtime, so the kernel sees exactly the canonical adapter's series;
* sessions without a runtime injection (the reference bridge, unit tests)
  read the files with the 35aadb3 readers;
* either way each Connection receives its own country's series, period by
  period on the run clock (src[p], wrapping a shorter series).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ...interconnector_identity import COUNTRIES, KERNEL_CONNECTION_BY_COUNTRY

METHOD_ID = "value.kernel-boundary/v2"


@dataclass(frozen=True)
class KernelBoundary:
    """Per-period transfer constraint (MW, signed) and external price (GBP/MWh) by country."""

    flow_mw: Mapping[str, np.ndarray]
    price_gbp_per_mwh: Mapping[str, np.ndarray]
    source: str
    evidence: Mapping[str, Any]

    def at(self, country: str, period: int) -> tuple[float, float]:
        flow = self.flow_mw[country]
        price = self.price_gbp_per_mwh[country]
        return flow[period % len(flow)], price[period % len(price)]


def from_pack(pack_root: Path, manifest: Mapping[str, Any], policy: Any, periods: int) -> KernelBoundary:
    """The canonical boundary of a pack (same reader, same clock) for the kernel."""

    from ...data_method import read_boundary

    boundary = read_boundary(pack_root, manifest, policy, periods=periods)
    return KernelBoundary(
        flow_mw={country: np.asarray(entry.flow_mw, dtype=float) for country, entry in boundary.countries.items()},
        price_gbp_per_mwh={
            country: np.asarray(entry.price_gbp_per_mwh, dtype=float) for country, entry in boundary.countries.items()
        },
        source="data_method.read_boundary",
        evidence={"method_id": METHOD_ID, "data_method": policy.data_method_id, **boundary.evidence()},
    )


def from_legacy_files(file_paths: Mapping[str, str]) -> KernelBoundary:
    """35aadb3 file readers (no pack manifest available), served period by period."""

    flows, prices = {}, {}
    for country in COUNTRIES:
        flows[country] = np.array(pd.read_csv(file_paths[f"{country}_profile"])).flatten()
        prices[country] = pd.to_numeric(
            pd.read_csv(file_paths[f"{country}_price"], header=None).iloc[:, 0], errors="coerce"
        ).fillna(0).values
    return KernelBoundary(flows, prices, "legacy_file_readers", {"method_id": METHOD_ID})


def active_boundary(runtime: object, file_paths: Mapping[str, str], periods: int) -> KernelBoundary:
    injected = getattr(runtime, "kernel_boundary", None) if runtime is not None else None
    if injected is not None:
        for country in COUNTRIES:
            if len(injected.flow_mw[country]) < periods or len(injected.price_gbp_per_mwh[country]) < periods:
                raise ValueError(f"Injected kernel boundary for {country} is shorter than the {periods}-period run")
        return injected
    return from_legacy_files(file_paths)


def assign_period(boundary: KernelBoundary, connections: Mapping[str, Any], period: int) -> None:
    """Set every Connection's transfer constraint and external price for ``period``."""

    for country in COUNTRIES:
        connection = connections.get(KERNEL_CONNECTION_BY_COUNTRY[country])
        if connection is None:
            continue
        connection.transfer_constraint, connection.external_price = boundary.at(country, period)
