// The current page: show desk data, loading, an empty list, or a connection error.
// useDesks handles requests and automatic refreshes; this component only renders
// its state and connects the Retry button. S3-4 can replace this view with the dashboard.

import { useDesks } from './hooks/useDesks';

export default function App() {
  // These values update together when a request starts, succeeds, or fails.
  const { desks, loading, error, lastUpdated, refresh } = useDesks();

  return (
    <main>
      <h1>Desk System</h1>
      {/* Choose one view: error, first load, empty result, or the desk list.
          lastUpdated distinguishes the first load from a background refresh. */}
      {error ? (
        <section role="alert">
          <p>{error}</p>
          <button type="button" onClick={refresh}>Retry now</button>
        </section>
      ) : loading && !lastUpdated ? (
        <p role="status">Loading desks…</p>
      ) : desks.length === 0 ? (
        <p role="status">No desks are available.</p>
      ) : (
        <section aria-label="Current desks">
          <p>{desks.length} desk{desks.length === 1 ? '' : 's'} loaded.</p>
          <ul>
            {/* Make one row per desk. The ID lets React match rows across refreshes. */}
            {desks.map((desk) => (
              <li key={desk.desk_id}>
                {desk.name} ({desk.desk_id}): {desk.position_mm} mm — {desk.status}
              </li>
            ))}
          </ul>
        </section>
      )}
      {/* Keep the list visible while a background refresh is running. */}
      {lastUpdated && !error && <p>Updated at {lastUpdated.toLocaleTimeString()}</p>}
      {loading && lastUpdated && !error && <p role="status">Refreshing…</p>}
    </main>
  );
}
