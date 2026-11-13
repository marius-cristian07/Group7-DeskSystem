// React's data layer for the history section (S4-4). For one desk and one time range it
// loads the saved readings and the recorded movement requests, then reloads both about
// every 15 seconds while the section is on screen, so new readings appear on their own.
// The two lists are loaded and reported separately: if one fails, the other still shows.
//
// This hook is independent of useDesks. A history failure never touches the live desk list.

import { useCallback, useEffect, useRef, useState } from 'react';
import { getDeskCommands, getDeskReadings } from '../api/history';
import {
  COMMANDS_LIMIT,
  READINGS_LIMIT,
  getWindowStart,
  prepareCommands,
  prepareReadings,
} from '../utils/historyRules';

const REFRESH_INTERVAL_MS = 15000;

const LOADING = Object.freeze({ status: 'loading' });

/**
 * What the hook returns for each list (`readings` and `commands`):
 *   { status: 'loading' }
 *   { status: 'ready', prepared, fetchedAt, refreshError }
 *       Data to show. refreshError is a message when the latest reload failed and the
 *       data on screen is from an earlier one; otherwise null.
 *   { status: 'none-yet' }
 *       The desk has no saved history of this kind at all.
 *   { status: 'none-in-period', latestAt, fetchedAt }
 *       The desk has history, but none in the selected range. latestAt is the time of
 *       the most recent saved row, in milliseconds (or null if unreadable).
 *   { status: 'unavailable', message }
 *       The history service did not answer. The live desk list is not affected.
 */

// Tell "nothing in this range" from "nothing at all" by asking for the newest row ever saved.
async function describeEmpty(fetchRows, timeOf, options) {
  const latest = await fetchRows({ limit: 1 }, options);
  if (latest.length === 0) return { status: 'none-yet' };
  const latestAt = Date.parse(timeOf(latest[0]));
  return {
    status: 'none-in-period',
    latestAt: Number.isFinite(latestAt) ? latestAt : null,
    fetchedAt: new Date(),
  };
}

async function loadReadings(deskId, rangeId, now, options) {
  const fetchRows = (query, opts) => getDeskReadings(deskId, query, opts);
  try {
    // No end time is sent: "everything since the start" cannot hide a reading just
    // because this computer's clock is a little behind the database's.
    const rows = await fetchRows({ start: getWindowStart(rangeId, now), limit: READINGS_LIMIT }, options);
    const prepared = prepareReadings(rows, { rangeId, now });
    if (prepared.points.length > 0) {
      return { status: 'ready', prepared, fetchedAt: new Date(), refreshError: null };
    }
    if (rows.length > 0) throw new Error('Backend returned readings that could not be read.');
    return await describeEmpty(fetchRows, (row) => row.recorded_at, options);
  } catch (error) {
    // The backend answers 404 for a desk that has never been saved to the database.
    if (error.status === 404) return { status: 'none-yet' };
    throw error;
  }
}

async function loadCommands(deskId, rangeId, now, options) {
  const fetchRows = (query, opts) => getDeskCommands(deskId, query, opts);
  try {
    const rows = await fetchRows({ start: getWindowStart(rangeId, now), limit: COMMANDS_LIMIT }, options);
    const prepared = prepareCommands(rows);
    if (prepared.rows.length > 0) {
      return { status: 'ready', prepared, fetchedAt: new Date(), refreshError: null };
    }
    if (rows.length > 0) throw new Error('Backend returned movement requests that could not be read.');
    return await describeEmpty(fetchRows, (row) => row.requested_at, options);
  } catch (error) {
    if (error.status === 404) return { status: 'none-yet' };
    throw error;
  }
}

/**
 * @param {string} deskId  The desk whose history to show.
 * @param {string} rangeId One of the ids in HISTORY_RANGES.
 * @returns {{readings: object, commands: object, refresh: () => Promise<void>}}
 */
export function useDeskHistory(deskId, rangeId) {
  // The state remembers which desk and range it belongs to. Anything that does not
  // match the current desk and range is treated as not loaded yet, so one desk's
  // history can never appear while another desk is selected.
  const key = `${deskId}|${rangeId}`;
  const [state, setState] = useState({ key, readings: LOADING, commands: LOADING });
  const reload = useRef(() => Promise.resolve());

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    let loadingNow = false;

    // Start from "loading" whenever the desk or the range changes.
    setState((previous) => (previous.key === key ? previous : { key, readings: LOADING, commands: LOADING }));

    // Each result is written only if this effect run is still the current one. When the
    // desk or range changes, cleanup aborts the old requests and this check ignores
    // any answer that was already on its way.
    const report = async (name, loader) => {
      try {
        const result = await loader();
        if (controller.signal.aborted) return;
        setState((previous) => (previous.key === key ? { ...previous, [name]: result } : previous));
      } catch (error) {
        if (error.name === 'AbortError' || controller.signal.aborted) return;
        setState((previous) => {
          if (previous.key !== key) return previous;
          const shown = previous[name];
          // Keep data that is already on screen and say that it could not be refreshed.
          const failed = shown.status === 'ready'
            ? { ...shown, refreshError: error.message }
            : { status: 'unavailable', message: error.message };
          return { ...previous, [name]: failed };
        });
      }
    };

    const load = async () => {
      // A slow request must not pile up behind the timer.
      if (loadingNow) return;
      loadingNow = true;
      const now = new Date();
      try {
        await Promise.all([
          report('readings', () => loadReadings(deskId, rangeId, now, options)),
          report('commands', () => loadCommands(deskId, rangeId, now, options)),
        ]);
      } finally {
        loadingNow = false;
      }
    };

    reload.current = load;
    void load();
    const timer = setInterval(() => { void load(); }, REFRESH_INTERVAL_MS);

    return () => {
      controller.abort();
      clearInterval(timer);
      reload.current = () => Promise.resolve();
    };
  }, [deskId, rangeId, key]);

  const refresh = useCallback(() => reload.current(), []);

  const current = state.key === key ? state : { readings: LOADING, commands: LOADING };
  return { readings: current.readings, commands: current.commands, refresh };
}
