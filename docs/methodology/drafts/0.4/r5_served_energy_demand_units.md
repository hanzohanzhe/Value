# Energy served, demand units and hourly demand (R5-1 draft for methodology 0.4)

Status: draft written with construction unit R5-1 (2026-10-08), following
decision A28 of `docs/dev/P0_DECISIONS.md` and the four-role swap-data report
(defects S-F-高1, S-F-中2, S-F-中3).

## 1 Energy served (both profiles)

The annual cost ledger divides the CEM system resource cost by the **energy
served**, and the carbon ledger divides emissions by the same quantity:

served = demand − recorded unserved energy (the PSM's blackout) − A2 stress
shortfall booked beyond it (`hidden_unserved_mwh` of the energy-balance ledger).

Before R5-1 only the recorded blackout was deducted, so a stress shortfall that
the PSM did not record as blackout counted as served energy. The rule is a
universal accounting correction (`r5.served-energy-net-of-stress-shortfall`):
it changes the cost per MWh served and the carbon intensity per MWh delivered,
never dispatch, prices or investment. A year without a stress period is
unchanged; the A2 remainder of such a year is numerical noise below the
energy-balance tolerance. Example (GBP1 public1 2025, doctoral profile):
served 232,910,596.5 → 232,831,786.3 MWh (78,810.2 MWh stress shortfall),
cost per MWh served 116.789 → 116.829 GBP/MWh.

Result pages state annual demand, demand served, unserved energy including the
stress shortfall and the PSM-recorded part separately.

## 2 Demand unit

VALUE reads demand as **MW, the average power of each half hour**; energy per
period is MW × 0.5 h. The VALUE 101 teaching demand files carry the header
`mwh` and the pack label `MWh/period`; that label is a known mislabel of these
bytes, which VALUE has always read as MW. The files are not rewritten (both
profiles read them unchanged); the application labels them "read as MW". A
user's replacement series is converted from its declared source unit
(MWh/period ÷ period length in hours = MW). A replacement whose annual energy
differs from the replaced series by more than a factor of 1.5 is flagged with
both annual energies (a warning, not a refusal).

## 3 Hourly demand

A demand series with hourly rows (8,760 or 8,784 rows, or declared timestamps
60 minutes apart) is expanded at import: each hour's MW is used for the two
half-hour periods of that hour, so hourly energy is preserved. A MWh/period
value of an hourly series is energy per hour (= MW). The 8,784-hour leap year
then follows the existing rule (29 February removed, energy rescaled).
