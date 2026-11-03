// React's data layer for the desk page. It loads desks on mount and tries again
// every five seconds, including after failures. App reads the returned state
// and can call refresh() for a manual retry; it does not need its own fetch or timer.

import { useCallback, useEffect, useRef, useState } from 'react';
import { getDesks } from '../api/desks';

const REFRESH_INTERVAL_MS = 5000;

/**
 * Dashboard data interface:
 *   desks       Current Desk[] from the last successful request; [] on failure.
 *   loading     A request is in progress (also true on initial load).
 *   error       Error message or null. A failure clears desks and lastUpdated.
 *   lastUpdated Date of the latest successful response, or null.
 *   refresh     Request immediately; concurrent calls share the active request.
 */
export function useDesks() {
  const [state, setState] = useState({
    desks: [],
    loading: true,
    error: null,
    lastUpdated: null,
  });
  // State above redraws the page. These refs only track whether a request may
  // update it, and survive renders without causing another render themselves.
  const mounted = useRef(false); // Is the component using this hook still on screen?
  const pendingRequest = useRef(null); // The active request's controller and promise.

  // Keep the same refresh function between renders, so the effect below does
  // not restart its timer every time loading or desk data changes.
  const refresh = useCallback(() => {
    if (!mounted.current) return Promise.resolve();
    // Timer ticks and manual retries share the same request while it is running.
    if (pendingRequest.current) return pendingRequest.current.promise;

    // The controller lets cleanup cancel fetch. The request object also identifies
    // this particular load, so an older response cannot overwrite a newer one.
    const request = { controller: new AbortController(), promise: null };
    pendingRequest.current = request;
    // Keep the current data or error visible until we know the new result.
    setState((previous) => ({ ...previous, loading: true }));

    // Start immediately and keep the promise for any callers that arrive later.
    request.promise = (async () => {
      try {
        const desks = await getDesks({ signal: request.controller.signal });
        // Only the active request may update a component that is still mounted.
        if (mounted.current && pendingRequest.current === request) {
          setState({ desks, loading: false, error: null, lastUpdated: new Date() });
        }
      } catch (error) {
        // Leaving the page cancels fetch with AbortError; that is not a connection failure.
        if (mounted.current && pendingRequest.current === request && error.name !== 'AbortError') {
          // An old successful reading must not look current after a failed refresh.
          setState({ desks: [], loading: false, error: error.message, lastUpdated: null });
        }
      } finally {
        // A cancelled older request must not clear a newer request's reference.
        if (pendingRequest.current === request) pendingRequest.current = null;
      }
    })();

    return request.promise;
  }, []);

  useEffect(() => {
    mounted.current = true;
    // Load once now, then poll. 'void' means we intentionally do not await the
    // promise here; refresh handles its errors and updates state itself.
    void refresh();
    const timer = setInterval(() => { void refresh(); }, REFRESH_INTERVAL_MS);
    // React calls this cleanup when the component is removed (or the effect restarts).
    return () => {
      mounted.current = false;
      clearInterval(timer);
      pendingRequest.current?.controller.abort();
      // The identity check above also ignores late responses from a previous mount.
      pendingRequest.current = null;
    };
  }, [refresh]);

  // The dashboard receives both the latest state and the manual retry action.
  return { ...state, refresh };
}
