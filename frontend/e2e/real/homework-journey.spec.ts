import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Critical journey against the REAL backend (no route mocks):
 * teacher creates a group, adds students, takes attendance, builds a
 * 20-question test, publishes and assigns it → student starts from the
 * website, answers, refreshes, resumes, submits → authoritative result →
 * teacher roster shows the real grade → exactly one Telegram result card is
 * queued in the outbox (never sent: the worker is disabled).
 */

const API = 'http://127.0.0.1:8000';
const PASSWORD = 'E2e-Journey-2026!';
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

type Tokens = { access: string; refresh: string };
type Login = { tokens: Tokens; user: { id: number } };

async function login(request: APIRequestContext, email: string): Promise<Login> {
  const r = await request.post(`${API}/api/auth/login/`, { data: { email, password: PASSWORD } });
  expect(r.status(), await r.text()).toBe(200);
  return r.json();
}

function auth(tok: string) {
  return { Authorization: `Bearer ${tok}` };
}

function djangoShell(code: string): string {
  const py = process.env.E2E_PYTHON || 'python';
  return execFileSync(py, ['manage.py', 'shell', '--no-imports', '-c', code], {
    cwd: REPO,
    env: { ...process.env, DJANGO_SETTINGS_MODULE: 'config.settings.e2e' },
  }).toString().trim();
}

async function asUser(page: Page, tokens: Tokens) {
  await page.addInitScript(([a, r]) => {
    sessionStorage.setItem('lms_access', a);
    sessionStorage.setItem('lms_refresh', r);
    localStorage.setItem('lms_lang', 'uz');
  }, [tokens.access, tokens.refresh]);
}

async function answer(page: Page, index: number, optionIndex: number) {
  const q = page.locator('fieldset.cd-question').nth(index);
  await q.scrollIntoViewIfNeeded();
  await q.locator('label.cd-option').nth(optionIndex).click();
}

test.describe.configure({ mode: 'serial' });

