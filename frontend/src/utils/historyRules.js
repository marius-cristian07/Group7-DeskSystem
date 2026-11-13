// Rules for the desk-history view (S4-4). There is no React and no fetch in this
// file, so the rules can be read and tested on their own (run `npm test` in frontend/).
//
// The backend returns saved readings and movement requests newest first, with a
// maximum of 1000 rows per request. The functions here turn those rows into what the
// chart and the table draw, and decide where the data has gaps or was cut short.

/** The time ranges the person can choose. `ms` is how far back the range reaches. */
export const HISTORY_RANGES = Object.freeze([
  Object.freeze({ id: '1h', label: 'Last hour', phrase: 'in the last hour', ms: 60 * 60 * 1000 }),
  Object.freeze({ id: '24h', label: 'Last 24 hours', phrase: 'in the last 24 hours', ms: 24 * 60 * 60 * 1000 }),
]);

export const DEFAULT_RANGE_ID = '1h';

/** 1000 is the most the backend allows in one request. */
export const READINGS_LIMIT = 1000;
/** A table of 100 requests is already long; the notice says when more exist. */
export const COMMANDS_LIMIT = 100;

/** Two readings closer than this are never treated as a gap. */
export const MIN_GAP_MS = 2 * 60 * 1000;

export function getRange(rangeId) {
  return HISTORY_RANGES.find((range) => range.id === rangeId) ?? HISTORY_RANGES[0];
}

/** Where the selected range begins, counted back from `now`. */
export function getWindowStart(rangeId, now) {
  return new Date(now.getTime() - getRange(rangeId).ms);
}

/**
 * How long without a saved reading counts as a gap. The backend saves a reading
 * about once a minute, but that is configurable, so the threshold follows the
 * typical spacing in the data: three times the usual interval, and never less than
 * two minutes. The lower median is used so that one long outage in a short series
 * cannot raise the threshold above itself.
 */
export function getGapThresholdMs(points) {
  if (points.length < 3) return MIN_GAP_MS;
  const spacings = [];
  for (let i = 1; i < points.length; i += 1) spacings.push(points[i].t - points[i - 1].t);
  spacings.sort((a, b) => a - b);
  const typical = spacings[Math.floor((spacings.length - 1) / 2)];
  return Math.max(MIN_GAP_MS, typical * 3);
}

/**
 * Turn the rows from the history endpoint into chart points, oldest first.
 *
 * `domain` is the time span the chart's horizontal axis covers. Normally that is the
 * whole selected range, so a period with no saved readings stays visibly empty.
 * When the backend cut the result short, the OLDEST rows are the ones missing, so the
 * axis starts at the oldest row that was returned. Otherwise the cut-off part of the
 * range would look like a period in which nothing was recorded.
 */
export function prepareReadings(rawReadings, { rangeId, now, limit = READINGS_LIMIT }) {
  const points = [];
  for (const reading of rawReadings) {
    const t = Date.parse(reading?.recorded_at);
    const height = reading?.position_mm;
    // A row without a usable time or height cannot be placed on the chart.
    if (!Number.isFinite(t) || typeof height !== 'number' || !Number.isFinite(height)) continue;
    points.push({
      id: reading.reading_id,
      t,
      height,
      status: reading.status,
      speedMms: reading.speed_mms,
    });
  }
  points.sort((a, b) => a.t - b.t || (a.id ?? 0) - (b.id ?? 0));

  // The API reports no total. Receiving exactly `limit` rows is the signal that
  // there may be older ones that were not sent.
  const truncated = rawReadings.length >= limit;
  const windowStart = getWindowStart(rangeId, now).getTime();
  const newest = points.length > 0 ? points[points.length - 1].t : 0;

  return {
    points,
    skipped: rawReadings.length - points.length,
    truncated,
    limit,
    domain: {
      start: truncated && points.length > 0 ? points[0].t : windowStart,
      end: Math.max(now.getTime(), newest),
    },
    gapThresholdMs: getGapThresholdMs(points),
  };
}

