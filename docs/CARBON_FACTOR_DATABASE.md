# Carbon factor database

GridForm stores carbon evidence in a small, local SQLite database while keeping
the human-reviewable CSV seeds beside it. The database does **not** overwrite or
reinterpret the retained Scheme C source. It separates three historical
reproduction datasets from two researched reference catalogues.

## Files

- `gridform_core/data/carbon/gridform_carbon_factors.sqlite` is the queryable
  database.
- `datasets.csv`, `sources.csv`, `factor_catalog.csv` and
  `methodology_rules.csv` are the reviewable source of truth used to build it.
- `legacy_postprocessor_snapshot.csv` is a line-ending-normalised copy of the
  factor file used by the paper postprocessor.
- `snapshot_manifest.json` fingerprints the original thesis, Scheme C config,
  postprocessor CSV and postprocessor code.
- `schema.sql` defines the SQLite contract.
- `scripts/build_carbon_factor_database.py` rebuilds the database atomically.

Rebuild with:

```powershell
py -3.10 scripts\build_carbon_factor_database.py
```

## Dataset boundaries

| Dataset | Purpose | May be silently substituted? |
| --- | --- | --- |
| `scheme_c_2026_07_18` | Literal values in retained Scheme C | No |
| `chapter4_thesis_2026_08_03` | Literal Chapter 4 tables | No |
| `paper_postprocess_2026_07_10` | Exact inputs to the overall-carbon chart | No |
| `uk_authority_reference_2026_08_06` | Audited operational, lifecycle and battery references | No; select a variant |
| `uk_transmission_reference_2026_08_06` | Future network material/equipment references | No; current PSM has no transmission model |

The first three datasets are immutable reproduction snapshots. A correction is
made by adding a new version, never by editing the old scientific result. The
reference catalogue is not a universal default: for example, UNECE has several
PV chemistries and mounting types and two materially different hydro cases.

## What the audit found

1. Scheme C's CCGT, OCGT and biomass values of 394, 651 and 120 kg/MWh match
   NESO's operational methodology. Its France, Netherlands, Belgium and Ireland
   import fallbacks also match NESO. Norway's 100 kg/MWh does not appear in that
   fallback table and remains a reproduction-only assumption.
2. NESO's zero factors for wind, solar, hydro, nuclear and pumped storage mean
   zero **direct generation** emissions. They do not mean zero lifecycle
   emissions. NESO explicitly excludes upstream and indirect GHG from this
   operational forecast boundary.
3. Scheme C's storage `carbon_emission` values 40/50 have no declared physical
   unit. The retained loop adds the scalar to energy-weighted emissions. The
   database therefore labels them `legacy_model_scalar`, not kg/MWh.
4. The paper postprocessor's selected 40/18/20 g/kWh values for solar, offshore
   wind and hydro are modelling representatives. They are not literal unique
   rows in UNECE Table 13. The database preserves them for chart reproduction
   and separately stores the original UNECE variants.
5. The thesis text states 1,394 tCO2e/MW for solar; the file actually used by the
   postprocessor contains 1,349 tCO2e/MW. Both facts are recorded and the
   postprocessor value is not silently changed.
6. Chapter 4 references 164 and 166 appear transposed between compressed-air
   and lithium-ion storage. Those table values remain in the snapshot but are
   flagged for source re-verification.

## Source hierarchy

### Operational generation and imports

