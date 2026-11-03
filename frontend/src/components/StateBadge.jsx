// A small label for a desk's state. It uses a word and a symbol as well as a
// colour, so the state is still clear to people who cannot tell the colours apart.
// Used by both the card (DeskCard) and the details dialog (DeskDetails).

import { DESK_STATE } from '../utils/deskStatus';

const LABELS = {
  [DESK_STATE.ERROR]: 'Error',
  [DESK_STATE.MOVING]: 'Moving',
  [DESK_STATE.IDLE]: 'Idle',
};

function getSymbol(state, movement) {
  if (state === DESK_STATE.ERROR) return '!';
  if (state === DESK_STATE.MOVING) return movement.direction === 'up' ? '▲' : '▼';
  return '●';
}

export default function StateBadge({ state, movement }) {
  return (
    <span className={`badge badge--${state}`}>
      {/* The symbol is decoration; the word next to it carries the meaning. */}
      <span aria-hidden="true">{getSymbol(state, movement)}</span> {LABELS[state]}
    </span>
  );
}
