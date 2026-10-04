"""Review-gated DSO-zone, computational-corridor and ETYS-cut candidate compiler."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable, Mapping, Sequence

from shapely.geometry import LineString, mapping, shape


OVERRIDE_SCHEMA = "value.network-review-overrides/v1"


def _minimum_touching_tree(
    geometries: Mapping[str, object],
) -> list[tuple[str, str]]:
    candidates: list[tuple[int, float, str, str]] = []
    zone_ids = sorted(geometries)
    for index, left_id in enumerate(zone_ids):
        left = geometries[left_id]
        for right_id in zone_ids[index + 1 :]:
            right = geometries[right_id]
            connected = left.touches(right) or left.intersects(right)  # type: ignore[attr-defined]
            if connected:
                distance = left.centroid.distance(right.centroid)  # type: ignore[attr-defined]
            else:
                distance = left.distance(right)  # type: ignore[attr-defined]
            candidates.append((0 if connected else 1, float(distance), left_id, right_id))
    parent = {zone_id: zone_id for zone_id in zone_ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    selected: list[tuple[str, str]] = []
    for _, _, left_id, right_id in sorted(candidates):
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            continue
        parent[right_root] = left_root
        selected.append((left_id, right_id))
    return selected


def _audit_svg(map_ids: Sequence[str]) -> str:
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800">',
        '<g aria-label="VALUE network candidate audit">',
    ]
    for index, map_id in enumerate(map_ids):
        kind = map_id.split(":", 1)[0]
        rows.append(
            f'<g data-kind="{escape(kind)}" data-map-id="{escape(map_id)}" '
            f'transform="translate(20 {20 + index * 18})"><text>{escape(map_id)}</text></g>'
        )
    rows.extend(["</g>", "</svg>"])
    return "\n".join(rows) + "\n"


def compile_review_candidate(
    zone_geojson: Mapping[str, object],
    cut_proposals: Sequence[Mapping[str, object]],
    review_overrides: Mapping[str, object],
) -> dict[str, object]:
    if zone_geojson.get("type") != "FeatureCollection":
        raise ValueError("Network-zone candidate must be a GeoJSON FeatureCollection")
    if review_overrides.get("schema_version") != OVERRIDE_SCHEMA:
        raise ValueError("Network review override uses an incompatible schema")
    geometries: dict[str, object] = {}
    zone_rows: list[dict[str, object]] = []
    zone_features: list[Mapping[str, object]] = []
    for raw in zone_geojson.get("features", []):  # type: ignore[assignment]
        if not isinstance(raw, Mapping) or not isinstance(raw.get("properties"), Mapping):
            raise ValueError("Network-zone feature is invalid")
        props = raw["properties"]
        zone_id = str(props.get("zone_id") or "")
        parent = str(props.get("dso_parent_zone_id") or "")
        if not zone_id or zone_id in geometries or not parent:
            raise ValueError("Every network zone requires a unique ID and one DSO parent")
        geometry = shape(raw.get("geometry"))
        if geometry.is_empty:
            raise ValueError(f"Network zone {zone_id} has empty geometry")
        geometries[zone_id] = geometry
        zone_rows.append(
            {
                "zone_id": zone_id,
                "dso_parent_zone_id": parent,
                "display_name": str(props.get("display_name") or zone_id),
            }
        )
        zone_features.append(raw)
    zone_rows.sort(key=lambda row: str(row["zone_id"]))
    zone_ids = set(geometries)
    corridor_pairs = _minimum_touching_tree(geometries)
    corridors = []
    inferred_gap_bridges: list[str] = []
    for left, right in corridor_pairs:
        corridor_id = f"corridor:{left}--{right}"
        connected = geometries[left].touches(geometries[right]) or geometries[left].intersects(geometries[right])  # type: ignore[attr-defined]
        row = {
            "corridor_id": corridor_id,
            "from_zone_id": left,
            "to_zone_id": right,
            "positive_direction": "from_to_positive",
            "purpose": "computational_routing",
        }
        if not connected:
            row["connection_method"] = "nearest_geometry_gap_bridge"
            inferred_gap_bridges.append(corridor_id)
        corridors.append(row)

    decisions: dict[str, Mapping[str, object]] = {}
    for raw in review_overrides.get("decisions", []):  # type: ignore[assignment]
        if not isinstance(raw, Mapping):
            raise ValueError("Network review decision is invalid")
        boundary_id = str(raw.get("boundary_id") or "")
        if not boundary_id or boundary_id in decisions:
            raise ValueError("Network review decisions have blank or duplicate boundary IDs")
        decisions[boundary_id] = raw

    accepted: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    known_boundaries: set[str] = set()
    for proposal in sorted(cut_proposals, key=lambda row: str(row.get("boundary_id"))):
        boundary_id = str(proposal.get("boundary_id") or "")
        if not boundary_id or boundary_id in known_boundaries:
            raise ValueError("Cut proposals have blank or duplicate boundary IDs")
        known_boundaries.add(boundary_id)
        positive = {str(item) for item in proposal.get("positive_zone_ids", [])}  # type: ignore[arg-type]
        negative = {str(item) for item in proposal.get("negative_zone_ids", [])}  # type: ignore[arg-type]
        if positive & negative or positive | negative != zone_ids:
            raise ValueError(f"Cut proposal {boundary_id} does not partition all network zones")
        members: list[dict[str, object]] = []
        for corridor in corridors:
            left = str(corridor["from_zone_id"])
            right = str(corridor["to_zone_id"])
            if left in positive and right in negative:
                members.append({"corridor_id": corridor["corridor_id"], "coefficient": 1})
            elif left in negative and right in positive:
                members.append({"corridor_id": corridor["corridor_id"], "coefficient": -1})
        decision = decisions.get(boundary_id)
        if decision is None:
            unresolved.append(
                {"boundary_id": boundary_id, "status": "needs_mapping", "proposed_members": members}
            )
            continue
        status = str(decision.get("decision") or "")
        if status == "excluded":
            excluded.append(
                {"boundary_id": boundary_id, "status": "excluded", "approval": dict(decision)}
            )
            continue
        if status != "accepted" or not str(decision.get("approved_by") or ""):
            raise ValueError(f"Cut {boundary_id} has an invalid approval decision")
        if not members:
            raise ValueError(f"Accepted cut {boundary_id} has no computational corridor members")
        expected = decision.get("expected_members")
        if expected is not None and list(expected) != members:  # type: ignore[arg-type]
            raise ValueError(f"Cut {boundary_id} proposed incidence differs from approved membership")
        accepted.append(
            {
                "boundary_id": boundary_id,
                "members": members,
                "positive_zone_ids": sorted(positive),
                "negative_zone_ids": sorted(negative),
                "approval": dict(decision),
            }
        )

    corridor_features = [
        {
            "type": "Feature",
            "properties": {"map_id": f"corridor:{row['corridor_id']}", **row},
            "geometry": mapping(
                LineString(
                    [
                        geometries[str(row["from_zone_id"])].centroid,
                        geometries[str(row["to_zone_id"])].centroid,
                    ]
                )
            ),
        }
        for row in corridors
    ]
    map_ids = [f"zone:{row['zone_id']}" for row in zone_rows] + [
        f"corridor:{row['corridor_id']}" for row in corridors
    ]
    return {
        "schema_version": "value.gb-zonal-review-candidate/v1",
        "network_zones": zone_rows,
        "corridors": corridors,
        "accepted_cutsets": accepted,
        "excluded_cutsets": excluded,
        "unresolved_cutsets": unresolved,
        "blocking_reasons": [
            f"cutset.{row['boundary_id']}.needs_mapping" for row in unresolved
        ],
        "map_ids": map_ids,
        "audit_geojson": {
            "type": "FeatureCollection",
            "features": list(zone_features) + corridor_features,
        },
        "audit_svg": _audit_svg(map_ids),
        "corridor_semantics": "computational_routing_not_physical_circuits",
        "inferred_gap_bridges": inferred_gap_bridges,
    }


def build_prompt98_candidate(
    source_inventory: Path,
    output_root: Path,
    *,
    implementation: Callable[[Path, Path], dict[str, object]],
) -> dict[str, object]:
    """Compatibility owner for the existing Prompt 98 offline builder."""

    return implementation(source_inventory, output_root)
