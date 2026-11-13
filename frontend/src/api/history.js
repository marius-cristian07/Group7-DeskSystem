// Browser requests for a desk's saved history (S4-4). These read what the backend
// stored in PostgreSQL, so they keep working when the simulator is offline.
// getJson (in desks.js) handles HTTP, JSON and error messages. useDeskHistory calls
// the two functions below and decides when to refresh.

import { getJson } from './desks';

/**
 * @typedef {{reading_id: number, desk_id: string, recorded_at: string,
 *   position_mm: number, speed_mms: number, status: string,
 *   errors: {error_index: number, time_s: number, error_code: number}[]}} Reading
 * @typedef {{command_id: number, desk_id: string, requested_at: string,
 *   target_position_mm: number, status: string}} Command
 */

// Both routes accept the same start, end and limit parameters, and return newest first.
// A Date becomes an ISO string ending in "Z", which the backend accepts as time-zone aware.
function historyPath(deskId, route, { start, end, limit }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start.toISOString());
  if (end) params.set('end', end.toISOString());
  params.set('limit', String(limit));
  // encodeURIComponent keeps characters such as ":" in a desk ID from changing the path.
  return `/api/desks/${encodeURIComponent(deskId)}/${route}?${params}`;
}

// Check the shape before the rest of the app relies on it, and make sure the answer is
// about the desk that was asked for. A response for another desk must never be shown.
function checkBody(body, deskId, field) {
  if (!body || !Array.isArray(body[field])) {
    throw new Error('Backend returned an invalid history response.');
  }
  if (body.desk_id !== deskId) {
    throw new Error('Backend returned history for a different desk.');
  }
  return body[field];
}

/**
 * Saved readings for one desk, newest first.
 * An error with `status` 404 means the desk has no saved history at all.
 * @param {{start?: Date, end?: Date, limit: number}} query
 * @returns {Promise<Reading[]>}
 */
export async function getDeskReadings(deskId, query, options) {
  const body = await getJson(historyPath(deskId, 'history', query), options);
  return checkBody(body, deskId, 'readings');
}

/**
 * Recorded movement requests for one desk, newest first.
 * @param {{start?: Date, end?: Date, limit: number}} query
 * @returns {Promise<Command[]>}
 */
export async function getDeskCommands(deskId, query, options) {
  const body = await getJson(historyPath(deskId, 'commands', query), options);
  return checkBody(body, deskId, 'commands');
}
