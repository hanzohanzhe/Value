"""Weather lineage only: retain the doctoral project's representative allocation.

This does not change project MW, commissioning dates, financial owners or nuclear
policy. A native independent project can represent a frozen mix of the original
generators; its available power is the sum of those generators' allocated MW.
"""
from dataclasses import replace
from math import asin, cos, isfinite, radians, sin, sqrt

from .v2.contracts import AssetStateV2

VRE = {"solar", "onshore", "offshore"}
PROPORTIONAL = "doctoral_proportional_at_commissioning"
REGION_CITY = {
    "East Midlands": "Nottingham", "Eastern": "Ipswich", "London": "London",
    "North East": "Newcastle", "North West": "Manchester", "Scotland": "Edinburgh",
    "South East": "Portsmouth", "South West": "Bournemouth", "Wales": "Cardiff",
    "West Midlands": "Birmingham", "Yorkshire and Humber": "Sheffield",
}


def representative_sites(fleet):
    sites = {}
    for name in fleet.get("generators", {}):
        technology = next((t for t in VRE if name.startswith(t + "_") or
                           (t == "offshore" and name.startswith(t))), None)
        if technology is None:
            continue
        key = name if technology == "offshore" else name.split("_", 1)[1]
        if key in fleet.get("locations", {}):
            sites[name] = {"technology": technology, **fleet["locations"][key]}
    return sites


def nearest_site(latitude, longitude, technology, sites):
    """Original haversine formula and first-in-order tie rule, not grid rounding."""
    minimum, selected = float("inf"), None
    for name, point in sites.items():
        if point["technology"] != technology:
            continue
        lat1, lon1, lat2, lon2 = map(radians, [latitude, longitude, point["lat"], point["lon"]])
        a = sin((lat2 - lat1) / 2)**2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2)**2
        distance = 2 * asin(sqrt(a)) * 6371
        if distance < minimum:
            selected, minimum = name, distance
    return selected


def attach_project_weather(state, fleet, raw_repd):
    # Reuse the preserved source's field parsing, including its textual-location
    # behavior. The planning path does NOT use the operational-stock OSGB helper.
    from .builtin.scheme_c_1000twh.runtime_compat.map_projects_to_generators_by_location import extract_location_from_repd

    sites = representative_sites(fleet)
    if not sites:
        return state
    by_id, by_name = {}, {}
    for _, row in raw_repd.iterrows():
        lat, lon = extract_location_from_repd(row)
        by_id[str(row.get("Ref ID", "")).strip()] = (lat, lon)
        if lat is not None and lon is not None:
            by_name[str(row.get("Site Name", ""))] = (lat, lon)
    projects = []
    for project in state.planning_projects:
        if project.technology not in VRE:
            projects.append(project)
            continue
        lat, lon = project.latitude, project.longitude
        if lat is None or lon is None:
            lat, lon = by_id.get(str(project.extensions.get("physical_project_id", project.project_id)), (None, None))
        if lat is None or lon is None:
            lat, lon = by_name.get(project.name, (None, None))
        name, rule = None, PROPORTIONAL
        if lat is not None and lon is not None:
            if not all(isfinite(float(v)) for v in (lat, lon)):
                raise ValueError(f"Non-finite doctoral project weather location: {project.project_id}")
            name = nearest_site(lat, lon, project.technology, sites)
            rule = "doctoral_nearest_representative"
        elif project.technology in {"solar", "onshore"}:
            city = REGION_CITY.get(str(project.region or "").strip())
            candidate = f"{project.technology}_{city}" if city else None
            if candidate in sites:
                name, rule = candidate, "doctoral_repd_region"
        evidence = {"weather_assignment_rule": rule if name else PROPORTIONAL,
                    "weather_project_location": {"lat": lat, "lon": lon},
                    "weather_mapping_source": "doctoral map_projects_to_generators + case3 commissioning"}
        if name:
            evidence["weather_source_asset_id"] = name
        projects.append(replace(project, extensions={**project.extensions, **evidence}))
    return replace(state, planning_projects=tuple(projects), extensions={
        **state.extensions, "doctoral_weather_reference_sites": sites})


