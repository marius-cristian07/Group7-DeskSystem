import { useDesks } from './hooks/useDesks';

export default function App() {
  const { desks, loading, error, lastUpdated, refresh } = useDesks();

  return (
    <main>
      <h1>Desk System</h1>
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
            {desks.map((desk) => (
              <li key={desk.desk_id}>
                {desk.name} ({desk.desk_id}): {desk.position_mm} mm — {desk.status}
              </li>
            ))}
          </ul>
        </section>
      )}
      {lastUpdated && !error && <p>Updated at {lastUpdated.toLocaleTimeString()}</p>}
      {loading && lastUpdated && !error && <p role="status">Refreshing…</p>}
    </main>
  );
}
