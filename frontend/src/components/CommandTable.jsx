// The movement-request table (S4-4): when each request was recorded, the height asked
// for, and the outcome that was recorded. An accepted request is never described as a
// completed movement. It only means the simulator took the request, and the wording
// comes from describeOutcome in utils/historyRules.js.

import { describeOutcome, formatDateTime } from '../utils/historyRules';

export default function CommandTable({ prepared }) {
  // Explain only the outcomes that actually appear in the table.
  const kinds = new Map();
  for (const row of prepared.rows) {
    const outcome = describeOutcome(row.status);
    if (!kinds.has(outcome.kind)) kinds.set(outcome.kind, outcome);
  }

  return (
    <>
      {/* The wrapper scrolls when the list is long; tabIndex lets the keyboard scroll it. */}
      <div className="history-table" role="region" aria-label="Movement requests, newest first" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Requested at</th>
              <th scope="col">Target</th>
              <th scope="col">Recorded outcome</th>
            </tr>
          </thead>
          <tbody>
            {prepared.rows.map((row) => {
              const outcome = describeOutcome(row.status);
              return (
                <tr key={row.id ?? `${row.iso}-${row.target}`}>
                  <td><time dateTime={row.iso}>{formatDateTime(row.t)}</time></td>
                  <td>{row.target} mm</td>
                  <td>
                    <span className={`outcome outcome--${outcome.kind}`} title={outcome.detail}>
                      <span aria-hidden="true">{outcome.symbol}</span> {outcome.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ul className="history-meanings">
        {[...kinds.values()].map((outcome) => (
          <li key={outcome.kind}>
            <strong>{outcome.label}:</strong> {outcome.detail}
          </li>
        ))}
      </ul>
      <p className="desk-dialog__note">
        To see what the desk really did after a request, check the height chart above.
      </p>
    </>
  );
}
