"""GB interconnector line identity (P0-5a S4; review P6-03).

A boundary flow series belongs to the country of the line it measures, not to
the file name it was saved under.  NESO interconnector flow columns name the
line; this module maps them to VALUE's boundary countries and resolves the
pack's profile bindings by line identity (decision A5: universal).
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

COUNTRIES = ("france", "belgium", "netherlands", "norway", "ireland")
# NESO "interconnector flows" column names -> the country at the other end.
NESO_LINE_COUNTRY = {
    "IFA_FLOW": "france",
    "IFA2_FLOW": "france",
    "ELECLINK_FLOW": "france",
    "NEMO_FLOW": "belgium",
    "BRITNED_FLOW": "netherlands",
    "NSL_FLOW": "norway",
    "MOYLE_FLOW": "ireland",
    "EAST_WEST_FLOW": "ireland",
    "GREENLINK_FLOW": "ireland",
}
# The retained kernel's Connection objects by country (its config names).
KERNEL_CONNECTION_BY_COUNTRY = {
    "france": "Interconnect_France",
    "belgium": "Interconnect_Beligum",
    "netherlands": "Interconnect_Netherland",
    "norway": "Interconnect_Norway",
    "ireland": "Interconnect_Ireland",
}


class BoundaryIdentityError(ValueError):
    code = "GF_DATA_BOUNDARY_IDENTITY"


def header_line_country(path: Path) -> tuple[str | None, str | None]:
    """``(source column, country)`` when the file's first cell names a NESO line."""

    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            first = handle.readline()
    except OSError:
        return None, None
    cells = [cell.strip().strip('"').upper() for cell in first.split(",")]
    for cell in cells:
        if cell in NESO_LINE_COUNTRY:
            return cell, NESO_LINE_COUNTRY[cell]
    return None, None


def resolve_profile_roles(
    pack_root: Path, manifest: Mapping[str, object], path_of: "callable[[str], Path]",
) -> tuple[dict[str, str], list[dict[str, object]]]:
    """``country -> profile role`` by line identity, with the evidence rows.

    A role whose file header names a NESO line is identified; the identified
    roles must be a permutation of their own countries (each identified file
    belongs to one of the identified roles' countries).  Then every
    identified file is used for its line's country.  Anything else (a line
    named twice, or a file naming a country whose role is not identified)
    cannot be resolved and raises ``GF_DATA_BOUNDARY_IDENTITY``.
    """

    del pack_root, manifest
    roles = {country: f"market.{country}.profile" for country in COUNTRIES}
    identified: dict[str, tuple[str, str]] = {}
    for country, role in roles.items():
        column, line_country = header_line_country(path_of(role))
        if line_country is not None:
            identified[country] = (str(column), line_country)
    evidence: list[dict[str, object]] = []
    targets = [line for _column, line in identified.values()]
    if len(set(targets)) != len(targets) or set(targets) != set(identified):
        raise BoundaryIdentityError(
            "GF_DATA_BOUNDARY_IDENTITY: interconnector flow files cannot be resolved by line identity: "
            + ", ".join(f"{roles[country]} -> {column} ({line})" for country, (column, line) in sorted(identified.items()))
        )
    resolved = dict(roles)
    for bound_country, (column, line_country) in sorted(identified.items()):
        resolved[line_country] = roles[bound_country]
        evidence.append({
            "role": roles[bound_country], "source_column": column, "line_country": line_country,
            "rebound": line_country != bound_country,
        })
    return resolved, evidence
