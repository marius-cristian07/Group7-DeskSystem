export default function StoredDesks({ catalogue, desks, lastUpdated, liveError, onSelect, disabled }) {
  const { data, error } = catalogue;
  const online = new Set(desks.map(desk => desk.desk_id));
  return <details className="recovery">
    <summary>Stored desk history</summary>
    {error ? <p role="alert">{error}</p> : !data ? <p>Loading stored desks…</p> :
      !data.desks.length ? <p>No desk history has been saved.</p> :
      <ul className="stored-list">{data.desks.map(desk => {
        const saved = desk.last_reading_at && new Date(desk.last_reading_at);
        const stale = saved && Date.now() - saved.getTime() > 120000;
        const live = liveError ? 'Live data unavailable' : !lastUpdated ? 'Checking live availability' :
          online.has(desk.desk_id) ? 'Online' : 'Desk offline';
        return <li key={desk.desk_id}>
          <button disabled={disabled} onClick={() => onSelect(desk.desk_id)}>{desk.name} · {desk.desk_id}</button>
          <span>{live} · {saved ? `Last saved reading ${saved.toLocaleString()}${stale ? ' · Stale (over 2 minutes old)' : ''}` : 'No saved readings'}</span>
        </li>;
      })}</ul>}
  </details>;
}
