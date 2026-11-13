// The maths behind the height chart (S4-4): axis ranges, tick positions, and the pixel
// coordinates of every point. There is no React in this file, so it can be tested on
// its own (run `npm test` in frontend/). HeightChart.jsx only draws what this returns.

import { findGaps, splitSegments } from './historyRules.js';

/** Space around the plot for axis labels and titles, in pixels. */
export const MARGIN = Object.freeze({ top: 12, right: 14, bottom: 46, left: 58 });

const MINUTE = 60 * 1000;
const DAY = 24 * 60 * MINUTE;
// Tick spacings the time axis can use, in minutes. The smallest one that keeps the
// number of ticks within the limit is chosen.
const TIME_STEPS_MIN = [1, 2, 5, 10, 15, 30, 60, 120, 180, 240, 360, 720, 1440];

/** Round a step up to 1, 2, 5 or 10 times a power of ten, so ticks land on tidy numbers. */
export function niceStep(rawStep) {
  const power = 10 ** Math.floor(Math.log10(rawStep));
  const fraction = rawStep / power;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * power;
}

/**
 * The vertical axis range, in millimetres. It fits the data with a little room, but
 * never spans less than `minSpan`, so a desk that moved 3 mm does not look like it
 * moved across the whole chart.
 */
export function heightDomain(points, minSpan = 100) {
  let low = 1000;
  let high = 1000;
  if (points.length > 0) {
    low = Infinity;
    high = -Infinity;
    for (const point of points) {
      if (point.height < low) low = point.height;
      if (point.height > high) high = point.height;
    }
  }
  if (high - low < minSpan) {
    const middle = (low + high) / 2;
    low = middle - minSpan / 2;
    high = middle + minSpan / 2;
  }
  const padding = (high - low) * 0.08;
  low -= padding;
  high += padding;

  const step = niceStep((high - low) / 4);
  const min = Math.floor(low / step) * step;
  const max = Math.ceil(high / step) * step;
  const ticks = [];
  for (let value = min; value <= max + step / 1000; value += step) ticks.push(value);
  return { min, max, step, ticks };
}

/** Minutes from UTC to local time at that moment, as milliseconds (positive east of UTC). */
export function localOffsetMs(ms) {
  return -new Date(ms).getTimezoneOffset() * MINUTE;
}

/**
 * Time-axis tick positions between start and end (milliseconds). Ticks fall on round
 * LOCAL times (for example :00, :15, :30), not round UTC times, because the labels
 * show local time. `offsetMs` is only passed in by tests.
 */
export function timeTicks(startMs, endMs, maxTicks = 5, offsetMs = localOffsetMs(startMs)) {
  const span = endMs - startMs;
  if (!(span > 0)) return [];
  const wanted = span / Math.max(1, maxTicks);
  const stepMs = (TIME_STEPS_MIN.find((minutes) => minutes * MINUTE >= wanted) ?? 1440) * MINUTE;
  const first = Math.ceil((startMs + offsetMs) / stepMs) * stepMs - offsetMs;
  const ticks = [];
  for (let t = first; t <= endMs; t += stepMs) ticks.push(t);
  return ticks;
}

/** A tick label: the time, or the date for a tick at local midnight on a long axis. */
export function formatTick(ms, spanMs, offsetMs = localOffsetMs(ms)) {
  const atMidnight = (ms + offsetMs) % DAY === 0;
  if (atMidnight && spanMs > 6 * 60 * MINUTE) {
    return new Date(ms).toLocaleDateString([], { day: 'numeric', month: 'short' });
  }
  return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Everything HeightChart needs to draw, for a chart `width` by `height` pixels.
 * `prepared` is the result of prepareReadings.
 *
 * Each run of readings becomes its own line segment, so the line stops where readings
 * are missing instead of crossing the gap. A run of one reading has no line and is
 * drawn as a dot. `gaps` are the shaded bands for the missing periods.
 */
export function buildChart({ prepared, width, height }) {
  const plot = {
    left: MARGIN.left,
    top: MARGIN.top,
    width: Math.max(80, width - MARGIN.left - MARGIN.right),
    height: Math.max(80, height - MARGIN.top - MARGIN.bottom),
  };
  const { start, end } = prepared.domain;
  const span = Math.max(1, end - start);
  const heights = heightDomain(prepared.points);

  const xOf = (t) => plot.left + Math.min(1, Math.max(0, (t - start) / span)) * plot.width;
  const yOf = (value) => plot.top + ((heights.max - value) / (heights.max - heights.min)) * plot.height;

  const segments = splitSegments(prepared.points, prepared.gapThresholdMs).map((run) => {
    const dots = run.map((point) => ({ ...point, x: xOf(point.t), y: yOf(point.height) }));
    return {
      dots,
      // A single reading has nothing to connect to.
      path: dots.length > 1 ? dots.map((dot, i) => `${i === 0 ? 'M' : 'L'}${dot.x.toFixed(1)} ${dot.y.toFixed(1)}`).join(' ') : null,
    };
  });

  const gaps = findGaps({
    points: prepared.points,
    domain: prepared.domain,
    gapThresholdMs: prepared.gapThresholdMs,
    truncated: prepared.truncated,
  }).map((gap) => ({ ...gap, x: xOf(gap.from), width: Math.max(0, xOf(gap.to) - xOf(gap.from)) }));

  const maxTicks = Math.max(2, Math.floor(plot.width / 90));
  return {
    plot,
    heights,
    yTicks: heights.ticks.map((value) => ({ value, y: yOf(value) })),
    xTicks: timeTicks(start, end, maxTicks).map((t) => ({ t, x: xOf(t), label: formatTick(t, span) })),
    segments,
    gaps,
  };
}
