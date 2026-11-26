// Keep group warnings mounted even while live desk readings are unavailable.

import RecoveryPanel from './components/RecoveryPanel';
import { useCleaningSchedules } from './hooks/useCleaningSchedules';
import { useSavedResource } from './hooks/useSavedResource';
import DeskDashboard from './components/DeskDashboard';
import CleaningSchedules from './components/CleaningSchedules';
import { useDesks } from './hooks/useDesks';
import './dashboard.css';
import './group-control.css';

export default function App() {
  // These values update together when a request starts, succeeds, or fails.
  const { desks, loading, error, lastUpdated, refresh } = useDesks();

  const catalogue = useSavedResource('/api/stored-desks');
  const cleaning = useCleaningSchedules();
  return (
    <main className="app">
      <header className="app__header">
        <h1>Desk System</h1>
        <a className="recovery-link" href="#recovery-title">Faults and recovery</a>
        {/* Keep the update time visible while a background refresh is running.
            lastUpdated distinguishes the first load from a background refresh. */}
        <p className="app__updated">
          {lastUpdated && !error && <>Updated at {lastUpdated.toLocaleTimeString()}</>}
          {loading && lastUpdated && !error && <span role="status"> · Refreshing…</span>}
        </p>
      </header>
      {error && (
        <section className="notice notice--error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={refresh}>Retry now</button>
        </section>
      )}
      {!error && loading && !lastUpdated ? (
        <p className="notice" role="status">Loading desks…</p>
      ) : !error && desks.length === 0 ? (
        <p className="notice" role="status">No desks are available.</p>
      ) : null}
      <DeskDashboard catalogue={catalogue} desks={desks} lastUpdated={lastUpdated} liveError={error} />
      <RecoveryPanel catalogue={catalogue.data?.desks} liveError={error} lastUpdated={lastUpdated} desks={desks} runs={cleaning.data?.runs} />
      <CleaningSchedules feed={cleaning} desks={desks} desksUnavailable={Boolean(error) || !lastUpdated} />
    </main>
  );
}
