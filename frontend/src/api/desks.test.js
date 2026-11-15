// Unit tests for the frontend's backend API client.

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { getDesk, getDesks, getHealth, getJson } from './desks.js';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function response(body, { status = 200, ok = status >= 200 && status < 300 } = {}) {
  return {
    ok,
    status,
    async json() {
      return body;
    },
  };
}

const sampleDesk = {
  desk_id: 'cd:fb:1a:53:fb:e6',
  name: 'DESK 4486',
  position_mm: 680,
  speed_mms: 0,
  status: 'Normal',
  is_anti_collision: false,
  last_errors: [],
};

test('getHealth requests the backend health endpoint', async () => {
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return response({ status: 'ok' });
  };

  assert.deepEqual(await getHealth(), { status: 'ok' });
  assert.equal(requestedUrl, 'http://127.0.0.1:8080/api/health');
});

test('getDesks returns the desk array from the backend', async () => {
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return response([sampleDesk]);
  };

  assert.deepEqual(await getDesks(), [sampleDesk]);
  assert.equal(requestedUrl, 'http://127.0.0.1:8080/api/desks');
});

test('getDesks accepts an empty array', async () => {
  globalThis.fetch = async () => response([]);
  assert.deepEqual(await getDesks(), []);
});

test('getDesks rejects a response that is not an array', async () => {
  globalThis.fetch = async () => response({ desks: [sampleDesk] });
  await assert.rejects(getDesks(), /invalid desk list/i);
});

test('getDesk encodes desk IDs before adding them to the URL', async () => {
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return response(sampleDesk);
  };

  assert.deepEqual(await getDesk('desk/with spaces'), sampleDesk);
  assert.equal(
    requestedUrl,
    'http://127.0.0.1:8080/api/desks/desk%2Fwith%20spaces',
  );
});

test('HTTP errors expose the backend detail and status code', async () => {
  globalThis.fetch = async () => response(
    { detail: 'Desk not found' },
    { status: 404, ok: false },
  );

  await assert.rejects(
    getJson('/api/desks/missing'),
    (error) => error.status === 404 && /Desk not found/.test(error.message),
  );
});

test('network failures become a readable backend connection error', async () => {
  globalThis.fetch = async () => {
    throw new TypeError('socket details');
  };

  await assert.rejects(
    getHealth(),
    /Cannot connect to the Python backend/,
  );
});

test('invalid JSON becomes a readable response error', async () => {
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    async json() {
      throw new SyntaxError('not JSON');
    },
  });

  await assert.rejects(
    getHealth(),
    /invalid response \(HTTP 200\)/i,
  );
});

test('AbortError is not converted into a connection error', async () => {
  const abortError = new Error('aborted');
  abortError.name = 'AbortError';
  globalThis.fetch = async () => {
    throw abortError;
  };

  await assert.rejects(getHealth(), (error) => error === abortError);
});