Use the [NESO Carbon Intensity methodology](https://www.neso.energy/data-portal/regional-carbon-intensity-forecast)
for dispatch-weighted operational accounting. It covers large metered power
stations, imports and network losses and describes daily generation-mix-derived
interconnector factors. Static country values are fallbacks, not a ten-year
forecast of each exporting system.

The underlying GB fleet methodology is also documented by Staffell,
[*Measuring the progress and impacts of decarbonising British electricity*](https://doi.org/10.1016/j.enpol.2016.12.037).

### Generation equipment lifecycle emissions

The [UNECE Life Cycle Assessment of Electricity Generation Options](https://unece.org/sed/documents/2021/10/reports/life-cycle-assessment-electricity-generation-options)
is used for original European technology rows. The catalogue stores, rather
than averages away, poly-Si/CdTe/CIGS PV, concrete/steel offshore foundations,
two hydro cases, onshore wind, nuclear and NGCC.

[DESNZ Electricity Generation Costs 2023](https://www.gov.uk/government/publications/electricity-generation-costs-2023)
supplies the Chapter 4-compatible 2025 load-factor and operating-life
assumptions: 45%/25 years for onshore wind, 11%/35 years for solar and 61%/30
years for offshore wind. DESNZ does **not** publish an embodied-carbon inventory
in that report. A derived annual capacity factor is therefore labelled as a
UNECE lifecycle row combined with a DESNZ technical assumption, not a “DESNZ
embodied-carbon factor”.

### Storage equipment

The DESNZ/BEIS
[storage cost and technical assumptions report](https://www.gov.uk/government/publications/storage-cost-and-technical-assumptions-for-electricity-storage-technologies)
is useful for engineering and cost data but does not supply the required
lifecycle-carbon inventory.

For lithium-ion BESS sensitivity cases, the database therefore records evidence
used in UK examined projects:

- the [Longfield Solar Farm environmental statement](https://nsip-documents.planninginspectorate.gov.uk/published-documents/EN010118-000163-6-1_ES_Chapter_6___Clima.pdf)
  reports a literature range of 59-119 kgCO2e/kWh of energy capacity and applies
  the midpoint 89;
- the [Cottam Solar Project environmental statement](https://nsip-documents.planninginspectorate.gov.uk/published-documents/EN010133-001025-C6.2.7_A%20ES%20Chapter%207_Climate%20Change_Revision%20A.pdf)
  applies a supplier-informed 100 kgCO2e/kWh realistic-worst-case assumption.

These are applicant assessments held in the statutory Planning Inspectorate
repository, not national DESNZ defaults. Battery chemistry, manufacturing
location, duration, life and replacement schedule must remain explicit.
Pumped-hydro, compressed-air, thermal and hydrogen values from Chapter 4 remain
in the reproduction snapshot until their technology-specific primary studies
are normalised to a common lifecycle boundary.

### Transmission

The present GridForm PSM is a single-node model and has no transmission asset or
loss state. Transmission rows are consequently inactive. The
[Morgan and Morecambe transmission GHG assessment](https://nsip-documents.planninginspectorate.gov.uk/published-documents/EN020032-000542-F.4.1.1_MMTA_ES_Greenhouse%20gas%20assessment.pdf)
provides a useful future template: 2,190 kgCO2e/MW for substation manufacturing,
545 kgCO2e/m2 for substation buildings, and material factors for copper, lead,
steel, UPVC, HDPE and concrete. The Cottam assessment adds an aluminium cable
factor. These values require project-specific material quantities; they are not
presented as a universal “tCO2e per kilometre” line factor.

Operational network emissions should be calculated from time-specific losses
multiplied by the contemporaneous generation-mix intensity. That rule cannot be
activated until a network and loss model exists.

## Safe query examples

Python refuses an ambiguous request instead of choosing a hidden average:

```python
from gridform_core.carbon_factors import CarbonFactorDatabase

db = CarbonFactorDatabase()
factor = db.get_unique(
    dataset_id="uk_authority_reference_2026_08_06",
    technology="solar",
    factor_kind="lifecycle_intensity",
    variant="UNECE_polySi_ground",
)
print(factor.value, factor.unit, factor.source_url)
```

The same catalogue can be inspected with SQLite:

```sql
SELECT technology, variant, value, unit, lifecycle_scope, source_title
FROM factor_records
WHERE dataset_id = 'uk_authority_reference_2026_08_06'
ORDER BY technology, variant;
```

## Integration rule for the future carbon ledger

A project must pin a dataset ID, factor record ID and factor boundary in its
immutable input snapshot. Operational emissions, equipment embodied emissions,
import emissions, storage charging emissions and (later) network losses should
be separate ledger categories. Full lifecycle g/kWh values must not be added to
direct operational factors for the same MWh, because that double-counts the
operational stage.
