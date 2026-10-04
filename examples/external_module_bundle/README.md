# Uploadable VALUE module example

This deliberately simple storage offer proves the packaging and execution
contract. It returns GBP 42/MWh and is **not** a scientific baseline.

From the VALUE repository root, build a deterministic uploadable bundle:

```powershell
py -3.10 scripts\build_module_bundle.py `
  --manifest examples\external_module_bundle\value-module.json `
  --source-root examples\external_module_bundle\src `
  --license LICENSE `
  --readme examples\external_module_bundle\README.md `
  --output work\example-flat-storage-offer.zip
```

Open **Modules**, choose the ZIP, acknowledge the executable-code boundary and
select **Install and validate module**. Then create a new Study and select
`Example flat storage offer` in the Storage Cost slot. Run the two-period wiring
check before any longer experiment.

To test a different fixed offer, edit the single `price_gbp_per_mwh` default
from `42.0` to `73.0` in `src/value_example_flat_offer/plugin.py`. Update
manifest and definition `id`, `version`, and `scientific_version` together to
a new identity; leave all lifecycle methods intact. Build and install the ZIP
as above and acknowledge its experimental maturity. Select it in a new derived
Study with an offer-based PSM. The annual storage report identifies
`experimental_fixed_offer`, exposes `fixed_offer_gbp_per_mwh` (73), and records
actual delivered MWh and dwell. The zero cycle/holding compatibility fields
mean this example does not model depreciation or holding cost.

The offer initializes `prepared_year`, accepts annual project parameters,
preserves sales on repeated same-year preparation, records real discharge via
`record_sale`, and carries observations to the next year. Installation checks
exercise this minimal real Battery lifecycle, including non-zero discharge and
report consumption. This establishes runtime wiring, not scientific validity.
