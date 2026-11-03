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
  const mounted = useRef(false);
  const pendingRequest = useRef(null);

  const refresh = useCallback(() => {
    if (pendingRequest.current) return pendingRequest.current.promise;

    const request = { controller: new AbortController(), promise: null };
    pendingRequest.current = request;
    setState((previous) => ({ ...previous, loading: true }));

    request.promise = (async () => {
      try {
        const desks = await getDesks({ signal: request.controller.signal });
        if (mounted.current && pendingRequest.current === request) {
          setState({ desks, loading: false, error: null, lastUpdated: new Date() });
        }
      } catch (error) {
        if (mounted.current && pendingRequest.current === request && error.name !== 'AbortError') {
          setState({ desks: [], loading: false, error: error.message, lastUpdated: null });
        }
      } finally {
        if (pendingRequest.current === request) pendingRequest.current = null;
      }
    })();

    return request.promise;
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = setInterval(() => { void refresh(); }, REFRESH_INTERVAL_MS);
    return () => {
      mounted.current = false;
      clearInterval(timer);
      pendingRequest.current?.controller.abort();
      pendingRequest.current = null;
    };
  }, [refresh]);

  return { ...state, refresh };
}
