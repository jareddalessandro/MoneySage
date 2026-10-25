/** Y-axis ranges with round, evenly spaced ticks ($0, $100, $200 rather than $65, $130, $195). */

type Axis = { domain: [number, number]; ticks: number[] };

// The smallest of 1, 2, 2.5, 5, 10 × a power of ten that's at least `rough`.
function niceStep(rough: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((m) => m >= rough)!;
}

function axis(min: number, step: number, steps: number): Axis {
  return { domain: [min, min + step * steps], ticks: Array.from({ length: steps + 1 }, (_, i) => min + step * i) };
}

/**
 * Range fitted to the data instead of starting at $0, so month-to-month moves are visible:
 * padded so no point sits on the edge.
 */
export function fittedAxis(values: number[]): Axis | undefined {
  if (values.length === 0) return undefined;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.02 || 1;
  const step = niceStep((hi - lo + 2 * pad) / 4);
  const min = Math.floor((lo - pad) / step) * step;
  return axis(min, step, Math.max(4, Math.ceil((hi + pad - min) / step)));
}

/** Range from $0 up to a round step above the largest value, for bars that compare amounts. */
export function zeroAxis(values: number[]): Axis | undefined {
  const hi = Math.max(0, ...values);
  if (hi <= 0) return undefined;
  const step = niceStep(hi / 4);
  return axis(0, step, Math.ceil(hi / step));
}
