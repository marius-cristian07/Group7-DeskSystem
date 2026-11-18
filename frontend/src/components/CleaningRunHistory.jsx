import { formatOccurrence, runLabel, runProblems } from '../utils/cleaningSchedule';
import { isWarning } from './GroupOperations';

// use the existing warning panel for the countdown and cancellation
export default function CleaningRunHistory({ runs, timezone, stale }) {
  return (
    <section aria-labelledby="cleaning-runs-title">
      <h3 id="cleaning-runs-title">Run progress and history</h3>
      <p>Cancel a current movement in the <a href="#movement-warnings">shared movement warnings</a> above.
        This affects the current occurrence. Disabling a schedule affects future starts and keeps an authorized current return.</p>
      <p>Cancelling a return warning can leave desks raised. Inspect their positions before arranging a safe return.</p>
      {!runs.length && <p>No cleaning runs have been reported.</p>}
      {runs.map((run) => {
        const problems = runProblems(run);
        const runTimezone = run.timezone || timezone;
        const needsAttention = problems.length > 0 || ['blocked', 'cancelled', 'needs_review'].includes(run.status);
        let badge = 'moving';
        if (run.status === 'completed') badge = 'idle';
        if (needsAttention) badge = 'error';
        return (
          <article key={run.run_id} className="cleaning-panel" aria-label={`Cleaning run ${run.run_id}`}>
            <div className="cleaning-heading">
              <h4>{run.schedule_name}</h4>
              <span className={`badge badge--${badge}`}>
                {runLabel(run)}
              </span>
            </div>
            <p>Run {run.run_id} · Occurrence date: {run.occurrence_date}</p>
            {run.raise_requested_at && <p>Raise requested: {formatOccurrence(run.raise_requested_at, runTimezone)}</p>}
            {run.return_requested_at && <p>Return requested: {formatOccurrence(run.return_requested_at, runTimezone)}</p>}
            {run.status === 'needs_review' && <p className="cleaning-error">This run needs review. Movement may be incomplete or uncertain. Inspect desk positions and the operation results; no automatic retry is planned.</p>}
            {problems.length > 0 && <p className="cleaning-error"><strong>{problems.length} desk result{problems.length === 1 ? '' : 's'} did not confirm success.</strong> Review the results below.</p>}
            {(run.operations || []).map((operation) => (
              <details key={operation.operation_id} open={['partial_failure', 'failed', 'blocked', 'unavailable'].includes(operation.state)}>
                <summary>{operation.phase === 'return' ? 'Return' : 'Raise'} group operation {operation.operation_id}: {operation.state.replaceAll('_', ' ')}</summary>
                <p>{operation.blocked_message || operation.message}</p>
                {isWarning(operation) && <p><a href="#movement-warnings">View the shared warning and cancel this movement</a>. Cancelling affects this occurrence; the future schedule stays enabled.</p>}
                {operation.state === 'unavailable' && <p>Operation details are no longer available in server memory. The stored operation ID is retained for review.</p>}
                <ul>{operation.desks.map(desk => (
                  <li key={desk.desk_id}>
                    {desk.desk_id}: {desk.result.replaceAll('_', ' ')}
                    {desk.last_position_mm != null && <> ({desk.last_position_mm} mm)</>}
                    <p>{desk.detail}</p>
                  </li>
                ))}</ul>
              </details>
            ))}
            {!run.operations?.length && <p>No group operation has been reported yet.</p>}
            {stale && <p>Monitoring is stale; refresh to confirm this run’s current state.</p>}
          </article>
        );
      })}
    </section>
  );
}
