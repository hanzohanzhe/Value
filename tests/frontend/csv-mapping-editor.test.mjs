import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { chromiumLaunchOptions } from './helpers/chromium.mjs';

const root = path.resolve(import.meta.dirname, '../..');
const sha = 'a'.repeat(64), normalized = 'b'.repeat(64), spec = 'c'.repeat(64);
const columns = [{ source: 'load', target: 'value', source_unit: 'MW', target_unit: 'MW' }];
const expires_at = '2099-01-01T00:00:00Z';
const stage = { schema_version: 'value.data-mapping-stage/v1', stage_id: '1'.repeat(32), pack_id: 'copy', role: 'demand.forecast', source_sha256: sha, source_bytes: 7, source_columns: ['load', 'other'], rows: 1, target_manifest_sha256: sha, expires_at };
const review = { schema_version: 'value.data-mapping-review/v1', review_id: '2'.repeat(32), stage_id: stage.stage_id, pack_id: 'copy', role: stage.role, valid: true, errors: [], warnings: [], source_sha256: sha, spec_sha256: spec, normalized_sha256: normalized, target_manifest_sha256: sha, source_bytes: 7, normalized_bytes: 8, rows: 1, columns, sample_rows: [{ value: '10' }], validation: { status: 'passed', time_semantics: 'contract-defined' }, expires_at };
const catalog = (pack_id) => ({ schema_version: 'value.data-mapping-catalog/v1', pack_id, target_manifest_sha256: sha, max_upload_bytes: 33554432, roles: [{ role: stage.role, columns: [{ target: 'value', target_unit: 'MW' }], conversion_pairs: [{ source_unit: 'MW', target_unit: 'MW' }], single_value: false }] });

