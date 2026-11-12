// The history section of the desk details (S4-4): a height-over-time chart and a table
// of recorded movement requests, with a time-range choice and a Refresh button.
//
// The chart and the table are loaded and shown separately (see useDeskHistory), and each
// has its own message for: loading, no history yet, nothing in the selected period, and
// the history service being unavailable. A failure here stays inside this section. The
// live desk details above it, and the dashboard behind the dialog, keep working.
//
// DeskDetails renders this with key={deskId}, and the hook only returns data that matches
// the desk it was asked about, so one desk's history is never shown under another's name.

import { useId, useState } from 'react';
import { useDeskHistory } from '../hooks/useDeskHistory';
import { DEFAULT_RANGE_ID, HISTORY_RANGES, formatClock, formatDateTime, getRange } from '../utils/historyRules';
import CommandTable from './CommandTable';
import HeightChart from './HeightChart';
import '../history.css';

// A short line that says why a list is not showing, in the same place the list would be.
function Message({ children, error = false }) {
  return (
    <div className={`history__state${error ? ' history__state--error' : ''}`} role={error ? 'alert' : 'status'}>
      {children}
    </div>
  );
}

function Notice({ children, error = false }) {
  return <p className={`history__notice${error ? ' history__notice--error' : ''}`}>{children}</p>;
}

// Shown above a list when some of its rows were left out or could not be read.
function ListNotices({ part, newest, what, range }) {
  const { prepared } = part;
  return (
    <>
      {part.refreshError && (
        <Notice error>
          Could not refresh this list ({part.refreshError}). Showing what was loaded at {formatClock(part.fetchedAt.getTime(), true)}.
        </Notice>
      )}
      {prepared.truncated && (
        <Notice>
          Showing only the newest {prepared.limit} {what} {range.phrase}{newest}. Older ones in this period are not shown.
        </Notice>
      )}
      {prepared.skipped > 0 && (
        <Notice>{prepared.skipped} {what} could not be read and {prepared.skipped === 1 ? 'is' : 'are'} not shown.</Notice>
      )}
    </>
  );
}

function ReadingsPanel({ part, range }) {
  switch (part.status) {
    case 'loading':
      return <Message>Loading height history…</Message>;
    case 'none-yet':
      return (
        <Message>
          <strong>No history yet.</strong> No readings have been saved for this desk. They appear here
          once the backend has saved some.
        </Message>
      );
    case 'none-in-period':
      return (
        <Message>
          <strong>No readings {range.phrase}.</strong>{' '}
          {part.latestAt !== null && <>The latest saved reading is from {formatDateTime(part.latestAt)}.</>}
        </Message>
      );
    case 'unavailable':
      return (
        <Message error>
          <strong>Height history is unavailable right now.</strong> The live details above still work.
          Select Refresh to try again.
          <span className="history__detail">{part.message}</span>
        </Message>
      );
    default: {
      const { prepared } = part;
      const from = formatDateTime(prepared.domain.start);
      return (
        <>
          <ListNotices part={part} what="readings" range={range} newest={` (from ${from})`} />
          <HeightChart prepared={prepared} />
        </>
      );
    }
  }
}

function CommandsPanel({ part, range }) {
  switch (part.status) {
    case 'loading':
      return <Message>Loading movement requests…</Message>;
    case 'none-yet':
      return <Message><strong>No movement requests yet.</strong> None have been recorded for this desk.</Message>;
    case 'none-in-period':
      return (
        <Message>
          <strong>No movement requests {range.phrase}.</strong>{' '}
          {part.latestAt !== null && <>The latest recorded request is from {formatDateTime(part.latestAt)}.</>}
        </Message>
      );
    case 'unavailable':
      return (
        <Message error>
          <strong>Movement requests are unavailable right now.</strong> The live details above still
          work. Select Refresh to try again.
          <span className="history__detail">{part.message}</span>
        </Message>
      );
    default:
      return (
        <>
          <ListNotices part={part} what="requests" range={range} newest="" />
          <CommandTable prepared={part.prepared} />
        </>
      );
  }
}

export default function DeskHistory({ deskId, deskName }) {
  const [rangeId, setRangeId] = useState(DEFAULT_RANGE_ID);
  const { readings, commands, refresh } = useDeskHistory(deskId, rangeId);
  const range = getRange(rangeId);
  const headingId = useId();

  // The newest time at which either list was loaded successfully.
  const loadedTimes = [readings, commands]
    .map((part) => part.fetchedAt)
    .filter(Boolean)
    .map((date) => date.getTime());
  const updatedAt = loadedTimes.length > 0 ? Math.max(...loadedTimes) : null;

  return (
    <section className="history" aria-labelledby={headingId}>
      <h3 id={headingId}>History for {deskName}</h3>

      <div className="history__controls">
        <div className="range-picker" role="group" aria-label="Time range">
          {HISTORY_RANGES.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={option.id === rangeId}
              onClick={() => setRangeId(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button type="button" className="history__refresh" onClick={() => { void refresh(); }}>
          Refresh
        </button>
      </div>
      <p className="history__updated">
        {updatedAt !== null ? <>Updated at {formatClock(updatedAt, true)}. </> : null}
        Reloads about every 15 seconds.
      </p>

      <h4>Height over time</h4>
      <ReadingsPanel part={readings} range={range} />

      <h4>Movement requests</h4>
      <CommandsPanel part={commands} range={range} />
    </section>
  );
}
