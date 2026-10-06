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
