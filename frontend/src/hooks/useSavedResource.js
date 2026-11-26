// Poll each saved data source independently. Changing pages cancels the old request.
import { useEffect, useState } from 'react';
import { getJson } from '../api/desks';

export function useSavedResource(path, revision = 0) {
  const [state, setState] = useState({});
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let timer;
    async function load() {
      try {
        const data = await getJson(path, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
        });
        if (!controller.signal.aborted) setState({ path, data });
      } catch (error) {
        if (!controller.signal.aborted) setState({ path, error: error.message });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 10000);
      }
    }
    load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [path, revision]);
  return state.path === path ? state : {};
}
