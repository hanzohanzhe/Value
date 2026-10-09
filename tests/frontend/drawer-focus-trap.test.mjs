import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import path from 'node:path';
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { chromiumLaunchOptions } from './helpers/chromium.mjs';

// W6 (P1 spec 5.2 and 7, D-W3-10): below 900 px the sidebar is a drawer over a
// backdrop. While it is open, Tab and Shift+Tab stay in the sidebar (no focus
// on controls hidden under the backdrop); Esc closes it and focus returns to
// the menu button; when it is closed, Tab reaches the page again.
const root = path.resolve(import.meta.dirname, '../..');
const service = { state: 'online', failures: 0, health: null, runtime: { python: '3.10.18', compatible: true }, architectureVersion: 'value.contracts/v2' };

test('the open navigation drawer keeps keyboard focus inside the sidebar (W6, D-W3-10)', { timeout: 60000 }, async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-drawer-')); let server, browser;
  try {
    await build({
      stdin: { contents: `import React from'react';import{createRoot}from'react-dom/client';import WorkspaceRail from './app/features/shell/WorkspaceRail';import{LocaleProvider}from'./app/i18n/LocaleProvider';const service=${JSON.stringify(service)};createRoot(document.getElementById('root')).render(<LocaleProvider><WorkspaceRail view="overview" onNavigate={()=>{}} service={service} onRetry={()=>{}}/><main><button type="button">Page control</button></main></LocaleProvider>);`, resolveDir: root, loader: 'tsx' },
      bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js'), logLevel: 'silent',
    });
    await writeFile(path.join(directory, 'index.html'), '<!doctype html><link rel="stylesheet" href="/harness.css"><div id="root"></div><script type="module" src="/harness.js"></script>');
    server = createServer(async (req, res) => {
      const file = req.url === '/harness.js' ? 'harness.js' : req.url === '/harness.css' ? 'harness.css' : 'index.html';
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
      res.end(await readFile(path.join(directory, file)).catch(() => ''));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch(chromiumLaunchOptions());
    const page = await browser.newPage({ viewport: { width: 375, height: 800 } });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const menu = page.getByRole('button', { name: 'Open navigation' });
    await menu.click();
    const focused = () => page.evaluate(() => { const a = document.activeElement; return { inRail: Boolean(a?.closest('.rail')), label: (a?.getAttribute('aria-label') || a?.textContent || '').trim() }; });
    assert.match((await focused()).label, /^Home/);
    const stops = [];
    for (let i = 0; i < 40; i += 1) { await page.keyboard.press('Tab'); stops.push(await focused()); }
    assert.ok(stops.every((stop) => stop.inRail), `Tab left the open drawer: ${JSON.stringify(stops.find((stop) => !stop.inRail))}`);
    assert.ok(stops.some((stop) => stop.label === 'Close navigation'), 'Tab wraps to the menu button');
    assert.ok(stops.some((stop) => stop.label === '中文'), 'Tab reaches the language switch');
    await page.getByRole('button', { name: 'Close navigation' }).focus();
    await page.keyboard.press('Shift+Tab');
    assert.deepEqual(await focused(), { inRail: true, label: '中文' });
    await page.keyboard.press('Escape');
    assert.deepEqual(await focused(), { inRail: true, label: 'Open navigation' });
    await page.waitForTimeout(300); // the closing slide (150 ms) ends with the panel hidden
    await page.keyboard.press('Tab');
    assert.deepEqual(await focused(), { inRail: false, label: 'Page control' });
  } finally { await browser?.close(); if (server) await new Promise(resolve => server.close(resolve)); await rm(directory, { recursive: true, force: true }); }
});
