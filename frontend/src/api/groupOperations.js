import { getJson } from './desks.js';

const path = '/api/group-operations';

export async function listOperations(signal) {
  const operations = await getJson(path, { signal, cache: 'no-store' });
  if (!Array.isArray(operations)) throw new Error('Invalid group operation list.');
  return operations;
}

function post(route, body) {
  return getJson(path + route, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  });
}

export function createGroup(deskIds, target) {
  return post('', { desk_ids: deskIds, target_position_mm: target });
}

export function acknowledgeWarning(id) {
  return post(`/${encodeURIComponent(id)}/acknowledge`, { channel: 'dashboard' });
}

export function cancelGroup(id) {
  return post(`/${encodeURIComponent(id)}/cancel`);
}