/** Split the points into runs. A new run starts wherever the gap is longer than the threshold. */
export function splitSegments(points, gapThresholdMs) {
  const segments = [];
  for (const point of points) {
    const current = segments[segments.length - 1];
    if (current && point.t - current[current.length - 1].t <= gapThresholdMs) {
      current.push(point);
    } else {
      segments.push([point]);
    }
  }
  return segments;
}

/**
 * The periods inside the chart with no saved readings: between two readings that are
 * too far apart, before the first reading, and after the last one. The chart shades
 * these so a missing period is never read as a measured one.
 */
export function findGaps({ points, domain, gapThresholdMs, truncated }) {
  if (points.length === 0) return [];
  const gaps = [];
  // When the result was cut short, the axis already starts at the first row.
  if (!truncated && points[0].t - domain.start > gapThresholdMs) {
    gaps.push({ from: domain.start, to: points[0].t });
  }
  for (let i = 1; i < points.length; i += 1) {
    if (points[i].t - points[i - 1].t > gapThresholdMs) {
      gaps.push({ from: points[i - 1].t, to: points[i].t });
    }
  }
  const last = points[points.length - 1];
  if (domain.end - last.t > gapThresholdMs) gaps.push({ from: last.t, to: domain.end });
  return gaps;
}

/** Rows from the commands endpoint, newest first, with the same cut-off signal as readings. */
export function prepareCommands(rawCommands, { limit = COMMANDS_LIMIT } = {}) {
  const rows = [];
  for (const command of rawCommands) {
    const t = Date.parse(command?.requested_at);
    if (!Number.isFinite(t) || typeof command.target_position_mm !== 'number') continue;
    rows.push({
      id: command.command_id,
      t,
      iso: command.requested_at,
      target: command.target_position_mm,
      status: String(command.status ?? ''),
    });
  }
  rows.sort((a, b) => b.t - a.t || (b.id ?? 0) - (a.id ?? 0));
  return {
    rows,
    skipped: rawCommands.length - rows.length,
    truncated: rawCommands.length >= limit,
    limit,
  };
}

/**
 * What a recorded request status means, in words. "accepted" only says the simulator
 * took the request; it never says the desk finished moving, so the wording avoids that.
 * A status this code does not know is shown as recorded rather than hidden.
 */
export function describeOutcome(status) {
  switch (String(status).trim().toLowerCase()) {
    case 'accepted':
      return {
        kind: 'accepted',
        symbol: '✓',
        label: 'Accepted',
        detail: 'The simulator accepted the request. This does not confirm the desk reached the target.',
      };
    case 'failed':
      return {
        kind: 'failed',
        symbol: '✕',
        label: 'Failed',
        detail: 'The request was rejected, so the desk was not asked to move.',
      };
    case 'unknown':
      return {
        kind: 'unknown',
        symbol: '?',
        label: 'Unknown',
        detail: 'It could not be confirmed whether the request was accepted. The desk may have moved.',
      };
    default:
      return {
        kind: 'other',
        symbol: '•',
        label: String(status).trim() || 'No status',
        detail: 'This status is shown exactly as it was recorded.',
      };
  }
}

/** Date and time for tables and notices, in the viewer's own time zone. */
export function formatDateTime(ms) {
  return new Date(ms).toLocaleString([], {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** Clock time only, for the chart's axis and the "updated" text. */
export function formatClock(ms, withSeconds = false) {
  return new Date(ms).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    ...(withSeconds ? { second: '2-digit' } : {}),
  });
}

/** "3 minutes" or "1 hour 30 minutes", for explaining the gap threshold. */
export function formatDuration(ms) {
  const totalMinutes = Math.max(1, Math.round(ms / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const parts = [];
  if (hours > 0) parts.push(`${hours} hour${hours === 1 ? '' : 's'}`);
  if (minutes > 0) parts.push(`${minutes} minute${minutes === 1 ? '' : 's'}`);
  return parts.join(' ');
}
