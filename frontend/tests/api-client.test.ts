import test from 'node:test';
import assert from 'node:assert/strict';
import {
  makeRequestId,
  parseJsonSuccess,
  toApiError,
} from '../src/lib/httpClient.ts';

const tr = (k: string) => `TR:${k}`;

test('parseJsonSuccess rejects HTML 200 responses cleanly without SyntaxError', async () => {
  const res = new Response('<!doctype html><html><body>Login</body></html>', {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
  await assert.rejects(
    () => parseJsonSuccess(res, '/api/v1/school/groups/', 'GET', makeRequestId(), tr),
    (err: Error & { status?: number; requestId?: string }) => {
      assert.equal(err.message, 'TR:error_invalid_server_response');
      assert.ok(!err.message.includes('Unexpected token'));
      assert.ok(Boolean(err.requestId));
      return true;
    },
  );
});

test('parseJsonSuccess rejects HTML disguised with JSON content-type', async () => {
  const res = new Response('<!doctype html><html></html>', {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
  await assert.rejects(
    () => parseJsonSuccess(res, '/api/v1/school/groups/', 'GET', 'req-1', tr),
    (err: Error & { requestId?: string }) => {
      assert.equal(err.message, 'TR:error_invalid_server_response');
      assert.equal(err.requestId, 'req-1');
      return true;
    },
  );
});

test('parseJsonSuccess returns undefined for HTTP 204 and zero-byte responses', async () => {
  const r204 = new Response(null, { status: 204 });
  assert.equal(await parseJsonSuccess(r204, '/api/v1/school/groups/1/', 'DELETE', 'r1', tr), undefined);

  const rEmpty = new Response('', { status: 200, headers: { 'content-type': 'application/json' } });
  assert.equal(await parseJsonSuccess(rEmpty, '/api/v1/school/groups/1/', 'POST', 'r2', tr), undefined);
});

test('toApiError strips HTML on 500 and maps 403 / 409 / 429 cleanly', async () => {
  const r500 = new Response('<html><body>Traceback</body></html>', {
    status: 500,
    headers: { 'content-type': 'text/html' },
  });
  const e500 = await toApiError(r500, '/api/v1/school/groups/', 'POST', 'r500', tr);
  assert.equal(e500.status, 500);
  assert.equal(e500.message, 'TR:error_server_failed');
  assert.ok(!e500.message.includes('Traceback'));

  const r409 = new Response('{}', {
    status: 409,
    headers: { 'content-type': 'application/json' },
  });
  const e409 = await toApiError(r409, '/api/v1/school/groups/', 'POST', 'r409', tr);
  assert.equal(e409.status, 409);
  assert.equal(e409.message, 'TR:error_conflict');
});
