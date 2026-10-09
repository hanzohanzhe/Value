import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import path from 'node:path';
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { chromiumLaunchOptions } from './helpers/chromium.mjs';

// P1-polish R-1 (designer ruling, W6 todo 5): at 1440x900 and 1280x720 every
// one of the ten sidebar entries is fully visible without scrolling the
// sidebar; the footer (service status, language, version) stays in view.
// Real component, real tokens and shell CSS, headless Chromium.
const root = path.resolve(import.meta.dirname, '../..');
const service = { state: 'online', failures: 0, health: { status: 'ok', version: '0.6.0-alpha.2' }, runtime: { python: '3.10.18', compatible: true, selected_capability: 'value-native' }, architectureVersion: 'value.contracts/v2' };

async function harness(locale) {
  const directory = await mkdtemp(path.join(tmpdir(), 'value-rail-'));
  await build({
    stdin: { contents: `import React from'react';import{createRoot}from'react-dom/client';import './app/globals.css';import './app/styles/reset.css';import './app/styles/base.css';import WorkspaceRail from './app/features/shell/WorkspaceRail';import{LocaleProvider}from'./app/i18n/LocaleProvider';const service=${JSON.stringify(service)};createRoot(document.getElementById('root')).render(<LocaleProvider initialLocale="${locale}"><div className="workbench"><WorkspaceRail view="audit" onNavigate={()=>{}} service={service} onRetry={()=>{}}/><main className="surface"><p>Page</p></main></div></LocaleProvider>);`, resolveDir: root, loader: 'tsx' },
    bundle: true, format: 'esm', jsx: 'automatic', outfile: path.join(directory, 'harness.js'), logLevel: 'silent',
  });
  await writeFile(path.join(directory, 'index.html'), '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/harness.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>');
  const server = createServer(async (req, res) => {
    const file = req.url === '/harness.js' ? 'harness.js' : req.url === '/harness.css' ? 'harness.css' : 'index.html';
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
    res.end(await readFile(path.join(directory, file)).catch(() => ''));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { directory, server, url: `http://127.0.0.1:${server.address().port}` };
}

for (const locale of ['en', 'zh']) {
  test(`all ten sidebar entries are visible at 1440x900 and 1280x720 (${locale}, R-1)`, { timeout: 60000 }, async () => {
    const { directory, server, url } = await harness(locale);
    let browser;
    try {
      browser = await chromium.launch(chromiumLaunchOptions());
      for (const [width, height] of [[1440, 900], [1280, 720]]) {
        const page = await browser.newPage({ viewport: { width, height } });
        await page.goto(url);
        await page.waitForSelector('.rail nav a');
        const layout = await page.evaluate(() => {
          const nav = document.querySelector('.rail nav');
          const box = nav.getBoundingClientRect();
          const foot = document.querySelector('.rail-foot').getBoundingClientRect();
          const links = [...nav.querySelectorAll('a')].map((link) => {
            const rect = link.getBoundingClientRect();
            return { label: link.getAttribute('title'), top: rect.top, bottom: rect.bottom };
          });
          return { navTop: box.top, navBottom: box.bottom, scroll: nav.scrollHeight - nav.clientHeight, footTop: foot.top, footBottom: foot.bottom, links };
        });
        const where = `${width}x${height} ${locale}`;
        assert.equal(layout.links.length, 10, `${where}: ten entries`);
        assert.ok(layout.scroll <= 0, `${where}: the sidebar navigation needs ${layout.scroll}px of scrolling`);
        for (const link of layout.links) {
          assert.ok(link.top >= layout.navTop - 0.5 && link.bottom <= layout.navBottom + 0.5, `${where}: "${link.label}" is cut off (${link.top}-${link.bottom} outside ${layout.navTop}-${layout.navBottom})`);
          assert.ok(link.bottom <= layout.footTop + 0.5, `${where}: "${link.label}" is under the sidebar footer`);
        }
        assert.ok(layout.footBottom <= height + 0.5, `${where}: the sidebar footer is below the window (${layout.footBottom})`);
        await page.close();
      }
    } finally {
      await browser?.close();
      await new Promise(resolve => server.close(resolve));
      await rm(directory, { recursive: true, force: true });
    }
  });
}
