import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import path from 'node:path';
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { chromiumLaunchOptions } from './helpers/chromium.mjs';

// W4a review (AF-低2): after a new Study is saved, or the edit of a saved Study is
// left, the draft is not reported as unsaved, nothing is stored under its key and
// leaving the page does not ask.  The backend saves a normalised Study (filled
// market_configuration, effective extension parameters), so the as-typed form differs.
const root = path.resolve(import.meta.dirname, '../..');
const PACK = 'value-uk-1000twh-reproduction';
const savedProject = (name, revision) => ({
  id: 'value-uk-transition', name, purpose: '', data_pack_id: PACK, start_year: 2025, end_year: 2034, revision_sha256: revision, revision_number: 1, updated_at: '2026-10-08T00:00:00Z',
  modules: { psm: 'value-bid-at-cost-psm', investment: 'agent-investment', pipeline: 'planning-pipeline', vre_cap: 'vre-expansion-cap', storage_cap: 'value-storage-expansion-policy', transition: 'value-annual-state-transition', storage_cost: 'dynamic-annual-storage-cost' },
  selected_extensions: [], extension_parameters: { 'ext.effective': 1 }, maturity_acknowledgements: {},
  market_configuration: { ahead_market_module_id: 'value-bid-at-cost-psm', balancing_module_id: '', ledger_detail: 'summary', voll_gbp_per_mwh: 17000.0 },
  parameters: {}, runtime_options: { 'runtime.market_trace_level': 'summary' },
});

test('a saved or left Study draft is not reported as unsaved (W4a review, AF-低2)', { timeout: 60000 }, async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-study-draft-')); let server, browser;
  try {
    await build({ entryPoints: [path.join(root, 'tests/frontend/helpers/study-draft-harness.tsx')], bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js'), logLevel: 'silent' });
    await writeFile(path.join(directory, 'index.html'), '<div id="root"></div><script type="module" src="/harness.js"></script>');
    server = createServer(async (req, res) => { const file = req.url === '/harness.js' ? 'harness.js' : 'index.html'; res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html'); res.end(await readFile(path.join(directory, file))); });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch(chromiumLaunchOptions());
    const page = await browser.newPage(); let saved = [], revision = 0;
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/projects') { revision += 1; saved = [savedProject(route.request().postDataJSON().name, `rev-${revision}`)]; await route.fulfill({ json: { project: saved[0] } }); }
      else if (url.pathname === '/api/workspace') await route.fulfill({ json: { projects: saved } });
      else assert.fail(`unexpected request ${url.pathname}`);
    });
    const origin = `http://127.0.0.1:${server.address().port}`;
    const output = (label) => page.getByLabel(label).innerText();
    const stored = () => page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith('value.study-draft.v1:')).sort());
    const leaveAsks = () => page.evaluate(() => { const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented; });
    const settle = async (editing) => { await page.getByLabel('editing').filter({ hasText: editing }).waitFor(); await page.waitForTimeout(150); };

    // Control: the pre-fix flow reports the saved Study as unsaved and stores a phantom draft.
    await page.goto(origin);
    await page.getByLabel('Study name').fill('VALUE UK transition');
    await page.getByRole('button', { name: 'Save (pre-fix)', exact: true }).click(); await settle('value-uk-transition:1');
    assert.equal(await output('dirty'), 'unsaved', 'the control reproduces the reported defect');
    assert.deepEqual(await stored(), ['value.study-draft.v1:value-uk-transition']);
    await page.evaluate(() => localStorage.clear());

    // Fixed save of a new Study: clean, nothing stored, leaving does not ask.
    await page.goto(origin); saved = []; revision = 0;
    await page.getByLabel('Study name').fill('My new Study');
    assert.equal(await output('dirty'), 'unsaved', 'a typed new draft is unsaved');
    assert.equal(await leaveAsks(), true);
    assert.deepEqual(await stored(), ['value.study-draft.v1:new']);
    await page.getByRole('button', { name: 'Save', exact: true }).click(); await settle('value-uk-transition:1');
    assert.equal(await output('dirty'), 'clean');
    assert.equal(await output('offer'), 'none');
    assert.deepEqual(await stored(), [], 'neither the new-Study draft nor a phantom edit draft is stored');
    assert.equal(await leaveAsks(), false, 'reloading or closing the tab does not ask');

    // A new revision of the edited Study is clean as well.
    await page.getByLabel('Study name').fill('My new Study v2');
    assert.equal(await output('dirty'), 'unsaved');
    assert.deepEqual(await stored(), ['value.study-draft.v1:value-uk-transition']);
    await page.getByRole('button', { name: 'Save', exact: true }).click(); await page.waitForTimeout(300);
    assert.equal(await output('dirty'), 'clean');
    assert.deepEqual(await stored(), []);

    // Leaving the edit (research suite Study, trash of the edited Study): the pre-fix flow turns the loaded Study into a dirty new draft.
    await page.getByRole('button', { name: 'Leave edit (pre-fix)', exact: true }).click(); await settle('new:1');
    assert.equal(await output('dirty'), 'unsaved', 'the control reproduces the reported defect');
    await page.evaluate(() => localStorage.clear());
    await page.goto(origin); saved = []; revision = 0;
    await page.getByRole('button', { name: 'Save', exact: true }).click(); await settle('value-uk-transition:1');
    await page.getByRole('button', { name: 'Leave edit', exact: true }).click(); await settle('new:1');
    assert.equal(await output('dirty'), 'clean');
    assert.equal(await output('offer'), 'none');
    assert.deepEqual(await stored(), []);
    assert.equal(await leaveAsks(), false);
  } finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(directory, { recursive: true, force: true }); }
});
