"""Plane-of-array irradiance from horizontal ERA5 irradiance (decision A13, corrected profile only).

The corrected profile converts the horizontal global irradiance (GHI, ERA5
``ssrd`` divided by 3.6e6, i.e. kW m-2 averaged over the source hour) of every
half-hour period into the irradiance on a south-facing plane tilted at the
literature-optimum angle for the site latitude (Jacobson & Jadhav 2018), and only then applies the PV performance ratio (which the
literature defines on plane-of-array irradiance):

1. solar geometry at the period MIDPOINT on the model clock (period ``t`` of a
   365-day UTC year covers ``[t/2, t/2 + 1/2)`` h; day of year
   ``t // 48 + 1``): Spencer (1971) declination, equation of time and
   eccentricity correction, local solar time from the site longitude;
2. decomposition of GHI into diffuse (DHI) and beam (BHI) with the Erbs,
   Klein & Duffie (1982) clearness-index correlation;
3. transposition with the Hay & Davies (1980) anisotropic sky model (beam +
   circumsolar on the beam ratio, the rest isotropic) plus isotropic ground
   reflection with albedo 0.2.

The geometry is evaluated at the period midpoint whatever the source clock: the
weather v2 clock (``p05.weather-time-convention``) already serves each period
the ERA5 accumulation of the hour that contains it (``t // 2 + 1``), so the
midpoint is inside the interval the irradiance was accumulated over.  Below
the zenith cut-off (87 degrees) a period has no beam component and its GHI is
treated as isotropic diffuse, so a horizontal plane (tilt 0) returns GHI
exactly for every period (energy-consistency identity, tested).

Parameters and citations live in ``data/weather/value_uk_vre_loss_factors_v1.json``
(``solar_plane_of_array``).  All angles below are radians unless the name says
``_deg``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

PERIODS_PER_DAY = 48
DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class PlaneOfArrayParameters:
    tilt_rule: str                 # "jacobson-jadhav-2018", "site_latitude" or "fixed"
    fixed_tilt_deg: float | None
    surface_azimuth: str           # "south" (equator-facing in the northern hemisphere)
    albedo: float
    solar_constant_w_m2: float
    max_zenith_deg: float          # beyond this zenith the period carries no beam component
    decomposition: str             # "erbs-1982"
    transposition: str             # "hay-davies-1980"

    @classmethod
    def from_table(cls, block: Mapping[str, Any]) -> "PlaneOfArrayParameters":
        values = {key: block[key] for key in ("tilt_rule", "surface_azimuth", "albedo", "solar_constant_w_m2",
                                              "max_zenith_deg", "decomposition", "transposition")}
        parameters = cls(fixed_tilt_deg=block.get("fixed_tilt_deg"), **values)
        parameters.validate()
        return parameters

    def validate(self) -> None:
        if self.tilt_rule not in TILT_RULES:
            raise ValueError(f"Unknown solar tilt rule {self.tilt_rule!r}")
        if self.tilt_rule == "fixed" and (self.fixed_tilt_deg is None or not 0.0 <= float(self.fixed_tilt_deg) <= 90.0):
            raise ValueError("A fixed solar tilt needs fixed_tilt_deg in [0, 90]")
        if self.surface_azimuth != "south":
            raise ValueError("Only a south-facing plane is implemented")
        if not 0.0 <= float(self.albedo) <= 1.0:
            raise ValueError("Albedo must be in [0, 1]")
        if not 1300.0 <= float(self.solar_constant_w_m2) <= 1400.0:
            raise ValueError("Solar constant out of range")
        if not 80.0 <= float(self.max_zenith_deg) < 90.0:
            raise ValueError("max_zenith_deg must be in [80, 90)")
        if self.decomposition != "erbs-1982" or self.transposition != "hay-davies-1980":
            raise ValueError("Only the Erbs (1982) decomposition and Hay-Davies (1980) transposition are implemented")

    def tilt_deg(self, latitude_deg: float) -> float:
        if self.tilt_rule == "fixed":
            return float(self.fixed_tilt_deg)  # type: ignore[arg-type]
        if self.tilt_rule == "jacobson-jadhav-2018":
            return optimal_tilt_jacobson_jadhav(latitude_deg)
        return abs(float(latitude_deg))


TILT_RULES = ("jacobson-jadhav-2018", "site_latitude", "fixed")


def optimal_tilt_jacobson_jadhav(latitude_deg: float) -> float:
    """Annual-optimal fixed tilt (deg) fitted by Jacobson & Jadhav (2018) for the northern hemisphere.

    theta = 1.3793 + phi (1.2011 + phi (-0.014404 + phi 0.000080509)), phi in
    degrees north (fit range 0-65 N); about 36 deg at 51.5 N.
    """

    phi = float(latitude_deg)
    if not 0.0 <= phi <= 65.0:
        raise ValueError("The Jacobson-Jadhav northern-hemisphere tilt fit covers 0-65 N")
    return 1.3793 + phi * (1.2011 + phi * (-0.014404 + phi * 0.000080509))


# --------------------------------------------------------------------------- geometry

def day_angle(day_of_year: np.ndarray | float) -> np.ndarray:
    """Spencer (1971) day angle Gamma = 2 pi (n - 1) / 365."""

    return 2.0 * np.pi * (np.asarray(day_of_year, dtype=float) - 1.0) / DAYS_PER_YEAR


def declination(day_of_year: np.ndarray | float) -> np.ndarray:
    """Solar declination (rad), Spencer (1971) Fourier series."""

    g = day_angle(day_of_year)
    return (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))


def equation_of_time_minutes(day_of_year: np.ndarray | float) -> np.ndarray:
    """Equation of time (minutes), Spencer (1971) as given by Iqbal (1983)."""

    g = day_angle(day_of_year)
    return 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                     - 0.014615 * np.cos(2 * g) - 0.04089 * np.sin(2 * g))


def eccentricity_factor(day_of_year: np.ndarray | float) -> np.ndarray:
    """(r0 / r)^2, Spencer (1971)."""

    g = day_angle(day_of_year)
    return (1.000110 + 0.034221 * np.cos(g) + 0.001280 * np.sin(g)
            + 0.000719 * np.cos(2 * g) + 0.000077 * np.sin(2 * g))


def hour_angle(utc_hours: np.ndarray | float, longitude_deg: float, day_of_year: np.ndarray | float) -> np.ndarray:
    """Hour angle (rad): 15 degrees per hour from local solar noon; east longitude positive."""

    solar_time = (np.asarray(utc_hours, dtype=float) + float(longitude_deg) / 15.0
                  + equation_of_time_minutes(day_of_year) / 60.0)
    return np.radians(15.0 * (solar_time - 12.0))


def incidence_cosines(latitude_deg: float, decl: np.ndarray | float, omega: np.ndarray | float,
                      tilt_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """(cos zenith, cos incidence on a south-facing plane tilted ``tilt_deg``), Duffie & Beckman eqs 1.6.5/1.6.7.

    Valid for an equator-facing plane in the northern hemisphere (surface
    azimuth 0 measured from south); a tilt of 0 gives cos incidence == cos zenith.
    """

    phi = np.radians(float(latitude_deg))
    beta = np.radians(float(tilt_deg))
    decl = np.asarray(decl, dtype=float)
    omega = np.asarray(omega, dtype=float)
    cos_zenith = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(omega)
    cos_incidence = np.sin(phi - beta) * np.sin(decl) + np.cos(phi - beta) * np.cos(decl) * np.cos(omega)
    return cos_zenith, cos_incidence


def period_clock(periods: int) -> tuple[np.ndarray, np.ndarray]:
    """(day of year 1..365, UTC hour of the period midpoint) of each half-hour period, wrapping yearly."""

    t = np.arange(int(periods))
    day_of_year = (t // PERIODS_PER_DAY) % DAYS_PER_YEAR + 1
    utc_hours = (t % PERIODS_PER_DAY) * 0.5 + 0.25
    return day_of_year, utc_hours


# --------------------------------------------------------------------------- decomposition

def erbs_diffuse_fraction(kt: np.ndarray | float) -> np.ndarray:
    """Diffuse fraction kd(kt), Erbs, Klein & Duffie (1982) hourly correlation."""

    kt = np.asarray(kt, dtype=float)
    middle = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    return np.where(kt <= 0.22, 1.0 - 0.09 * kt, np.where(kt <= 0.80, middle, 0.165))


# --------------------------------------------------------------------------- plane of array

def plane_of_array(ghi_kw_m2: np.ndarray, *, latitude_deg: float, longitude_deg: float,
                   parameters: PlaneOfArrayParameters, tilt_deg: float | None = None,
                   day_of_year: np.ndarray | None = None, utc_hours: np.ndarray | None = None
                   ) -> tuple[np.ndarray, dict[str, Any]]:
    """Per-period plane-of-array irradiance (kW m-2) from per-period GHI (kW m-2).

    ``day_of_year`` / ``utc_hours`` default to the model clock of ``period_clock``.
    Returns the POA array and an evidence summary (annual sums and fractions).
    """

    ghi = np.clip(np.asarray(ghi_kw_m2, dtype=float), 0.0, None)
    if day_of_year is None or utc_hours is None:
        day_of_year, utc_hours = period_clock(len(ghi))
    tilt = parameters.tilt_deg(latitude_deg) if tilt_deg is None else float(tilt_deg)
    decl = declination(day_of_year)
    omega = hour_angle(utc_hours, longitude_deg, day_of_year)
    cos_z, cos_theta = incidence_cosines(latitude_deg, decl, omega, tilt)
    extraterrestrial_normal = parameters.solar_constant_w_m2 / 1000.0 * eccentricity_factor(day_of_year)  # kW m-2
    sun_up = (cos_z > np.cos(np.radians(parameters.max_zenith_deg))) & (ghi > 0.0)
    safe_cos_z = np.where(sun_up, cos_z, 1.0)
    kt = np.where(sun_up, np.clip(ghi / (extraterrestrial_normal * safe_cos_z), 0.0, 1.0), 0.0)
    kd = np.where(sun_up, erbs_diffuse_fraction(kt), 1.0)
    dhi = kd * ghi
    bhi = ghi - dhi                                       # zero whenever the sun is below the cut-off
    dni = np.where(sun_up, bhi / safe_cos_z, 0.0)
    anisotropy = np.where(sun_up, np.clip(dni / extraterrestrial_normal, 0.0, 1.0), 0.0)
    beam_ratio = np.where(sun_up, np.clip(cos_theta, 0.0, None) / safe_cos_z, 0.0)
    cos_beta = np.cos(np.radians(tilt))
    sky_view, ground_view = (1.0 + cos_beta) / 2.0, (1.0 - cos_beta) / 2.0
    beam = bhi * beam_ratio
    sky_diffuse = dhi * (anisotropy * beam_ratio + (1.0 - anisotropy) * sky_view)
    ground = ghi * parameters.albedo * ground_view
    poa = beam + sky_diffuse + ground
    if not np.all(np.isfinite(poa)):
        raise ValueError("Non-finite plane-of-array irradiance")
    ghi_sum = float(ghi.sum())
    evidence = {
        "tilt_deg": tilt, "surface_azimuth": parameters.surface_azimuth,
        "ghi_kwh_m2_per_period_sum": ghi_sum * 0.5, "poa_kwh_m2_per_period_sum": float(poa.sum()) * 0.5,
        "poa_to_ghi_ratio": float(poa.sum()) / ghi_sum if ghi_sum > 0 else None,
        "diffuse_fraction_of_ghi": float(dhi.sum()) / ghi_sum if ghi_sum > 0 else None,
    }
    return poa, evidence
