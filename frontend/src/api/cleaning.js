import { getJson } from './desks.js';

const path = '/api/cleaning-schedules';

export async function getCleaningSchedules(signal) {
  // these reads are independent so they can run together
  const [settings, schedules, history] = await Promise.all([
    getJson(`${path}/settings`, { signal }),
    getJson(path, { signal }),
    getJson(`${path}/runs`, { signal }),
  ]);
  return { ...settings, schedules, runs: history.runs };
}

export function saveCleaningSchedule(id, schedule) {
  // a new schedule has no id yet
  return getJson(id == null ? path : `${path}/${id}`, {
    method: id == null ? 'POST' : 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(schedule),
  });
}

export function disableCleaningSchedule(id) {
  // this leaves the current run and its return alone
  return getJson(`${path}/${id}/disable`, { method: 'POST' });
}
