# Prompt 08 — Run API, planning results and on-demand audit UI

Continue from accepted Prompts 01-07. Act as a senior frontend engineer with
scientific-data UX experience. Keep the application in English as requested by the
project owner.

## Objective

Expose the real orchestrator lifecycle, editable advanced settings, planning
evolution and on-demand market evidence without turning the main Run centre into a
debug console.

## Mandatory constraints

- UI module lists, parameter fields and lifecycle labels must be generated from the
  same backend manifests/contracts used for execution.
- Never load a full annual market or planning table in `/api/workspace`,
  `status.json` or the initial Run-centre render.
- Use pagination and fetch details only when a user opens them.
- Do not show two-period smoke economics as annual results.
- Do not expose unnecessary storage pricing internals on the main result card.

## Work

1. Add API endpoints for:
   - module manifests/capabilities;
   - parameter schemas and effective-parameter preview;
   - planning annual summary;
   - paginated planning projects/events;
   - period summaries;
   - paginated market orders;
   - artifacts and provenance.
2. Add safe run-relative artifact access. Prevent arbitrary path traversal.
3. Generate an `Advanced settings` section from the parameter schema, grouped into
   Planning, Expansion, Market experiment and Output/runtime. Show units, defaults,
   descriptions, bounds and whether a value is fixed, Data Pack-derived or
   overridden.
4. Correct the overview and Run-centre lifecycle to show planning advance before
   PSM and planning admission after investment.
5. Extend each annual result with a collapsed `Planning pipeline` panel showing:
   active/commissioned/failed counts and MW, next completions, stage, technology and
   region breakdowns.
6. Add a paginated project table with search/filter and location or region. Clearly
   display failure/exclusion reason. A map is optional and must not delay the table.
7. Add an `Audit` view opened on demand. It shows one selected year/period summary,
   then the bid/order table if full tracing exists. Explain when the selected run
   contains summary-only tracing.
8. Add artifact download links and run provenance without exposing absolute local
   filesystem paths.
9. Maintain keyboard accessibility, responsive layout, loading/empty/error states
   and English copy.

## Tests

- API pagination, filtering and path-safety tests.
- TypeScript contract/build checks.
- Rendered-page tests for planning summary, failures, advanced settings and audit
  empty/full states.
- Verify initial workspace/status payload size stays bounded when ledger size grows.
- Browser smoke test against a fixture run if the local service is available.
- Retained-source hash test.

## Deliverable

Describe the user flow, include screenshots if practical, report payload sizes and
prove every displayed module/parameter maps to the executed backend contract.
