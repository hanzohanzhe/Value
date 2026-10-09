import assert from "node:assert/strict";
import test from "node:test";
import { chartHeightFor, linearScale, niceTicks } from "../../../app/ui/chartScale.ts";
import { TECH_SERIES, techSeries } from "../../../app/ui/chartPalette.ts";

// P1 spec 1.2 / 2.1: chart sizing, scales and the technology palette (W1).

test("ChartFrame sizing and scales: 220 px below 600 px wide, else 300 px; round ticks", () => {
  assert.equal(chartHeightFor(375), 220);
  assert.equal(chartHeightFor(599), 220);
  assert.equal(chartHeightFor(600), 300);
  assert.equal(chartHeightFor(1280), 300);
  const x = linearScale([0, 10], [40, 440]);
  assert.equal(x(0), 40);
  assert.equal(x(5), 240);
  assert.equal(linearScale([3, 3], [0, 100])(3), 0);
  assert.deepEqual(niceTicks(0, 100, 5), [0, 20, 40, 60, 80, 100]);
  assert.deepEqual(niceTicks(0, 1, 4), [0, 0.25, 0.5, 0.75, 1]);
  assert.deepEqual(niceTicks(-12, 37, 5), [-20, -10, 0, 10, 20, 30, 40]);
  assert.deepEqual(niceTicks(5, 5), [5]);
  assert.deepEqual(niceTicks(Number.NaN, 1), []);
});

test("technology palette: tokens only; shared colours are told apart by a pattern", () => {
  for (const style of Object.values(TECH_SERIES)) assert.match(style.color, /^var\(--tech-[a-z-]+\)$/);
  const byColour = new Map();
  for (const [key, style] of Object.entries(TECH_SERIES)) {
    const seen = byColour.get(style.color) ?? [];
    seen.push([key, style.pattern]);
    byColour.set(style.color, seen);
  }
  for (const [colour, entries] of byColour) {
    const patterns = entries.map(([, pattern]) => pattern);
    assert.equal(new Set(patterns).size, patterns.length, `${colour}: ${entries.map(([key]) => key).join(", ")} need different patterns`);
  }
  assert.equal(TECH_SERIES.unused_vre.pattern, "hatch", "unused VRE is hatched, not colour-only");
  assert.equal(TECH_SERIES.import.pattern, "dots");
  assert.deepEqual(techSeries("offshore_wind"), TECH_SERIES.wind_offshore);
  assert.deepEqual(techSeries("ccgt"), TECH_SERIES.ccgt);
  assert.equal(techSeries("unknown_tech"), null);
});
