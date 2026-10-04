import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) => readFile(new URL(path, import.meta.url), "utf8").catch(() => "");

test("Study trace selection and readiness render frozen VALUE evidence", async () => {
  const [page, traceNotice, composer, readiness] = await Promise.all([
    source("../app/page.tsx"),
    source("../app/features/market/TraceCoverageNotice.tsx"),
    source("../app/features/studies/StudyComposer.tsx"),
    source("../app/features/evidence/ReadinessEvidence.tsx"),
  ]);
  const renderedSource = `${page}\n${traceNotice}\n${composer}\n${readiness}`;

  assert.match(page, /runtime\.market_trace_level/);
  assert.match(renderedSource, /Summary/);
  assert.match(renderedSource, /Full market replay/);
  assert.match(renderedSource, /Advanced: Off/);
  assert.match(renderedSource, /Estimated persisted output/);
  assert.match(renderedSource, /Temporary space/);
  assert.match(renderedSource, /Free-space reserve/);
  assert.match(renderedSource, /Recorded trace/);
  assert.match(renderedSource, /Observed free space/);
  assert.match(renderedSource, /Runtime basis/);
  assert.match(readiness, /project\.solver_contract\.contract_version/);
  assert.doesNotMatch(page, /project\.solver_contract\.solver_contract_version/);
  assert.doesNotMatch(page, /Data pack manifest \/ frozen data SHA-256/);
  assert.doesNotMatch(page, /bound into the frozen data fingerprint/);
});

test("summary results describe missing bid evidence and only offer a new Study revision", async () => {
  const [page, traceNotice] = await Promise.all([
    source("../app/page.tsx"),
    source("../app/features/market/TraceCoverageNotice.tsx"),
  ]);
  const renderedSource = `${page}\n${traceNotice}`;

  assert.match(renderedSource, /Bid-level replay was not recorded/);
  assert.match(renderedSource, /Create a new Study revision/);
  assert.doesNotMatch(renderedSource, /automatically rerun|mutate the completed Study/i);
});

test("market and network result requests expose year, window and page bounds", async () => {
  const [page, networkView, networkClient] = await Promise.all([
    source("../app/page.tsx"),
    source("../app/features/network/NetworkRedispatchView.tsx"),
    source("../app/features/network/networkRedispatch.ts"),
  ]);
  const network = `${networkView}\n${networkClient}`;

  for (const contract of [/period_from/, /period_to/, /limit/, /offset/]) {
    assert.match(page, contract);
    assert.match(network, contract);
  }
  assert.match(page, /Previous window/);
  assert.match(page, /Next window/);
  assert.match(network, /Previous period page/);
  assert.match(network, /Next period page/);
});

test("replay exports use one explicit range and poll only the created job", async () => {
  const [page, panel, network] = await Promise.all([
    source("../app/page.tsx"),
    source("../app/features/market/ReplayExportPanel.tsx"),
    source("../app/features/network/NetworkRedispatchView.tsx"),
  ]);

  for (const range of ["period", "24_hours", "168_hours", "year", "complete"]) {
    assert.match(panel, new RegExp(`value=["']${range}["']`));
  }
  assert.match(panel, /\/replay-exports/);
  assert.match(panel, /status_url/);
  assert.match(panel, /status_url:\s*current\?\.status_url/);
  assert.match(panel, /download_url/);
  assert.match(panel, /queued|running/);
  assert.match(panel, /useState\(initialYear\)/);
  assert.doesNotMatch(panel, /setYear\(initialYear\)/);
  assert.match(page, /key=\{`\$\{run\.id\}-\$\{year\}-\$\{period\}`\}/);
  assert.match(network, /key=\{`\$\{run\.id\}-\$\{year\}-\$\{period\}`\}/);
  assert.doesNotMatch(panel, /staged-market\.jsonl/);
  assert.doesNotMatch(network, /href=\{`\$\{base\}\/export\?view=resource&format=jsonl`\}/);
});

