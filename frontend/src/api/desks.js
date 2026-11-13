// All browser requests to the Python backend go through this file.
// getJson handles HTTP, JSON, and error messages; the exported functions choose
// the route. useDesks calls getDesks and decides when to refresh the page.

/**
 * The Python backend is the only API used by the frontend. Its list endpoint
 * returns Desk[] directly; the single-desk endpoint returns one Desk.
 *
 * @typedef {{time_s: number, errorCode: number}} DeskError
 * @typedef {{desk_id: string, name: string, position_mm: number,
 *   speed_mms: number, status: string, is_anti_collision: boolean,
 *   last_errors: DeskError[]}} Desk
 */

// Remove trailing slashes so joining the address and route gives one slash.
const backendUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080').replace(/\/+$/, '');

// signal is optional: the hook passes an AbortController's signal so it can
// stop a request when the user leaves the page. Callers may omit the options.
export async function getJson(path, { signal } = {}) {
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
  } catch (error) {
    // Cancellation can happen while the response body is still being read.
    if (error.name === 'AbortError') throw error;
    throw new Error(`Backend returned an invalid response (HTTP ${response.status}).`);
  }

  // Fetch resolves on HTTP errors too; FastAPI puts the reason in detail.
  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${response.status}`;
    throw Object.assign(new Error(`Backend request failed: ${detail}`), { status: response.status });
  }

  return body;
}

/** Fetch the current list (an empty array is a valid result). @returns {Promise<Desk[]>} */
export async function getDesks(options) {
  const desks = await getJson('/api/desks', options);
  if (!Array.isArray(desks)) throw new Error('Backend returned an invalid desk list.');
  return desks;
}

/** Fetch one desk by ID for a detail view. @returns {Promise<Desk>} */
export function getDesk(deskId, options) {
  // Keep special characters in the ID from changing the URL path.
  return getJson(`/api/desks/${encodeURIComponent(deskId)}`, options);
}

/** Check that the backend responds; this does not check the simulator or database.
 * @returns {Promise<{status: string}>} */
export function getHealth(options) {
  return getJson('/api/health', options);
}
