/**
 * The Python backend is the only API used by the frontend. Its list endpoint
 * returns Desk[] directly; the single-desk endpoint returns one Desk.
 *
 * @typedef {{time_s: number, errorCode: number}} DeskError
 * @typedef {{desk_id: string, name: string, position_mm: number,
 *   speed_mms: number, status: string, is_anti_collision: boolean,
 *   last_errors: DeskError[]}} Desk
 */

const backendUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080').replace(/\/+$/, '');

async function getJson(path, { signal } = {}) {
  let response;
  try {
    response = await fetch(`${backendUrl}${path}`, { signal });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot connect to the Python backend. Check that it is running.');
  }

  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`Backend returned an invalid response (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
    throw new Error(`Backend request failed: ${detail}`);
  }

  return body;
}

/** @returns {Promise<Desk[]>} */
export async function getDesks(options) {
  const desks = await getJson('/api/desks', options);
  if (!Array.isArray(desks)) throw new Error('Backend returned an invalid desk list.');
  return desks;
}

/** @returns {Promise<Desk>} */
export function getDesk(deskId, options) {
  return getJson(`/api/desks/${encodeURIComponent(deskId)}`, options);
}

/** @returns {Promise<{status: string}>} */
export function getHealth(options) {
  return getJson('/api/health', options);
}
