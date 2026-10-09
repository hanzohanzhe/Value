import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderTsx } from "../helpers/render-tsx.mjs";

// P1 frontend overhaul spec 2.1: ChartFrame (W1).
const h = React.createElement;

test("ChartFrame draws in pixels (no viewBox), sizes by width, HTML legend with patterns, data-table toggle", async () => {
  const props = {
    title: "Generation by technology",
    summary: "Solar and offshore wind generation for 2025.",
    width: 480,
    legend: [
      { key: "solar", label: "Solar", color: "var(--tech-solar)" },
      { key: "offshore", label: "Offshore wind", color: "var(--tech-wind)", pattern: "hatch" },
    ],
    table: { caption: "Generation (MWh)", rows: [{ id: "solar", v: "1" }], rowKey: (row) => row.id, columns: [{ key: "v", header: "MWh", numeric: true, render: (row) => row.v }] },
    children: ({ width, height, fill }) => h("rect", { x: 0, y: 0, width, height, style: { fill: fill("offshore") }, "data-solar": fill("solar") }),
  };
  const html = await renderTsx("app/ui/ChartFrame.tsx", "ChartFrame", props);
  assert.match(html, /<svg class="v-chart__svg" width="480" height="220" role="img" aria-label="Solar and offshore wind generation for 2025\.">/);
  assert.doesNotMatch(html, /viewBox/);
  assert.match(html, /<ul class="v-chart__legend"><li><span class="v-swatch v-swatch--solid" style="--swatch:var\(--tech-solar\)" aria-hidden="true"><\/span><span>Solar<\/span><\/li>/);
  assert.match(html, /v-swatch--hatch/);
  const patternId = /<pattern id="([^"]+)"[^>]*patternTransform="rotate\(45\)"/.exec(html)[1];
  assert.match(html, new RegExp(`style="fill:url\\(#${patternId}\\)" data-solar="var\\(--tech-solar\\)"`));
  assert.match(html, /<button type="button" class="v-chart__toggle" aria-expanded="false" aria-controls="[^"]+">Show data table<\/button>/);
  assert.doesNotMatch(html, /<table/, "the table is shown only on request");
  const wide = await renderTsx("app/ui/ChartFrame.tsx", "ChartFrame", { ...props, width: 900 });
  assert.match(wide, /width="900" height="300"/);
});
