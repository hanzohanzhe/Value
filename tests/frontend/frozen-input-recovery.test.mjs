import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import path from 'node:path';
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { chromiumLaunchOptions } from './helpers/chromium.mjs';
const root = path.resolve(import.meta.dirname, '../..'), sha = 'a'.repeat(64);
const report = (run, mode) => ({ schema_version: 'value.frozen-recovery-review/v1', source_run_id: run, source_snapshot_id: 'snapshot-1', recovery_mode: mode, review_sha256: sha, allowed: true, input_integrity: 'verified', scope: { mode: 'smoke', start_year: 2025, end_year: 2025, periods_per_year: 2 }, canonical_role_count: 2, source_execution_identity_sha256: null, current_execution_identity_sha256: sha, missing_evidence: ['Historical source not bundled'], changes: [{ field: 'method', recorded: null, current: 'current' }], blocking_reasons: [], limitations: ['Input recovery does not restore checkpoints'] });
test('frozen recovery discards late reviews across mode/Run and creates only an explicitly confirmed Study', { timeout: 45000 }, async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-frozen-ui-')); let server, browser;
  try {
    await build({ stdin: { contents: `import React,{useState}from'react';import{createRoot}from'react-dom/client';import Panel from './app/features/workspace/FrozenInputRecoveryPanel';function Harness(){const[run,setRun]=useState('run-a');const[created,setCreated]=useState('');return <><button onClick={()=>setRun(run==='run-a'?'run-b':'run-a')}>Switch Run</button><output aria-label="created Study">{created}</output><Panel runId={run} onStudyCreated={(id,mode)=>setCreated(id+':'+mode)}/></>};createRoot(document.getElementById('root')).render(<Harness/>);`, resolveDir: root, loader: 'tsx' }, bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js') });
    await writeFile(path.join(directory, 'index.html'), '<div id="root"></div><script type="module" src="/harness.js"></script>');
    server = createServer(async (req, res) => { const file = req.url === '/harness.js' ? 'harness.js' : 'index.html'; res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html'); res.end(await readFile(path.join(directory, file))); });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch(chromiumLaunchOptions());
    const page = await browser.newPage(); let pending, delayed = true, creates = 0;
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url()), run = url.pathname.split('/')[3], body = route.request().postDataJSON();
      if (url.pathname.endsWith('/review')) { if (delayed) { pending = { route, response: report(run, body.recovery_mode) }; return; } await route.fulfill({ json: report(run, body.recovery_mode) }); }
      else if (url.pathname.endsWith('/frozen-recovery')) { creates++; assert.deepEqual(body, { recovery_mode: 'migration', review_sha256: sha, name: 'Recovered inputs', acknowledge: true }); await route.fulfill({ json: { schema_version: 'value.frozen-recovery-created/v1', source_run_id: run, source_snapshot_id: 'snapshot-1', project: { id: 'independent-study', name: body.name }, run_started: false, mode: 'smoke' } }); }
      else assert.fail('Component must never call readiness or launch endpoints');
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const review = page.getByRole('button', { name: '核对冻结输入与执行身份' }), save = page.getByRole('button', { name: '确认创建独立 Study' });
    const waitPending = async () => { const deadline = Date.now() + 5000; while (!pending && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10)); assert.ok(pending); };
    await review.click(); await waitPending(); await page.getByLabel('核对方式').selectOption('migration'); await pending.route.fulfill({ json: pending.response }).catch(() => {}); pending = null;
    assert.equal(await save.count(), 0);
    await review.click(); await waitPending(); await page.getByRole('button', { name: 'Switch Run' }).click(); await pending.route.fulfill({ json: pending.response }).catch(() => {}); pending = null;
    assert.equal(await save.count(), 0); await page.getByRole('button', { name: 'Switch Run' }).click(); assert.equal(await save.count(), 0);
    delayed = false; await page.getByLabel('核对方式').selectOption('migration'); await review.click(); await save.waitFor();
    assert.equal(await save.isEnabled(), false); assert.equal(creates, 0);
    await page.getByLabel('新 Study 名称').fill('Recovered inputs'); await page.getByRole('checkbox').check(); await save.click();
    await page.getByLabel('created Study').filter({ hasText: 'independent-study:smoke' }).waitFor(); assert.equal(creates, 1); assert.equal(await save.count(), 0);
  } finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(directory, { recursive: true, force: true }); }
});