for (const viewport of [{ name: 'desktop', width: 1280, height: 800, touch: false }, { name: 'mobile 390', width: 390, height: 844, touch: true }]) {
test(`teacher → student → result → teacher → one queued notification (real backend, ${viewport.name})`, async ({ browser, request }) => {
  const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, hasTouch: viewport.touch });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const stamp = Date.now();

  // ---------------- teacher (real API) ----------------
  const teacher = await login(request, 'e2e-teacher@example.test');
  const s1 = await login(request, 'e2e-student1@example.test');
  const s2 = await login(request, 'e2e-student2@example.test');
  const outsider = await login(request, 'e2e-outsider@example.test');
  const T = auth(teacher.tokens.access);

  const group = await (await request.post(`${API}/api/v1/school/groups/`, { headers: T, data: { name: `Journey ${stamp}`, subject: 'english' } })).json();
  const members = await request.post(`${API}/api/v1/school/groups/${group.id}/members/`, { headers: T, data: { add: [s1.user.id, s2.user.id] } });
  expect(members.status()).toBe(200);
  // Cross-center student cannot be added.
  const foreign = await request.post(`${API}/api/v1/school/groups/${group.id}/members/`, { headers: T, data: { add: [outsider.user.id] } });
  expect(foreign.status()).toBe(400);

  // Attendance: open register, everyone present, finalize.
  const ses = await (await request.post(`${API}/api/v1/school/attendance/sessions/`, { headers: T, data: { group_id: group.id } })).json();
  const sheet = await (await request.get(`${API}/api/v1/school/attendance/sessions/${ses.session.id}/`, { headers: T })).json();
  const present = await request.post(`${API}/api/v1/school/attendance/sessions/${ses.session.id}/mark-all-present/`, { headers: T, data: { revision: sheet.revision } });
  expect(present.status(), await present.text()).toBe(200);
  const afterPresent = await (await request.get(`${API}/api/v1/school/attendance/sessions/${ses.session.id}/`, { headers: T })).json();
  const fin = await request.post(`${API}/api/v1/school/attendance/sessions/${ses.session.id}/finalize/`, { headers: T, data: { revision: afterPresent.revision } });
  expect(fin.status(), await fin.text()).toBe(200);

  // Test Builder: 20 questions, answer A each time.
  const questions = Array.from({ length: 20 }, (_, i) => ({
    number: i + 1, text: `Q${i + 1}: 2+${i}=?`, options: [String(2 + i), String(3 + i), String(4 + i), String(5 + i)], answer: 'A',
  }));
  const built = await (await request.post(`${API}/api/v1/teacher/studio/tests/`, {
    headers: T, data: { title: `Journey 20Q ${stamp}`, subject: 'english', time_limit_minutes: 30, blocks: [{ type: 'mcq', section: 'GENERAL', title: 'Part 1', questions }] },
  })).json();
  const testId = built.test.id;
  expect((await request.post(`${API}/api/v1/teacher/studio/tests/${testId}/publish/`, { headers: T })).status()).toBe(200);
  const assigned = await request.post(`${API}/api/v1/teacher/studio/tests/${testId}/assign/`, {
    headers: T, data: { group_id: group.id, due_at: new Date(Date.now() + 86_400_000).toISOString(), max_attempts: 1 },
  });
  expect(assigned.status(), await assigned.text()).toBe(201);
  const homeworkId: number = (await assigned.json()).assignment.id;

  // ---------------- unauthorized probes ----------------
  const O = auth(outsider.tokens.access);
  for (const action of ['start', 'save', 'submit']) {
    const r = await request.post(`${API}/api/v1/school/student/homeworks/${homeworkId}/${action}/`, { headers: O, data: { answers: { x: 1 } } });
    expect(r.status(), action).toBe(404);
  }
  expect((await request.get(`${API}/api/v1/school/student/homeworks/${homeworkId}/`, { headers: O })).status()).toBe(404);
  expect(djangoShell(`from apps.courses.models import HomeworkSubmission as H; print(H.objects.filter(homework_id=${homeworkId}).count())`)).toBe('0');

  // ---------------- student on the website ----------------
  await asUser(page, s1.tokens);
  await page.goto('/my-homework');
  const card = page.locator('div', { has: page.getByRole('heading', { name: `Journey 20Q ${stamp}` }) }).filter({ has: page.getByRole('button', { name: /Boshlash/ }) }).last();
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: /Boshlash/ }).click();
  await expect(page).toHaveURL(new RegExp(`/tests/${testId}`));
  await page.getByRole('button', { name: /Testni boshlash|Davom ettirish/ }).first().click();
  await page.getByRole('button', { name: /Practice/ }).click();
  await expect(page).toHaveURL(/\/english-exam\/\d+/);
  const runnerUrl = page.url();

  for (let i = 0; i < 10; i++) await answer(page, i, 0);
  await expect(page.getByText(/Saqlandi/).first()).toBeVisible();
  await expect.poll(() => djangoShell(
    `from apps.tests.models import StudentAnswer as A; print(A.objects.filter(attempt__test_id=${testId}, attempt__student_id=${s1.user.id}).count())`,
  ), { timeout: 20_000 }).toBe('10');

  // Refresh → resume with saved answers.
  await page.reload();
  await expect(page).toHaveURL(runnerUrl);
  await expect(page.locator('fieldset.cd-question').nth(0).locator('input:checked')).toHaveCount(1);
  await expect(page.locator('fieldset.cd-question').nth(9).locator('input:checked')).toHaveCount(1);

  // Network interruption while answering: the answer must still reach the server.
  await page.context().setOffline(true);
  await answer(page, 10, 0);
  await page.waitForTimeout(1500);
  await page.context().setOffline(false);
  await expect.poll(() => djangoShell(
    `from apps.tests.models import StudentAnswer as A; print(A.objects.filter(attempt__test_id=${testId}, attempt__student_id=${s1.user.id}).count())`,
  ), { timeout: 30_000 }).toBe('11');

  for (let i = 11; i < 19; i++) await answer(page, i, 0);
  await answer(page, 19, 1); // one wrong answer → 19/20
  await expect.poll(() => djangoShell(
    `from apps.tests.models import StudentAnswer as A; print(A.objects.filter(attempt__test_id=${testId}, attempt__student_id=${s1.user.id}).count())`,
  ), { timeout: 20_000 }).toBe('20');

  await page.getByRole('button', { name: /^Topshirish$|^Yakunlash$/ }).first().click();
  const confirm = page.getByRole('dialog').getByRole('button', { name: /Topshirish|Yakunlash|Ha/ });
  if (await confirm.count()) await confirm.first().click();

  // ---------------- authoritative result ----------------
  await expect.poll(async () => {
    const r = await request.get(`${API}/api/v1/school/student/homeworks/${homeworkId}/result/`, { headers: auth(s1.tokens.access) });
    return r.status() === 200 ? (await r.json()).score_display : `http ${r.status()}`;
  }, { timeout: 30_000 }).toBe('19.00/20.00');

  await page.goto('/my-homework');
  const done = page.locator('div', { has: page.getByRole('heading', { name: `Journey 20Q ${stamp}` }) }).filter({ has: page.getByRole('button', { name: /Natijani ko'rish/ }) }).last();
  await expect(done.getByText('Baholandi')).toBeVisible();
  await done.getByRole('button', { name: /Natijani ko'rish/ }).click();
  await expect(page.getByText('19.00/20.00').first()).toBeVisible();

  // ---------------- teacher sees the real grade ----------------
  const roster = await (await request.get(`${API}/api/v1/school/teacher/homeworks/${homeworkId}/roster/`, { headers: T })).json();
  const rows = Object.fromEntries(roster.students.map((r: { student_id: number }) => [r.student_id, r]));
  expect(rows[s1.user.id].status).toBe('graded');
  expect(rows[s1.user.id].score).toBe(95);
  expect(rows[s2.user.id].status).toBe('not_started');
  expect(roster.summary).toMatchObject({ total_students: 2, submitted: 1, graded: 1 });

  // ---------------- exactly one queued result card, not sent ----------------
  expect(djangoShell(
    `from apps.notifications.models import OutboxMessage as O; q=O.objects.filter(event='homework_result', payload__homework_id=${homeworkId}); print(q.count(), q.first().recipient_id, q.first().status)`,
  )).toBe(`1 ${s1.user.id} pending`);

  // A second finish attempt is idempotent and queues nothing new.
  const again = await request.post(`${API}/api/v1/school/student/homeworks/${homeworkId}/submit/`, { headers: auth(s1.tokens.access), data: {} });
  expect(again.status()).toBe(200);
  expect(djangoShell(
    `from apps.notifications.models import OutboxMessage as O; print(O.objects.filter(event='homework_result', payload__homework_id=${homeworkId}).count())`,
  )).toBe('1');

  expect(errors).toEqual([]);
  await context.close();
});
}

for (const width of [320, 360, 375, 390, 430, 768, 1280]) {
  test(`my-homework has no horizontal overflow at ${width}px (real data)`, async ({ page, request }) => {
    const s1 = await login(request, 'e2e-student1@example.test');
    await page.setViewportSize({ width, height: 900 });
    await asUser(page, s1.tokens);
    await page.goto('/my-homework');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const [scrollW, innerW] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(scrollW).toBeLessThanOrEqual(innerW);
    // Primary actions are touch-sized on phones.
    if (width < 768) {
      for (const box of await page.getByRole('button', { name: /Boshlash|Natijani ko'rish|Davom ettirish/ }).evaluateAll(
        (els) => els.map((e) => e.getBoundingClientRect().height),
      )) expect(box).toBeGreaterThanOrEqual(36);
    }
  });
}
