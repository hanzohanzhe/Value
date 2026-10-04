import assert from "node:assert/strict";
import test from "node:test";
import { renderTsx, textOf } from "../helpers/render-tsx.mjs";

// Infrastructure check for the offline SSR path used by later view tests.
test("renderTsx renders a real app component to markup without a browser", async () => {
  const html = await renderTsx("app/features/shared/presentation.tsx", "Badge", { tone: "good", children: "Passed" });
  assert.equal(html, '<span class="badge good">Passed</span>');
  assert.equal(textOf(html), "Passed");
});

test("renderTsx reuses the bundle and passes fresh props on every call", async () => {
  const first = await renderTsx("app/features/shared/presentation.tsx", "Badge", { children: "A" });
  const second = await renderTsx("app/features/shared/presentation.tsx", "Badge", { tone: "warn", children: "B" });
  assert.match(first, /badge neutral/);
  assert.match(second, /badge warn/);
});

test("renderTsx reports a missing export instead of rendering nothing", async () => {
  await assert.rejects(renderTsx("app/features/shared/presentation.tsx", "NoSuchComponent", {}), /no function export/);
});
