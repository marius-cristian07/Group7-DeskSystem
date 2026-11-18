// The desk grid: one card per desk, a summary line, and the details dialog for the
// card that was pressed. desks comes from useDesks (S3-3) through App.
//
// This is a grid, not a floor plan. The backend does not report where desks are, so
// the cards stay in the order the backend returns them and their position on the
// screen means nothing about the office.

import { useState, useEffect } from 'react';
import { summarize, hasError } from '../utils/deskStatus';
import { useGroupOperations } from '../hooks/useGroupOperations';
import GroupHeightControl from './GroupHeightControl';
import { WarningPanel, OperationProgress, isWarning, isMovingGroup } from './GroupOperations';
import DeskCard from './DeskCard';
import DeskDetails from './DeskDetails';

export default function DeskDashboard({ desks, lastUpdated }) {
  // Remember the ID, not the desk object: the object is replaced at every refresh.
  const [selectedId, setSelectedId] = useState(null);
  const [groupIds, setGroupIds] = useState([]);
  const [locked, setLocked] = useState(false);
  const [names, setNames] = useState({});
  const feed = useGroupOperations();
  const hasWarning = feed.operations.some(isWarning);
  const reserved = new Set(feed.operations.filter(op => isWarning(op) || isMovingGroup(op)).flatMap(op => op.desk_ids));
  const ready = Boolean(lastUpdated && feed.updated && !feed.error);
  const available = desks.filter(desk => !hasError(desk) && !reserved.has(desk.desk_id)).map(desk => desk.desk_id);
  const offline = Object.keys(names).filter(id => !desks.some(desk => desk.desk_id === id));
  const counts = summarize(desks);
  useEffect(() => {
    if (desks.length) setNames(previous => ({
      ...previous, ...Object.fromEntries(desks.map(desk => [desk.desk_id, desk.name])),
    }));
  }, [desks]);
  useEffect(() => {
    if (hasWarning) setSelectedId(null);
  }, [hasWarning]);

  function toggle(id) {
    setGroupIds(ids => ids.includes(id) ? ids.filter(other => other !== id) : [...ids, id]);
  }

  return (
    <section className="dashboard" aria-labelledby="desk-grid-title">
      <WarningPanel feed={feed} names={names} />
      <GroupHeightControl selected={groupIds} names={names} available={available} ready={ready}
        onSelect={setGroupIds} locked={locked} onLock={setLocked} />
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
          <DeskCard key={desk.desk_id} desk={desk} onSelect={setSelectedId} detailsDisabled={hasWarning}
            selected={groupIds.includes(desk.desk_id)} onToggle={() => toggle(desk.desk_id)}
            locked={locked} unavailable={availabilityLabel(desk, ready, reserved)} />
        ))}
      </ul>
      {offline.length > 0 && <p>{lastUpdated ? 'Offline' : 'Availability unconfirmed'}: {offline.map(id => `${names[id]} (${id})`).join(', ')}</p>}
      <OperationProgress operations={feed.operations} names={names} />

      {selectedId !== null && !hasWarning && (
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

function availabilityLabel(desk, ready, reserved) {
  if (!ready) return 'Availability unconfirmed';
  if (hasError(desk)) return 'Unavailable · desk error';
  if (reserved.has(desk.desk_id)) return 'Unavailable · group in progress';
  return '';
}
