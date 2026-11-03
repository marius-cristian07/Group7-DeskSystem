// Checks for the dashboard's display rules. Run with `npm test` in frontend/.
// Uses Node's built-in test runner, so no extra packages are needed.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DESK_STATE, getDeskState, getMovement, hasError, summarize } from './deskStatus.js';

// A desk as returned by GET /api/desks, with overrides for each case.
const desk = (overrides = {}) => ({
  desk_id: 'cd:fb:1a:53:fb:e6',
  name: 'DESK 4486',
  position_mm: 872,
  speed_mms: 0,
  status: 'Normal',
  is_anti_collision: false,
  last_errors: [],
  ...overrides,
});

test('a stopped desk with status Normal is idle', () => {
  assert.equal(getDeskState(desk()), DESK_STATE.IDLE);
});

test('a positive speed is moving up and a negative speed is moving down', () => {
  assert.deepEqual(getMovement(desk({ speed_mms: 32 })), { direction: 'up', speed: 32, label: 'Moving up' });
  assert.deepEqual(getMovement(desk({ speed_mms: -32 })), { direction: 'down', speed: 32, label: 'Moving down' });
  assert.equal(getDeskState(desk({ speed_mms: -32 })), DESK_STATE.MOVING);
});

test('a status other than Normal is an error, whatever its capitalisation', () => {
  assert.equal(getDeskState(desk({ status: 'Collision' })), DESK_STATE.ERROR);
  assert.equal(getDeskState(desk({ status: 'something new' })), DESK_STATE.ERROR);
  assert.equal(hasError(desk({ status: 'NORMAL' })), false);
});

test('the anti-collision flag is an error even when the status says Normal', () => {
  assert.equal(getDeskState(desk({ is_anti_collision: true })), DESK_STATE.ERROR);
});

test('a problem outranks movement', () => {
  assert.equal(getDeskState(desk({ status: 'Collision', speed_mms: 32 })), DESK_STATE.ERROR);
});

test('old entries in last_errors do not make a healthy desk an error', () => {
  const history = [{ time_s: 120, errorCode: 93 }];
  assert.equal(getDeskState(desk({ last_errors: history })), DESK_STATE.IDLE);
});

test('a missing or unreadable speed counts as stationary', () => {
  assert.equal(getMovement(desk({ speed_mms: undefined })).direction, 'none');
  assert.equal(getMovement(desk({ speed_mms: 'fast' })).direction, 'none');
});

test('summarize counts each state and the total', () => {
  const desks = [
    desk(),
    desk({ speed_mms: 32 }),
    desk({ speed_mms: -32 }),
    desk({ status: 'Collision' }),
  ];
  assert.deepEqual(summarize(desks), { total: 4, moving: 2, error: 1, idle: 1 });
  assert.deepEqual(summarize([]), { total: 0, moving: 0, error: 0, idle: 0 });
});