def source_weights(asset, sites):
    """Validate stored lineage; never infer a new mix from a changed fleet."""
    extensions = asset.extensions
    if "weather_source_weights" in extensions:
        weights = {str(k): float(v) for k, v in dict(extensions["weather_source_weights"]).items()}
        if (not weights or any(not isfinite(v) or v < 0 for v in weights.values())
                or sum(weights.values()) > 1 + 1e-12):
            raise ValueError(f"Invalid doctoral weather weights: {asset.asset_id}")
        deficit = 1.0 - sum(weights.values())
        if deficit > 1e-12:
            cohort = float(extensions.get("weather_allocation_cohort_mw", 0.))
            # Only the source's explicitly bounded tiny-MW skip may lose mass.
            # An arbitrary partial curve is corruption, not a valid fallback.
            skipped = sum(v == 0. for v in weights.values())
            if (not isfinite(cohort) or cohort <= 0. or
                    deficit > skipped * 1e-6 / cohort + 1e-12):
                raise ValueError(f"Invalid doctoral weather weight deficit: {asset.asset_id}")
        for name in weights:
            if name not in sites or sites[name]["technology"] != asset.technology:
                raise ValueError(f"Invalid doctoral weather source identity: {asset.asset_id}: {name}")
        return weights
    # Explicit weather identity is authoritative: do not hide corruption behind
    # another financial-owner or asset-name candidate.
    explicit = extensions.get("weather_source_asset_id")
    if explicit is not None:
        if explicit not in sites or sites[explicit]["technology"] != asset.technology:
            raise ValueError(f"Invalid doctoral weather source identity: {asset.asset_id}: {explicit}")
        return {str(explicit): 1.0}
    for name in (asset.asset_id, extensions.get("assigned_generator"),
                 extensions.get("investment_owner_id"), extensions.get("source_agent_id"),
                 extensions.get("base_asset_id")):
        if name in sites and sites[name]["technology"] == asset.technology:
            return {str(name): 1.0}
    raise ValueError(f"Missing doctoral weather identity mapping for asset {asset.asset_id} ({asset.technology})")


def commissioned_project_weather(state):
    """Freeze each due cohort after all same-year explicit assignments, as case3.

    The original aggregates all unassigned MW of a technology, distributes in
    sorted generator order and gives the last generator the floating remainder.
    Keep the <=1e-6 MW source skip as zero weather availability, not invented MW.
    """
    sites = state.extensions.get("doctoral_weather_reference_sites")
    if not sites:
        return {}
    due = [p for p in state.planning_projects if p.technology in VRE
           and p.expected_completion_year <= state.year
           and p.outcome not in {"failed", "failed_planning"}]
    if not due:
        return {}
    stock = {name: 0.0 for name in sites}
    for asset in state.assets:
        if asset.technology in VRE and asset.capacity_mw > 0:
            for name, weight in source_weights(asset, sites).items():
                stock[name] += asset.capacity_mw * weight
    result, unassigned = {}, {}
    for p in due:
        if p.extensions.get("weather_assignment_rule") == PROPORTIONAL:
            unassigned.setdefault(p.technology, []).append(p)
            continue
        weights = source_weights(AssetStateV2(p.project_id, p.technology, p.capacity_mw,
                                             extensions=p.extensions), sites)
        result[p.project_id] = {"weather_source_weights": weights, "weather_allocation_year": state.year}
        for name, weight in weights.items():
            stock[name] += p.capacity_mw * weight
    for technology, projects in unassigned.items():
        names = [n for n, s in sites.items() if s["technology"] == technology]
        if not names:
            raise ValueError(f"Missing doctoral weather representatives for {technology}")
        total_stock = sum(stock[n] for n in names)
        total_new = sum(p.capacity_mw for p in projects)
        if total_new <= 0:
            weights = {names[0]: 1.0}
        elif total_stock <= 0:
            weights = {names[0]: 1.0}  # Original first-generator fallback.
        else:
            names.sort()
            remaining, weights = total_new, {}
            for i, name in enumerate(names):
                amount = remaining if i == len(names) - 1 else total_new * (stock[name] / total_stock)
                remaining -= amount
                weights[name] = amount / total_new if amount > 1e-6 else 0.0
        for p in projects:
            result[p.project_id] = {"weather_source_weights": dict(weights),
                "weather_allocation_year": state.year,
                "weather_allocation_basis_mw": {n: stock[n] for n in names},
                "weather_allocation_cohort_mw": total_new}
    return result
