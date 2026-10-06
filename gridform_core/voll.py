"""Value of lost load (VoLL) used across VALUE (decision A16-5).

The author's value is 17,000 GBP/MWh (8,500 GBP per MW and half-hour period).
It applies to both methodology profiles:

* the doctoral reproduction profile values unserved energy at this constant
  in its cost accounts.  The thesis code (``case3.py``) used 8,000 GBP/MWh,
  which entered only the cost ledger, never dispatch; replacing it is a
  universal accounting correction (Q12, correction id ``fx5.voll-17000``);
* the corrected profile and every module that reads the scientific parameter
  ``market.voll_gbp_per_mwh`` (default PSM, perfect-foresight LP, reference DC
  network, zonal redispatch, doctoral national PSM) default to it.  The zonal
  VALUE UK study already pinned 17,000.

Historical values are kept here only so that older records can be recognised
and explained; no model path uses them.
"""

from __future__ import annotations

VOLL_GBP_PER_MWH = 17_000.0
CORRECTION_ID = "fx5.voll-17000"

# The thesis cost-ledger constant (runtime_compat/case3.py before FX5).
THESIS_CODE_VOLL_GBP_PER_MWH = 8_000.0
# The registry default of market.voll_gbp_per_mwh before FX5 (0.6.0-alpha.2
# up to the P0 construction).  A saved Study's derived market configuration
# may still carry it although the author never chose it (see
# study_market_config.resolve_market_configuration).
LEGACY_DEFAULT_VOLL_GBP_PER_MWH = 10_000.0
