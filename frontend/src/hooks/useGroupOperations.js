import { useEffect, useState } from 'react';
import { listOperations } from '../api/groupOperations';

// A single read in flight keeps snapshots ordered. Only reads repeat on failure.
export function useGroupOperations() {
  const [feed, setFeed] = useState({ operations: [], updated: null, error: null });
  useEffect(() => {
    const lifetime = new AbortController();
    let timer;
    async function poll() {
      try {
        const signal = AbortSignal.any([lifetime.signal, AbortSignal.timeout(4000)]);
        const operations = await listOperations(signal);
        if (!lifetime.signal.aborted) setFeed({ operations, updated: new Date(), error: null });
      } catch (error) {
        if (!lifetime.signal.aborted) setFeed(previous => ({ ...previous, error: error.message }));
      } finally {
        if (!lifetime.signal.aborted) timer = setTimeout(poll, 1000);
      }
    }
    poll();
    return () => { lifetime.abort(); clearTimeout(timer); };
  }, []);
  return feed;
}
