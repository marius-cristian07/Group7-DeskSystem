// The dashboard page (S3-4): a grid of desk cards built from live desk data,
// or a loading, empty, or connection-error message.
// useDesks handles requests and automatic refreshes; this component only renders
// its state and connects the Retry button. DeskDashboard draws the grid.

import DeskDashboard from './components/DeskDashboard';
import { useDesks } from './hooks/useDesks';
import './dashboard.css';

export default function App() {
  // These values update together when a request starts, succeeds, or fails.
  const { desks, loading, error, lastUpdated, refresh } = useDesks();

  return (
    <main className="app">
      <header className="app__header">
        <h1>Desk System</h1>
        {/* Keep the update time visible while a background refresh is running.
            lastUpdated distinguishes the first load from a background refresh. */}
        <p className="app__updated">
          {lastUpdated && !error && <>Updated at {lastUpdated.toLocaleTimeString()}</>}
          {loading && lastUpdated && !error && <span role="status"> · Refreshing…</span>}
        </p>
      </header>
      {/* Choose one view: error, first load, empty result, or the desk grid. */}
      {error ? (
        <section className="notice notice--error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={refresh}>Retry now</button>
        </section>
      ) : loading && !lastUpdated ? (
        <p className="notice" role="status">Loading desks…</p>
      ) : desks.length === 0 ? (
        <p className="notice" role="status">No desks are available.</p>
      ) : (
        <DeskDashboard desks={desks} lastUpdated={lastUpdated} />
      )}
    </main>
  );
}
