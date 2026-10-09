// Small scale helpers for ChartFrame children (pixel coordinates, no viewBox).

/** Linear map from a data domain to a pixel range; a flat domain maps to the range start. */
export function linearScale(domain: readonly [number, number], range: readonly [number, number]): (value: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  return (value) => (span === 0 ? r0 : r0 + ((value - d0) / span) * (r1 - r0));
}

/** About `count` round tick values covering [min, max] (1, 2, 2.5, 5 x 10^n steps). */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const [low, high] = min < max ? [min, max] : [max, min];
  const raw = (high - low) / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((candidate) => candidate >= raw) ?? 10 * power;
  const first = Math.floor(low / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= high + step * 1e-9; value += step) ticks.push(Number(value.toPrecision(12)));
  if (ticks[ticks.length - 1] < high) ticks.push(Number((ticks[ticks.length - 1] + step).toPrecision(12)));
  return ticks;
}

/** Spec 2.1: chart height by measured width - 220 px below 600 px, else 300 px. */
export function chartHeightFor(width: number): number {
  return width < 600 ? 220 : 300;
}
