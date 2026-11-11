import assert from 'node:assert/strict';
import { afterEach, it } from 'node:test';
import { getUnsyncedAnswers, saveAnswerOffline, syncOfflineBatch } from '../src/utils/offlineExam.ts';

const storage = new Map<string, string>();
Object.assign(globalThis, {
  localStorage: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  },
});
const originalFetch = globalThis.fetch;
afterEach(() => { storage.clear(); globalThis.fetch = originalFetch; });

it('keeps a newer edit pending while an older batch completes', async () => {
  await saveAnswerOffline(1, 2, { text_answer: 'old' });
  let finish!: (value: Response) => void;
  globalThis.fetch = () => new Promise((resolve) => { finish = resolve; });
  const syncing = syncOfflineBatch(1);
  while (!finish) await new Promise((resolve) => setTimeout(resolve, 0));
  await saveAnswerOffline(1, 2, { text_answer: 'new' });
  finish(new Response(JSON.stringify({ success: true, saved_count: 1 }), { status: 200 }));
  assert.equal((await syncing).success, true);
  assert.equal((await getUnsyncedAnswers(1))[0].text_answer, 'new');
});

it('keeps pending answers when the server does not acknowledge the whole batch', async () => {
  await saveAnswerOffline(1, 2, { text_answer: 'answer' });
  globalThis.fetch = async () => new Response(JSON.stringify({ success: true, saved_count: 0 }), { status: 200 });
  assert.equal((await syncOfflineBatch(1)).success, false);
  assert.equal((await getUnsyncedAnswers(1)).length, 1);
});
