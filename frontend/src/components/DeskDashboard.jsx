// The desk grid: one card per desk, a summary line, and the details dialog for the
// card that was pressed. desks comes from useDesks (S3-3) through App.
//
// This is a grid, not a floor plan. The backend does not report where desks are, so
// the cards stay in the order the backend returns them and their position on the
// screen means nothing about the office.

import { useState } from 'react';
import { summarize } from '../utils/deskStatus';
import DeskCard from './DeskCard';
import DeskDetails from './DeskDetails';

export default function DeskDashboard({ desks, lastUpdated }) {
  // Remember the ID, not the desk object: the object is replaced at every refresh.
  const [selectedId, setSelectedId] = useState(null);
  const counts = summarize(desks);

  return (
    <section className="dashboard" aria-labelledby="desk-grid-title">
      <h2 id="desk-grid-title">
        Desk grid <span className="tag">Preliminary view</span>
      </h2>
      <p className="dashboard__note">
        Cards are listed in the order the backend returns the desks. Their positions do not show
        where the desks are in the office, because the API has no desk locations yet.
      </p>

      <ul className="summary" aria-label="Summary">
        <li>{counts.total} desk{counts.total === 1 ? '' : 's'}</li>
        <li className="summary__moving">{counts.moving} moving</li>
        <li className="summary__error">{counts.error} with an error</li>
      </ul>

      <ul className="desk-grid" aria-label="Desks">
        {/* The ID lets React match cards across refreshes. */}
        {desks.map((desk) => (
          <DeskCard key={desk.desk_id} desk={desk} onSelect={setSelectedId} />
        ))}
      </ul>

      {selectedId !== null && (
        <DeskDetails
          deskId={selectedId}
          desk={desks.find((desk) => desk.desk_id === selectedId)}
          lastUpdated={lastUpdated}
          onClose={() => setSelectedId(null)}
        />
      )}
    </section>
  );
}