// Real React component, isolated from the application/server/model lifecycle.
test('CSV mapping requires review confirmation, refreshes only after bound commit, and discards stale reviews', { timeout: 45000 }, async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-csv-ui-'));
  let server, browser;
  try {
    await build({ stdin: { contents: `import React,{useState} from 'react';import{createRoot}from'react-dom/client';import Editor from './app/features/data/CsvMappingEditor';function Harness(){const[pack,setPack]=useState('copy');const[revision,setRevision]=useState('${sha}');const[count,setCount]=useState(0);return <><button onClick={()=>setPack(pack==='copy'?'other':'copy')}>Switch context</button><output aria-label="refresh count">{count}</output><Editor key={pack+revision} packId={pack} manifestSha256={revision} role="demand.forecast" onMapped={result=>{setCount(v=>v+1);setRevision(result.manifest_sha256)}}/></>};createRoot(document.getElementById('root')).render(<Harness/>);`, resolveDir: root, loader: 'tsx' }, bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js') });
    await writeFile(path.join(directory, 'index.html'), '<div id="root"></div><script type="module" src="/harness.js"></script>');
    server = createServer(async (request, response) => { try { const file = request.url === '/harness.js' ? 'harness.js' : 'index.html'; response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html'); response.end(await readFile(path.join(directory, file))); } catch { response.writeHead(500).end(); } });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch(chromiumLaunchOptions());
    const page = await browser.newPage();
    let commitCount = 0, delayReview = false, pending;
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      let payload;
      if (url.pathname.endsWith('/catalog')) payload = catalog(url.pathname.split('/')[3]);
      else if (url.pathname.endsWith('/stages')) { assert.equal(url.searchParams.get('role'), stage.role); assert.equal(route.request().headers()['x-expected-pack-revision'], sha); assert.equal(route.request().postData(), 'load\n10'); payload = stage; }
      else if (url.pathname.endsWith('/preview')) { const body = route.request().postDataJSON(); assert.equal(body.source_sha256, sha); assert.deepEqual(body.columns, columns); if (delayReview) { pending = route; return; } payload = review; }
      else if (url.pathname.endsWith('/commit')) { commitCount++; assert.deepEqual(route.request().postDataJSON(), { schema_version: 'value.data-mapping-commit-request/v1', source_sha256: sha, spec_sha256: spec, normalized_sha256: normalized, target_manifest_sha256: sha }); payload = { schema_version: 'value.data-mapping-commit/v1', ok: true, pack_id: 'copy', role: stage.role, binding: { sha256: normalized, mapping_provenance: { source_sha256: sha, spec_sha256: spec, normalized_sha256: normalized } }, validation: { status: 'passed' }, manifest_sha256: 'd'.repeat(64), run_started: false }; }
      else throw new Error(`Unexpected mapping request ${url.pathname}`);
      await route.fulfill({ json: payload });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const upload = async () => { await page.getByText('选择含标题行的 CSV', { exact: true }).waitFor(); await page.locator('input[type=file]').setInputFiles({ name: 'raw.csv', mimeType: 'text/csv', buffer: Buffer.from('load\n10') }); await page.getByLabel('CSV 来源列').selectOption('load'); };
    const previewButton = page.getByRole('button', { name: '预览规范样例并校验完整文件' });
    const submit = page.getByRole('button', { name: '确认提交映射后的文件' });
    await upload(); await previewButton.click(); await submit.waitFor();
    assert.equal(await submit.isEnabled(), false); assert.equal(commitCount, 0);
    await page.getByLabel('CSV 来源列').selectOption('other');
    assert.equal(await submit.count(), 0); // Mapping change clears the reviewed identity and confirmation.
    await page.getByLabel('CSV 来源列').selectOption('load'); await previewButton.click();
    await page.getByRole('checkbox').check(); await submit.click();
    await page.getByLabel('refresh count').filter({ hasText: '1' }).waitFor();
    assert.equal(commitCount, 1); assert.equal(await submit.count(), 0);
    // Return to original revision in a fresh mount for a response arriving after context switch.
    await page.reload(); await upload(); delayReview = true; await previewButton.click();
    const deadline = Date.now() + 5000;
    while (!pending && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10));
    assert.ok(pending, 'Preview request must reach the delayed response fixture');
    await page.getByRole('button', { name: 'Switch context' }).click();
    await pending.fulfill({ json: review }).catch(() => {}); // Browser may already have aborted it.
    await page.getByText('选择含标题行的 CSV', { exact: true }).waitFor();
    assert.equal(await submit.count(), 0); assert.equal(await page.getByText('完整校验通过，等待明确提交', { exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Switch context' }).click();
    await page.getByText('选择含标题行的 CSV', { exact: true }).waitFor();
    assert.equal(await submit.count(), 0); assert.equal(commitCount, 1);
  } finally {
    await browser?.close();
    if (server) await new Promise(resolve => server.close(resolve));
    await rm(directory, { recursive: true, force: true });
  }
});

// F-P05A-1 (designer ruling 2026-10-06): an EUR price column needs a declared rate, basis and year.
test('an EUR price mapping requires the rate, basis and year before preview and shows original beside converted', { timeout: 45000 }, async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-csv-fx-ui-'));
  let server, browser;
  const role = 'market.belgium.price';
  const priceStage = { ...stage, role, source_columns: ['eur'], rows: 1 };
  const priceColumns = [{ source: 'eur', target: 'value', source_unit: 'EUR/MWh', target_unit: 'GBP/MWh' }];
  const priceCatalog = { ...catalog('copy'), roles: [{ role, columns: [{ target: 'value', target_unit: 'GBP/MWh' }], fx_required_for: ['EUR/MWh'], conversion_pairs: [{ source_unit: 'EUR/MWh', target_unit: 'GBP/MWh', requires_fx: true }, { source_unit: 'GBP/MWh', target_unit: 'GBP/MWh' }], single_value: true }] };
  const fx = { eur_per_gbp: 1.1, fx_basis: 'fixed rate', price_year: 2022 };
  const priceReview = { ...review, role, columns: priceColumns, sample_rows: [{ value: '100' }], source_sample_rows: [{ eur: '110' }], fx };
  try {
    await build({ stdin: { contents: `import React from 'react';import{createRoot}from'react-dom/client';import Editor from './app/features/data/CsvMappingEditor';createRoot(document.getElementById('root')).render(<Editor packId="copy" manifestSha256="${sha}" role="${role}" onMapped={()=>{}}/>);`, resolveDir: root, loader: 'tsx' }, bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js') });
    await writeFile(path.join(directory, 'index.html'), '<div id="root"></div><script type="module" src="/harness.js"></script>');
    server = createServer(async (request, response) => { try { const file = request.url === '/harness.js' ? 'harness.js' : 'index.html'; response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html'); response.end(await readFile(path.join(directory, file))); } catch { response.writeHead(500).end(); } });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch(chromiumLaunchOptions());
    const page = await browser.newPage();
    const previews = [];
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      let payload;
      if (url.pathname.endsWith('/catalog')) payload = priceCatalog;
      else if (url.pathname.endsWith('/stages')) payload = priceStage;
      else if (url.pathname.endsWith('/preview')) { previews.push(route.request().postDataJSON()); payload = priceReview; }
      else throw new Error(`Unexpected mapping request ${url.pathname}`);
      await route.fulfill({ json: payload });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByText('选择含标题行的 CSV', { exact: true }).waitFor();
    await page.locator('input[type=file]').setInputFiles({ name: 'be.csv', mimeType: 'text/csv', buffer: Buffer.from('eur\n110') });
    await page.getByLabel('CSV 来源列').selectOption('eur');
    const previewButton = page.getByRole('button', { name: '预览规范样例并校验完整文件' });
    assert.equal(await page.getByLabel('Currency').inputValue(), 'GBP');
    assert.equal(await previewButton.isEnabled(), true);
    // Spec 11.6 (S-D5): an "eur" column mapped as GBP gets an amber, non-blocking hint.
    assert.equal(await page.getByText('Column name suggests EUR — confirm the currency.', { exact: true }).count(), 1);
    await page.getByLabel('Currency').selectOption('EUR');
    assert.equal(await page.getByText('Column name suggests EUR — confirm the currency.', { exact: true }).count(), 0);
    assert.equal(await page.getByLabel('原始单位').inputValue(), 'EUR/MWh');
    assert.equal(await previewButton.isEnabled(), false, 'missing rate, basis and year block the preview');
    assert.equal(await page.getByText(/^GF_MAPPING_FX/).count(), 3);
    await page.getByLabel('EUR per GBP').fill('1.1');
    await page.getByLabel('FX basis').selectOption('fixed rate');
    await page.getByLabel('Price year').fill('1989');
    assert.equal(await previewButton.isEnabled(), false);
    await page.getByLabel('Price year').fill('2022');
    assert.equal(await previewButton.isEnabled(), true);
    await previewButton.click();
    await page.getByText('converted at 1.1 EUR/GBP (fixed rate, 2022)', { exact: false }).waitFor();
    assert.deepEqual(previews.at(-1).fx, fx);
    assert.deepEqual(previews.at(-1).columns, priceColumns);
    const cells = await page.locator('.csv-mapping-fx-table td').allTextContents();
    assert.deepEqual(cells, ['110', '100']);
  } finally {
    await browser?.close();
    if (server) await new Promise(resolve => server.close(resolve));
    await rm(directory, { recursive: true, force: true });
  }
});

// Spec 11.6 (S-D4): an optional timestamp column and time zone, checked row by row.
test('a declared timestamp column is sent with the preview and its problems are listed by row', { timeout: 45000 }, async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-csv-ts-ui-'));
  let server, browser;
  const role = 'market.france.profile';
  const timedStage = { ...stage, role, source_columns: ['time', 'flow'], rows: 3 };
  const timedColumns = [{ source: 'flow', target: 'value', source_unit: 'MW', target_unit: 'MW' }];
  const timedCatalog = { ...catalog('copy'), roles: [{ role, columns: [{ target: 'value', target_unit: 'MW' }], conversion_pairs: [{ source_unit: 'MW', target_unit: 'MW' }], single_value: true, interval_minutes: 30, timestamp_supported: true, time_zones: ['UTC', 'Europe/London'] }] };
  const timestamp = { column: 'time', time_zone: 'Europe/London', interval_minutes: 30, rows_checked: 3, problem_count: 1, problems: [{ row: 4, timestamp: '2025-01-01T00:30:00+00:00', problem: 'duplicate of row 3' }] };
  const timedReview = { ...review, role, rows: 3, columns: timedColumns, valid: false, normalized_sha256: null, validation: null, errors: ['GF_DATA_TIMESTAMPS: 1 timestamp problem(s) in column time (Europe/London); the rows are listed below.'], timestamp };
  try {
    await build({ stdin: { contents: `import React from 'react';import{createRoot}from'react-dom/client';import Editor from './app/features/data/CsvMappingEditor';createRoot(document.getElementById('root')).render(<Editor packId="copy" manifestSha256="${sha}" role="${role}" onMapped={()=>{}}/>);`, resolveDir: root, loader: 'tsx' }, bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js') });
    await writeFile(path.join(directory, 'index.html'), '<div id="root"></div><script type="module" src="/harness.js"></script>');
    server = createServer(async (request, response) => { try { const file = request.url === '/harness.js' ? 'harness.js' : 'index.html'; response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html'); response.end(await readFile(path.join(directory, file))); } catch { response.writeHead(500).end(); } });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch(chromiumLaunchOptions());
    const page = await browser.newPage();
    const previews = [];
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      let payload;
      if (url.pathname.endsWith('/catalog')) payload = timedCatalog;
      else if (url.pathname.endsWith('/stages')) payload = timedStage;
      else if (url.pathname.endsWith('/preview')) { previews.push(route.request().postDataJSON()); payload = timedReview; }
      else throw new Error(`Unexpected mapping request ${url.pathname}`);
      await route.fulfill({ json: payload });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByText('选择含标题行的 CSV', { exact: true }).waitFor();
    await page.locator('input[type=file]').setInputFiles({ name: 'fr.csv', mimeType: 'text/csv', buffer: Buffer.from('t,f\n1,2') }); // 7 bytes, as the stage fixture says
    await page.getByLabel('CSV 来源列').selectOption('flow');
    const timeZone = page.getByLabel('Time zone');
    assert.equal(await timeZone.isDisabled(), true, 'the time zone applies only once a column is chosen');
    assert.deepEqual(await page.getByLabel('Timestamp column').locator('option').allTextContents(), ['No timestamp column (rows are read in order)', 'time']);
    const previewButton = page.getByRole('button', { name: '预览规范样例并校验完整文件' });
    await previewButton.click();
    await page.getByText('校验未通过，请修改文件或映射', { exact: true }).waitFor();
    assert.equal(previews.at(-1).timestamp, undefined, 'no timestamp column, no declaration');
    await page.getByLabel('Timestamp column').selectOption('time');
    await timeZone.selectOption('Europe/London');
    assert.equal(await page.getByText('校验未通过，请修改文件或映射', { exact: true }).count(), 0, 'a timestamp change discards the review');
    await previewButton.click();
    await page.getByText('duplicate of row 3', { exact: true }).waitFor();
    assert.deepEqual(previews.at(-1).timestamp, { column: 'time', time_zone: 'Europe/London' });
    assert.deepEqual(await page.locator('.csv-mapping-timestamp-report td').allTextContents(), ['4', '2025-01-01T00:30:00+00:00', 'duplicate of row 3']);
    assert.equal(await page.getByRole('button', { name: '确认提交映射后的文件' }).count(), 0);
  } finally {
    await browser?.close();
    if (server) await new Promise(resolve => server.close(resolve));
    await rm(directory, { recursive: true, force: true });
  }
});
