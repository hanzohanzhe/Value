"""Resolve national-demand authority before zonal redispatch clearing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from .zonal_contracts import ZonalDemand


SCENARIO_SCALED_ZONAL_SHARES = "scenario_scaled_zonal_shares"
NETWORK_PACK_ABSOLUTE_DEMAND = "network_pack_absolute_demand"
SUPPORTED_ZONAL_DEMAND_MODES = frozenset(
    {SCENARIO_SCALED_ZONAL_SHARES, NETWORK_PACK_ABSOLUTE_DEMAND}
)


@dataclass(frozen=True)
class ZonalDemandAlignmentRow:
    period_id: str
    research_real_demand_mwh: float
    research_forecast_demand_mwh: float
    network_national_demand_mwh: float
    scale_factor: float
    aligned_zonal_total_mwh: float
    conservation_residual_mwh: float


@dataclass(frozen=True)
class ZonalDemandAlignment:
    mode: str
    period_ids: tuple[str, ...]
    real_demand_mwh: tuple[float, ...]
    forecast_demand_mwh: tuple[float, ...]
    demand_mwh_by_zone: Mapping[str, tuple[float, ...]]
    rows: tuple[ZonalDemandAlignmentRow, ...]
    summary: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "demand_mwh_by_zone",
            MappingProxyType(dict(self.demand_mwh_by_zone)),
        )
        object.__setattr__(self, "summary", MappingProxyType(dict(self.summary)))


def align_zonal_demand(
    *,
    mode: str,
    period_ids: Sequence[str],
    research_real_mwh: Sequence[float],
    research_forecast_mwh: Sequence[float],
    network_demand: ZonalDemand,
) -> ZonalDemandAlignment:
    """Return one immutable chronology with one declared national authority."""

    periods = tuple(str(item) for item in period_ids)
    real = tuple(float(item) for item in research_real_mwh)
    forecast = tuple(float(item) for item in research_forecast_mwh)
    if mode not in SUPPORTED_ZONAL_DEMAND_MODES:
        raise ValueError(f"Unsupported zonal demand mode: {mode}")
    zone_ids = tuple(network_demand.demand_mwh_by_zone)
    if not zone_ids:
        raise ValueError("Zonal network demand requires at least one zone")
    network_demand.validate(set(zone_ids))
    if not periods or len(set(periods)) != len(periods):
        raise ValueError("Zonal demand alignment requires unique periods")
    network_index = {
        period_id: index for index, period_id in enumerate(network_demand.period_ids)
    }
    try:
        selected_network_indices = tuple(network_index[period_id] for period_id in periods)
    except KeyError as exc:
        raise ValueError(
            "Zonal network demand period IDs do not match the research chronology"
        ) from exc
    network_national_mwh = tuple(
        float(network_demand.national_demand_mwh[index])
        for index in selected_network_indices
    )
    network_demand_mwh_by_zone = {
        zone_id: tuple(
            float(network_demand.demand_mwh_by_zone[zone_id][index])
            for index in selected_network_indices
        )
        for zone_id in zone_ids
    }
    if len(real) != len(periods) or len(forecast) != len(periods):
        raise ValueError("Research demand chronology length does not match period IDs")
    if any(not math.isfinite(value) or value < 0.0 for value in real + forecast):
        raise ValueError("Research demand values must be finite and non-negative")

    aligned = {zone_id: [] for zone_id in zone_ids}
    output_real = (
        network_national_mwh
        if mode == NETWORK_PACK_ABSOLUTE_DEMAND
        else real
    )
    if mode == NETWORK_PACK_ABSOLUTE_DEMAND:
        absolute_forecast: list[float] = []
        for index, period_id in enumerate(periods):
            if real[index] == 0.0:
                if forecast[index] != 0.0 or output_real[index] != 0.0:
                    raise ValueError(
                        f"Base forecast-to-real ratio is undefined at {period_id}"
                    )
                absolute_forecast.append(0.0)
            else:
                absolute_forecast.append(
                    output_real[index] * forecast[index] / real[index]
                )
        output_forecast = tuple(absolute_forecast)
    else:
        output_forecast = forecast
    rows: list[ZonalDemandAlignmentRow] = []
    for index, period_id in enumerate(periods):
        network_national = network_national_mwh[index]
        if mode == NETWORK_PACK_ABSOLUTE_DEMAND or (
            network_national == 0.0 and output_real[index] == 0.0
        ):
            scale = 1.0
        elif network_national == 0.0:
            raise ValueError(
                f"Zonal network demand has zero national demand at {period_id}; "
                "no spatial fallback weights were declared"
            )
        else:
            scale = output_real[index] / network_national
        remaining = output_real[index]
        for zone_id in zone_ids[:-1]:
            value = network_demand_mwh_by_zone[zone_id][index] * scale
            aligned[zone_id].append(value)
            remaining -= value
        aligned[zone_ids[-1]].append(remaining)
        aligned_total = sum(aligned[zone_id][index] for zone_id in zone_ids)
        rows.append(ZonalDemandAlignmentRow(
            period_id=period_id,
            research_real_demand_mwh=real[index],
            research_forecast_demand_mwh=forecast[index],
            network_national_demand_mwh=network_national,
            scale_factor=scale,
            aligned_zonal_total_mwh=aligned_total,
            conservation_residual_mwh=aligned_total - output_real[index],
        ))
    return ZonalDemandAlignment(
        mode=mode,
        period_ids=periods,
        real_demand_mwh=output_real,
        forecast_demand_mwh=output_forecast,
        demand_mwh_by_zone={
            zone_id: tuple(values) for zone_id, values in aligned.items()
        },
        rows=tuple(rows),
        summary={
            "mode": mode,
            "period_count": len(periods),
            "research_real_demand_mwh": sum(real),
            "network_national_demand_mwh": sum(network_national_mwh),
            "aligned_national_demand_mwh": sum(output_real),
            "minimum_scale_factor": min(row.scale_factor for row in rows),
            "maximum_scale_factor": max(row.scale_factor for row in rows),
            "mean_scale_factor": sum(row.scale_factor for row in rows) / len(rows),
            "maximum_absolute_conservation_residual_mwh": max(
                abs(row.conservation_residual_mwh) for row in rows
            ),
        },
    )
