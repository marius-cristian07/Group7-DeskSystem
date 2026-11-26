// Display rules for the dashboard (S3-4): turn the backend's desk fields into
// the three states a card can show. There is no React in this file, so the rules
// can be read and tested on their own (run `npm test` in frontend/).

export const DESK_STATE = Object.freeze({
  ERROR: 'error',
  MOVING: 'moving',
  IDLE: 'idle',
});

// Prefer the backend's current classification. Historical errors never block movement.
export function hasError(desk) {
  const status = String(desk.status ?? '').trim().toLowerCase();
  return (desk.health != null && desk.health !== 'healthy') || Boolean(desk.fault_codes?.length)
    || desk.is_anti_collision === true || status !== 'normal';
}

/** Direction and speed from the signed `speed_mms` (positive = up, negative = down). */
export function getMovement(desk) {
  const speed = Number(desk.speed_mms);
  if (speed > 0) return { direction: 'up', speed, label: 'Moving up' };
  if (speed < 0) return { direction: 'down', speed: Math.abs(speed), label: 'Moving down' };
  return { direction: 'none', speed: 0, label: 'Stationary' };
}

/** The one state that decides a card's colour. A problem outranks movement. */
export function getDeskState(desk) {
  if (hasError(desk)) return DESK_STATE.ERROR;
  return getMovement(desk).direction === 'none' ? DESK_STATE.IDLE : DESK_STATE.MOVING;
}

/** Counts for the summary line above the grid. */
export function summarize(desks) {
  const counts = { total: desks.length, moving: 0, error: 0, idle: 0 };
  for (const desk of desks) counts[getDeskState(desk)] += 1;
  return counts;
}