test("replay export controls invalidate stale artifacts and lock one immutable request", async () => {
  const panel = await source("../app/features/market/ReplayExportPanel.tsx");

  assert.match(panel, /type ExportRequest =/);
  assert.match(panel, /request:\s*ExportRequest/);
  assert.match(panel, /const controlsLocked = submitting \|\|/);
  assert.match(panel, /function resetJobEvidence\(\)[\s\S]*setJob\(null\)[\s\S]*setError\(""\)/);
  assert.ok((panel.match(/resetJobEvidence\(\)/g) ?? []).length >= 5);
  assert.ok((panel.match(/disabled=\{controlsLocked/g) ?? []).length >= 5);
  assert.match(panel, /status_url:\s*current\?\.status_url,\s*request:\s*current\.request/);
});

test("Audit summary bid evidence only creates an unsaved Full replay Study revision", async () => {
  const [page, audit] = await Promise.all([source("../app/page.tsx"),source("../app/features/evidence/AuditView.tsx")]);

  assert.doesNotMatch(`${page}\n${audit}`, /Re-run with <code>runtime\.market_trace_level = full<\/code>/);
  assert.match(audit, /function AuditView\(\{ run, apiOrigin, onCreateFullReplayRevision \}/);
  assert.match(audit, /<TraceCoverageNotice traceLevel=\{periods\.trace_level \?\? "summary"\} bidReplayAvailable=\{false\} onCreateFullReplayRevision=\{onCreateFullReplayRevision\}/);
  assert.match(page, /<AuditView run=\{selectedRun\} apiOrigin=\{API_ORIGIN\} onCreateFullReplayRevision=\{createFullReplayRevision\}/);
});

test("GBP1 policy reads historical evidence and upgrades a draft only by explicit action", async () => {
  const ts = await import("typescript");
  const transpile = (code) => ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  const url = (code) => `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
  const networkUrl = url(transpile(await source("../app/features/network/networkRedispatch.ts")));
  const network = await import(networkUrl);
  const contractCode = transpile(await source("../app/features/studies/solverContract.ts")).replace("../network/networkRedispatch",networkUrl);
  const policy = await import(url(contractCode));
  const summary = {schema_version:"value.solver-validation-summary/v1",annual_status:"GO",study_status:"GO",solver_validated:true,solver_stack_validation_status:"builtin_validated_baseline",inherited_unvalidated:false,first_causal_period:null,row_count:1,warning_periods:0,unvalidated_periods:0,maximum_validated_ceiling_use:0,phases:{},evidence_status:"valid",evidence_errors:[],method:"highs-ds",scipy_version:"1.15",highs_identity:"recorded-highs",detail_view:"solver-diagnostics"};
  assert.equal(network.isSolverValidationSummary({...summary,solver_contract_version:"value.zonal-lexicographic/v2"}),true);
  assert.equal(network.isSolverValidationSummary({...summary,solver_contract_version:"value.zonal-lexicographic-gbp1/v3"}),true);
  assert.equal(network.isSolverValidationSummary({...summary,solver_contract_version:"unknown"}),false);
  const current = network.copyDefaultZonalSolverContract();
  const legacy = structuredClone(network.LEGACY_ZONAL_SOLVER_CONTRACT);
  assert.equal(current.validated_ceilings.primary_bid_cost_gbp,1);
  assert.equal(current.absolute_ceilings.primary_bid_cost_gbp,1);
  assert.equal(network.isZonalSolverContract(current),true);
  assert.equal(network.isZonalSolverContract(legacy),true);
  assert.equal(network.isZonalSolverContract({...current,contract_version:legacy.contract_version}),false);
  assert.equal(network.isZonalSolverContract({...current,validated_ceilings:{...current.validated_ceilings,primary_bid_cost_gbp:0.5}}),false);
  const custom = network.withZonalSolverContractFlags({...current, method:"highs-ipm"});
  assert.equal(custom.is_builtin_default,false);
  assert.equal(custom.requires_acknowledgement,true);
  const backToDefault = network.withZonalSolverContractFlags({...custom,method:current.method});
  assert.equal(backToDefault.is_builtin_default,true);
  assert.equal(backToDefault.requires_acknowledgement,false);
  assert.equal(network.isZonalSolverContract(backToDefault),true);
  const draft = { solver_contract:legacy, maturity_acknowledgements:{[policy.LEGACY_ZONAL_SOLVER_ACK_KEY]:policy.ZONAL_SOLVER_ACK,other:"retained"}, modules:{balancing:"value-zonal-redispatch-balancing"} };
  const original = structuredClone(draft);
  assert.deepEqual(policy.alignZonalSolverContract(draft,draft.modules).solver_contract,legacy);
  assert.match(policy.validateZonalSolverContract(legacy),/historical v2/);
  const upgraded = policy.upgradeZonalSolverContract(draft);
  assert.deepEqual(draft,original);
  assert.equal(upgraded.solver_contract.schema_version,"value.network-solver-contract/v3");
  assert.equal(upgraded.maturity_acknowledgements[policy.LEGACY_ZONAL_SOLVER_ACK_KEY],undefined);
  assert.equal(upgraded.maturity_acknowledgements[policy.ZONAL_SOLVER_ACK_KEY],undefined);
  assert.equal(upgraded.maturity_acknowledgements.other,"retained");
  assert.equal(policy.validateZonalSolverContract(upgraded.solver_contract),"");
  const editor = await source("../app/features/studies/SolverSettingsEditor.tsx");
  assert.match(editor,/onClick=\{onUpgrade\}/);
  assert.match(editor,/disabled=\{!useCustom \|\| legacy\}/);
  assert.match(editor,/Fixed at GBP 1 total bid cost/);
});
