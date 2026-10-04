# Uploadable PSM module example

This package is the executable companion to the Module Developer 101 in
[`English`](../../docs/MODULE_DEVELOPER_101.md) and
[`Chinese`](../../docs/MODULE_DEVELOPER_101_ZH.md).
It demonstrates the real `value.psm/v2` runtime path: thermal resources offer
90% of their physical availability and the public perfect-foresight LP clears
the resulting single-node chronology.

It is deliberately labelled **tutorial only, not a scientific baseline**. It
demonstrates a quantity-offer policy, not the sequential VALUE auction. The
physical marginal costs are left unchanged, so market behaviour is not silently
counted as extra physical system cost.

Build the deterministic uploadable ZIP from the VALUE repository root:

```powershell
py -3.10 scripts\build_module_bundle.py `
  --manifest examples\external_psm_bundle\value-module.json `
  --source-root examples\external_psm_bundle\src `
  --license LICENSE `
  --readme examples\external_psm_bundle\README.md `
  --output work\example-thermal-quantity-offer-psm.zip
```

Then open **Modules → Install a model module**, select the ZIP, acknowledge the
trusted-Python boundary, and install it. Create a Study and select **Example
thermal quantity-offer PSM** in the PSM slot. The Storage Cost selector is hidden
because this tutorial delegates storage to central perfect-foresight
co-optimization.

Before writing a paper with a derivative module:

1. replace the example ID, package name and scientific version;
2. document the information available to agents when offers are formed;
3. keep offer prices, settlement payments and physical resource costs separate;
4. add constraint, accounting, regression and independent-oracle tests;
5. run wiring, 24/168-hour, full-year and multi-year validation as appropriate.

## VRE curtailment attribution capability

This tutorial module deliberately does **not** declare
`evidence.vre-counterfactual-snapshot/v1`: it is a single-node,
perfect-foresight PSM and does not create the three matched dispatch cases.
It can still be built, installed and run. Its result will simply report VRE
curtailment attribution as unavailable, with reason code
`module_does_not_provide_counterfactual_snapshot`.

An external staged PSM may declare that capability only when it produces a
`value.vre-counterfactual-snapshot/v1` payload from matching perfect-forecast
copperplate, realised-copperplate and final-zonal dispatches. The selected
balancing module must also produce `network.zonal-redispatch-result/v1`; VALUE
does not infer the claim from module names or partial output.

All fields ending in `_mwh` in the following complete payload use MWh for the
same half-hour period. `realised_input_sha256` is a lowercase SHA-256, and the
zone and tranche IDs are stable identifiers owned by the module author.

```json
{
  "schema": "value.vre-counterfactual-snapshot/v1",
  "run_id": "external-zonal-demo-2025",
  "year": 2025,
  "period": 17,
  "period_id": "2025:17",
  "realised_input_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "module_identities": {
    "psm": "external-staged-psm@1.0.0",
    "balancing": "external-zonal-balancing@1.0.0"
  },
  "rows": [
    {
      "asset_id": "solar-east-01",
      "owner_id": "owner-solar-east",
      "canonical_technology": "Solar",
      "zone_id": "east-england",
      "bid_tranche_id": "vre-solar-7f9f0a7ab34af4c2fba1e06dd418a4dbfbb41a4f67bb53c6c11a83f4b7db2f94",
      "realised_available_vre_mwh": 12.0,
      "perfect_forecast_copperplate_dispatch_mwh": 10.0,
      "realised_copperplate_dispatch_mwh": 9.0,
      "zonal_final_dispatch_mwh": 8.0
    },
    {
      "asset_id": "onshore-north-01",
      "owner_id": "owner-onshore-north",
      "canonical_technology": "Onshore wind",
      "zone_id": "north-east",
      "bid_tranche_id": "vre-onshore-wind-b5606d52244a9eb2bc6b2f7fbde769f04052e97b5f22ea9f7999ca5eb571efc0",
      "realised_available_vre_mwh": 15.0,
      "perfect_forecast_copperplate_dispatch_mwh": 14.0,
      "realised_copperplate_dispatch_mwh": 13.0,
      "zonal_final_dispatch_mwh": 11.0
    },
    {
      "asset_id": "offshore-east-01",
      "owner_id": "owner-offshore-east",
      "canonical_technology": "Offshore wind",
      "zone_id": "east-england",
      "bid_tranche_id": "vre-offshore-wind-0bea526261091669aa5a6f9b9de403954a1cbd73524f8f6f5f453957a69f9c4b",
      "realised_available_vre_mwh": 20.0,
      "perfect_forecast_copperplate_dispatch_mwh": 19.0,
      "realised_copperplate_dispatch_mwh": 18.0,
      "zonal_final_dispatch_mwh": 16.0
    }
  ]
}
```
