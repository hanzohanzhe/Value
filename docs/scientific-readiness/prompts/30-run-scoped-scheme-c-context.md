# Prompt 30 — Run-scoped Scheme C context and explicit canonical inputs

Continue only after Prompt 29 is accepted. Read visibility Prompt 09 and
scientific Prompts 12, 13 and 14 before editing. Audit every mutation of
`compat.config`, `os.environ`, current working directory and module-level runtime
state reachable from the website worker. Act as a concurrency and reproducible
scientific-computing architect.

## Objective

Contain the remaining mutable-global compatibility state behind one explicit,
run-scoped boundary. Native public modules must receive typed inputs and canonical
data objects directly; a legacy adapter may temporarily translate that context for
the preserved Scheme C reference process, but no state may leak between runs.

## Non-duplication boundary

- Reuse `ResolvedRun`, `RunInputSnapshot`, the 25 canonical roles, parameter
  registry and provenance schemas. Do not define a third configuration format.
- Prompt 13 already freezes input bytes and Prompt 14 already normalizes adapters;
  consume those outputs rather than re-importing live source files.
- Do not rewrite storage pricing, planning, cost/carbon ledgers or scientific
  equations in this prompt.
- Preserve the retained Scheme C implementation and use a narrow compatibility
  session only where its function signatures still require legacy globals.

## Implement

1. Define an immutable `SchemeCRunContext` (or equivalently named internal type)
   assembled from the accepted `ResolvedRun` and `RunInputSnapshot`. Include run
   and year identity, canonical fleet/demand/weather/import bindings, resolved
   parameters, selected module identities, output/artifact sinks and cancellation
   token. Store references/hashes for large arrays rather than duplicating them.
2. Make public PSM/CEM entry points accept their declared typed contract or this
   internal context explicitly. They must not discover scientific inputs from
   ambient environment variables, current directory or a previously mutated
   module singleton.
3. Implement one allowlisted `LegacyConfigSession` for reference compatibility.
   It must snapshot, apply and restore every mutated config/environment/module
   value in `finally`, reject nesting or cross-run reuse, and emit a complete
   mutation manifest. It is not a public plugin API.
4. Replace the three fixed-name handoffs (`repd-q2-jul-2025.csv`,
   `mechansim cost.xlsx`, `regional_technology_success_rates.csv`) in native
   production with canonical adapter outputs. If the reference runner still
   requires names, stage them only inside its isolated run directory and record
   the mapping.
5. Remove production dependence on `os.chdir`. Resolve artifacts and input objects
   from explicit run roots. A reference-only subprocess may use a private working
   directory if it is declared and cannot affect the parent process.
6. Add a source-level allowlist for remaining global mutations. Every allowlisted
   occurrence must name its owner-removal prompt; undeclared new occurrences fail
   CI.

## Tests and acceptance

- Run projects A then B and B then A in one interpreter; each result and identity
  is order-independent.
- Inject a failure halfway through context binding; globals, environment and
  working directory are restored exactly.
- Concurrent native runs with different weather, demand, modules and parameters
  cannot observe one another's state.
- A module test proves every scientific input it reads is reachable from its typed
  arguments/snapshot, not a live project or desktop file.
- Checkpoint/resume recreates the same context hash and refuses a changed context.
- Retained-source hashes, two-period results and the accepted reference comparison
  remain unchanged.

## Stop condition

If a native production module still requires an undeclared mutable global or a
source-specific filename, leave the context-isolation gate failed and list the
first read site. Do not hide it behind a broader context object containing the
entire process environment.

## Deliverable

Provide the context schema, old-to-new dependency map, remaining reference-only
mutation allowlist, order/concurrency/failure-restoration tests and provenance
example.
