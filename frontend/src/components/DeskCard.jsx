// The details button and group checkbox are independent keyboard targets.

import { getDeskState, getMovement } from '../utils/deskStatus';
import StateBadge from './StateBadge';

export default function DeskCard({ desk, onSelect, selected, onToggle, locked, unavailable, detailsDisabled }) {
  const state = getDeskState(desk);
  const movement = getMovement(desk);

  return (
    <li className={selected ? 'group-selected' : ''}>
      <button
        type="button"
        className={`desk-card desk-card--${state}`}
        aria-haspopup="dialog"
        disabled={detailsDisabled}
        onClick={() => onSelect(desk.desk_id)}
      >
        <span className="desk-card__head">
          <span className="desk-card__name">{desk.name}</span>
          <StateBadge state={state} movement={movement} />
        </span>
        <span className="desk-card__id">{desk.desk_id}</span>
        <span className="desk-card__height">
          <span className="desk-card__value">{desk.position_mm}</span> mm
        </span>
        <span className="desk-card__line">Status: <strong>{desk.status}</strong></span>
        {desk.is_anti_collision && <span className="desk-card__line">Anti-collision active</span>}
        <span className="desk-card__line">
          {movement.direction === 'none' ? movement.label : `${movement.label} · ${movement.speed} mm/s`}
        </span>
      </button>
      <label className="desk-select">
        <input type="checkbox" checked={selected} onChange={onToggle}
          disabled={locked || (Boolean(unavailable) && !selected)}
          aria-label={`Select ${desk.name} (${desk.desk_id})`} />
        {unavailable || 'Select for group'}
      </label>
    </li>
  );
}
