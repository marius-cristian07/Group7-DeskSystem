// Everything the backend reports about one desk, in a modal dialog.
// It uses the browser's own <dialog>, which closes on Escape, keeps keyboard focus
// inside, and returns focus to the card that opened it. On a phone it is shown as
// a sheet at the bottom of the screen (see dashboard.css).
//
// desk is looked up from the latest refresh, so the values here stay current while
// the dialog is open. It is undefined when the desk is missing from that refresh.

import { useEffect, useRef } from 'react';
import { getDeskState, getMovement } from '../utils/deskStatus';
import StateBadge from './StateBadge';
import DeskHistory from './DeskHistory';

export default function DeskDetails({ deskId, desk, lastUpdated, onClose }) {
  const dialogRef = useRef(null);

  // Open as a modal as soon as the component appears. Closing the dialog through
  // close() fires its "close" event, which tells the dashboard to forget the selection.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog && dialog.open) dialog.close();
    };
  }, []);

  const close = () => dialogRef.current?.close();
  const movement = desk ? getMovement(desk) : null;

  return (
    <dialog
      ref={dialogRef}
      className="desk-dialog"
      aria-labelledby="desk-dialog-title"
      onClose={onClose}
      // The dark area outside the panel is the dialog element itself, so a click
      // whose target is the dialog (not something inside it) is a click outside.
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="desk-dialog__body">
        <header className="desk-dialog__header">
          <div>
            <h2 id="desk-dialog-title">{desk ? desk.name : 'Desk unavailable'}</h2>
            <p className="desk-id">{deskId}</p>
          </div>
          <button type="button" className="desk-dialog__close" onClick={close} aria-label="Close details">
            ×
          </button>
        </header>

        {desk ? (
          <>
            <StateBadge state={getDeskState(desk)} movement={movement} />

            <dl className="detail-list">
              <div>
                <dt>Height</dt>
                <dd>{desk.position_mm} mm</dd>
              </div>
              <div>
                <dt>Movement</dt>
                <dd>
                  {movement.direction === 'none'
                    ? movement.label
                    : `${movement.label} at ${movement.speed} mm/s`}
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{desk.status}</dd>
              </div>
              <div>
                <dt>Anti-collision</dt>
                <dd>{desk.is_anti_collision ? 'Active' : 'Not active'}</dd>
              </div>
            </dl>

            {/* Saved history (S4-4). It loads on its own, so if the history service fails,
                the live details above keep working. */}
            <DeskHistory key={deskId} deskId={deskId} deskName={desk.name} />

            <h3>Recent errors</h3>
            {desk.last_errors.length === 0 ? (
              <p>No recent errors reported.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th scope="col">Error code</th>
                    <th scope="col">Simulator time</th>
                  </tr>
                </thead>
                <tbody>
                  {desk.last_errors.map((entry, index) => (
                    <tr key={`${entry.time_s}-${entry.errorCode}-${index}`}>
                      <td>{entry.errorCode}</td>
                      <td>{entry.time_s} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="desk-dialog__note">
              This is a history list from the simulator, and its times are the simulator's own
              seconds, not clock times. Whether the desk has a problem now is shown by Status
              and Anti-collision above.
            </p>
            {lastUpdated && (
              <p className="desk-dialog__note">Data updated at {lastUpdated.toLocaleTimeString()}.</p>
            )}
          </>
        ) : (
          <p role="status">
            Details for this desk are not available right now. It may be powered off, or the
            connection to the backend was lost. They will appear here again when the desk reports in.
          </p>
        )}
      </div>
    </dialog>
  );
}
