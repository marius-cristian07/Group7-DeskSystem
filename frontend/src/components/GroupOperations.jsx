import { useEffect, useRef, useState } from 'react';
import { acknowledgeWarning, cancelGroup } from '../api/groupOperations';

export const isWarning = op => ['pending_warning', 'countdown'].includes(op.state);
export const isMovingGroup = op => ['dispatching', 'monitoring'].includes(op.state);

const phase = {
  pending_warning: 'Waiting for warning acknowledgements', countdown: 'Movement countdown',
  dispatching: 'Sending commands', monitoring: 'Tracking desk movement',
  completed: 'Targets reached', partial_failure: 'Partially completed', failed: 'Movement failed',
  blocked: 'Movement blocked', cancelled: 'Movement cancelled',
};

function clockTime(value) {
  return new Date(value).toLocaleTimeString();
}

function Warning({ op, stale, names, updated }) {
  const cancelButton = useRef(null);
  const cancelling = useRef(false);
  const [pending, setPending] = useState(false);
  const [cancelMessage, setCancelMessage] = useState('');
  const [ackFailed, setAckFailed] = useState(false);
  const id = op.operation_id;
  const lastRead = useRef(updated);
  useEffect(() => { lastRead.current = updated; }, [updated]);

  // Confirm only a mounted warning whose cancel control is visible in a foreground tab.
  // Heartbeats stop when it scrolls out of sight, becomes stale or leaves the warning phase.
  useEffect(() => {
    if (stale) return;
    let visible = false;
    let disposed = false;
    let sending = false;
    async function confirmVisible() {
      if (!visible || document.visibilityState !== 'visible' || sending || disposed) return;
      if (Date.now() - lastRead.current.getTime() > 5000) return;
      sending = true;
      try {
        await acknowledgeWarning(id);
        if (!disposed) setAckFailed(false);
      } catch (error) {
        if (!disposed) setAckFailed(error.status !== 409);
      } finally {
        sending = false;
      }
    }
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting && entry.intersectionRatio >= 0.5;
      if (visible) confirmVisible();
    }, { threshold: 0.5 });
    observer.observe(cancelButton.current);
    const timer = setInterval(confirmVisible, 2000);
    document.addEventListener('visibilitychange', confirmVisible);
    return () => {
      disposed = true;
      observer.disconnect();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', confirmVisible);
    };
  }, [id, stale]);

  async function cancel() {
    if (cancelling.current) return;
    cancelling.current = true;
    setPending(true);
    try {
      await cancelGroup(id);
      setCancelMessage('Cancellation confirmed.');
    } catch (error) {
      setCancelMessage(`Could not confirm cancellation. ${error.message}`);
    } finally {
      cancelling.current = false;
      setPending(false);
    }
  }

  return (
    <article className="group-warning" aria-label={`Movement warning for ${op.target_position_mm} mm`}>
      <div className="group-row">
        <div>
          <div className="group-kicker">Movement warning</div>
          <h2>{op.reason} · {op.target_position_mm} mm</h2>
        </div>
        <button ref={cancelButton} className="cancel-movement" onClick={cancel}
          disabled={pending || !op.cancellable}>{pending ? 'Cancelling…' : 'Cancel movement'}</button>
      </div>
      <p>{op.desk_ids.map(id => names[id] ? `${names[id]} (${id})` : id).join(', ')}</p>
      {stale ? <strong>Warning status is stale. Countdown unavailable.</strong> :
        op.state === 'countdown'
          ? <strong>{Math.ceil(op.seconds_remaining)} seconds remaining · Deadline {clockTime(op.warning_deadline)}</strong>
          : <strong>{op.message} Acknowledge by {clockTime(op.acknowledgement_deadline)}.</strong>}
      {ackFailed && <p role="alert">Dashboard acknowledgement failed. Reconnecting…</p>}
      {cancelMessage && <p role="status">{cancelMessage}</p>}
    </article>
  );
}

export function WarningPanel({ feed, names }) {
  const warnings = feed.operations.filter(isWarning);
  return (
    <section id="movement-warnings" className="warning-stack" aria-label="Movement warnings">
      {feed.error && <p className="notice notice--error" role="alert">
        {feed.updated ? `Group status is stale. Last update ${feed.updated.toLocaleTimeString()}.`
          : 'Group status is unavailable.'} Reconnecting…
      </p>}
      {warnings.map(op => <Warning key={op.operation_id} op={op} stale={Boolean(feed.error)}
        names={names} updated={feed.updated} />)}
    </section>
  );
}

export function OperationProgress({ operations, names }) {
  const progress = operations.filter(op => !isWarning(op));
  if (!progress.length) return null;
  return (
    <section className="group-progress" aria-label="Group movement progress">
      <h2>Group movements</h2>
      {progress.map(op => (
        <article key={op.operation_id}>
          <div className="group-row">
            <h3>{phase[op.state] || op.state} · {op.target_position_mm} mm</h3>
            <small>{clockTime(op.created_at)}</small>
          </div>
          <p>{op.reason}</p>
          <p>{op.blocked_message || op.message}</p>
          <ul>{op.desks.map(desk => (
            <li key={desk.desk_id}>
              <strong>{names[desk.desk_id] || desk.desk_id}</strong>
              {names[desk.desk_id] && <> ({desk.desk_id})</>} · {desk.result.replaceAll('_', ' ')}
              {desk.last_position_mm != null && <> · {desk.last_position_mm} mm</>}
              <div>{desk.detail}</div>
            </li>
          ))}</ul>
        </article>
      ))}
    </section>
  );
}
