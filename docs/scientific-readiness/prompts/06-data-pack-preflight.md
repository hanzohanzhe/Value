# Prompt 06 — Data-pack adapter validation

Act as a power-system data engineer. Validate imported databases before the PSM
or CEM starts.

## Implement

1. Produce a machine-readable validation report for every semantic binding:
   existence, checksum, format, required columns/keys, units, duplicate IDs,
   missing values, time coverage, timezone, period count and cross references.
2. Keep source-specific column names and transformations in adapters; modules
   consume canonical roles only.
3. Add template metadata and mapping previews suitable for CSV, JSON, NetCDF and
   optional Parquet/SQL adapters.
4. Validate full-year demand/weather alignment and the CEM cost/REPD/planning
   relationships required by selected modules.
5. Expose blocking errors and non-blocking warnings before launch.

## Tests and acceptance

- Small good and bad packs cover missing columns, duplicate IDs, bad units,
  truncated clocks and path escape.
- Validation is bounded: do not load a 600 MB NetCDF dataset merely to count it.
- The installed Scheme C pack passes the selected-module interface gate.
