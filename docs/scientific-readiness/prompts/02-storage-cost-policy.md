# Prompt 02 — Replaceable storage-cost policy

Act as a storage economics modeller. Make storage bidding a versioned selected
policy shared by PSM dispatch and storage-expansion appraisal.

## Scientific requirements

- With no observation in the first year, price dynamic recovery using the
  technology's full-utilisation design case.
- In later years allocate annual levelised project cost from the preceding
  year's delivered MWh and sales-weighted dwell time.
- Battery technologies alone receive cycle depreciation. Pumped hydro and
  hydrogen receive none.
- Keep MW, MWh, duration, charge efficiency and discharge efficiency explicit.

## Implement

1. Add a required `storage_cost` module contract and manifests for:
   `dynamic-annual-storage-cost`, `scheme-c-legacy-storage-tariff`, and a safe
   `user-formula-storage-cost`.
2. Inject the selected policy into both the modular Battery and storage cap.
3. The legacy policy must use the data-pack Scheme C `storage_fee + dwell *
   per_storage_fee` tariff without modifying the retained implementation.
4. The user formula accepts only a documented arithmetic expression over
   approved numeric variables; reject calls, attributes, indexing and unknown
   symbols. Never execute arbitrary Python.
5. Add advanced parameters for discount rate, utilisation floor and custom
   formula. Defaults preserve full-utilisation first-year initialisation and the
   thesis previous-year method thereafter.

## Tests and acceptance

- Prove first-year recovery equals annual levelised project cost.
- Prove the following year uses preceding sales and weighted dwell time.
- Prove only batteries receive cycle depreciation.
- Prove legacy bid values exactly equal the original tariff equation.
- Prove valid custom formulas work and malicious/invalid formulas fail before run.
- Prove PSM and storage-cap evidence records the same selected policy.
