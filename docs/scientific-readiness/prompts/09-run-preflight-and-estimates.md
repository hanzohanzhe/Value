# Prompt 09 — Run preflight and estimates

Act as a modelling-workbench UX engineer. Prevent expensive invalid runs.

## Implement

1. Add one preflight service used by API, CLI and frontend.
2. Check Python/scientific dependencies, project revision, module conformance,
   data-pack validation, parameter relevance, years/periods, output permissions,
   free disk, checkpoint policy and optional export dependencies.
3. Estimate periods, ledger rows, disk use and runtime from declared mode plus
   prior comparable completed runs. Clearly label estimates as estimates.
4. Block only genuine requirements. Present experimental assumptions and optional
   missing capabilities as warnings.
5. Persist the accepted preflight report in the run bundle.

## Tests and acceptance

- API and CLI return identical reports for the same project/mode.
- A run cannot launch after a blocking preflight error.
- Warning-only preflight can launch and is preserved in provenance.
- The UI remains usable by a non-programmer and explains the next corrective action.
