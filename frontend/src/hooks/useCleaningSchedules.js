import { useEffect, useState } from 'react';
import { getCleaningSchedules } from '../api/cleaning';

export function useCleaningSchedules() {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer;

    async function load() {
      try {
        // stop the read if we leave the page or it takes too long
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
        const data = await getCleaningSchedules(signal);
        if (!controller.signal.aborted) setState({ data, loading: false, error: null });
      } catch (error) {
        if (!controller.signal.aborted) {
          setState(previous => ({ ...previous, loading: false, error: error.message }));
        }
      } finally {
        // wait for this read to finish before starting another
        if (!controller.signal.aborted) timer = setTimeout(load, 5000);
      }
    }

    load();
    // stop the old loading cycle before refreshing or leaving
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [reload]);

  function refresh() {
    setState(previous => ({ ...previous, loading: true }));
    // changing reload runs the effect again immediately
    setReload(previous => previous + 1);
  }

  return { ...state, refresh };
}
