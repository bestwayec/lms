import { test, expect, type APIRequestContext, type Page, type Browser } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Real Django → React scenarios (no API mocks) for the multi-tenant /
 * classroom-access / Smart Import 7.0 requirements:
 *   A  separate learning centers stay isolated
 *   C  PowerPoint import through the editor (slides, table, notes, key slide)
 *   D  scanned (image-only) PDF is refused with guidance
 *   E  FREE group member takes an assigned private test with no paywall;
 *      an unrelated FREE user is blocked
 *   F  a PRO outsider gets only explicitly published paid-catalog tests
 */

const API = 'http://127.0.0.1:8000';
const PASSWORD = 'E2e-Journey-2026!';
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const FX = process.env.E2E_FIXTURES || '/tmp/e2e-fixtures';

type Tokens = { access: string; refresh: string };
type Login = { tokens: Tokens; user: { id: number } };

function py(args: string[]): string {
  return execFileSync(process.env.E2E_PYTHON || 'python', args, {
    cwd: REPO,
    env: { ...process.env, DJANGO_SETTINGS_MODULE: 'config.settings.e2e' },
  }).toString().trim();
}
function shell(code: string): string {
  return py(['manage.py', 'shell', '--no-imports', '-c', code]);
}

test.beforeAll(() => {
  py(['-m', 'tests.import_fixtures', FX]);
  py(['-c', `import sys; sys.path.insert(0, '.'); from tests.import_fixtures import pdf_bytes; open('${FX}/scan.pdf','wb').write(pdf_bytes(image_only=True))`]);
});

async function login(request: APIRequestContext, email: string): Promise<Login> {
  const r = await request.post(`${API}/api/auth/login/`, { data: { email, password: PASSWORD } });
  expect(r.status(), email).toBe(200);
  return r.json();
}
const auth = (t: Tokens) => ({ Authorization: `Bearer ${t.access}` });

async function pageAs(browser: Browser, tokens: Tokens, width = 1280): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width, height: 860 }, hasTouch: width < 768 });
  const page = await ctx.newPage();
  await page.addInitScript(([a, r]) => {
    sessionStorage.setItem('lms_access', a);
    sessionStorage.setItem('lms_refresh', r);
    localStorage.setItem('lms_lang', 'uz');
  }, [tokens.access, tokens.refresh]);
  return page;
}

/** Teacher A: group with student1, a private published 3-question Ona tili test, assigned as homework. */
async function classroom(request: APIRequestContext, stamp: number) {
  const teacher = await login(request, 'e2e-teacher@example.test');
  const member = await login(request, 'e2e-student1@example.test');
  const T = auth(teacher.tokens);
  const group = await (await request.post(`${API}/api/v1/school/groups/`, { headers: T, data: { name: `Class ${stamp}`, subject: 'uzbek' } })).json();
  expect((await request.post(`${API}/api/v1/school/groups/${group.id}/members/`, { headers: T, data: { add: [member.user.id] } })).status()).toBe(200);
  const questions = [1, 2, 3].map((n) => ({ number: n, text: `${n}. savol`, options: ['a', 'b', 'c', 'd'], answer: 'A' }));
  const built = await (await request.post(`${API}/api/v1/teacher/studio/tests/`, {
    headers: T, data: { title: `Attestatsiya ${stamp}`, subject: 'uzbek', time_limit_minutes: 20, blocks: [{ type: 'mcq', section: 'GENERAL', title: 'Imlo', questions }] },
  })).json();
  const testId: number = built.test.id;
  expect((await request.post(`${API}/api/v1/teacher/studio/tests/${testId}/publish/`, { headers: T })).status()).toBe(200);
  const assigned = await (await request.post(`${API}/api/v1/teacher/studio/tests/${testId}/assign/`, {
    headers: T, data: { group_id: group.id, due_at: new Date(Date.now() + 86_400_000).toISOString() },
  })).json();
  return { teacher, member, group, testId, homeworkId: assigned.assignment.id as number };
}

const attempts = (testId: number, email: string) =>
  shell(`from apps.tests.models import TestAttempt as A; print(A.objects.filter(test_id=${testId}, student__email='${email}').count())`);

// --------------------------------------------------------------------------- A

test('Scenario A: Center B admin/teacher/student cannot read or change Center A records', async ({ request }) => {
  const c = await classroom(request, Date.now());
  const adminB = await login(request, 'e2e-admin-b@example.test');
  const teacherB = await login(request, 'e2e-teacher-b@example.test');
  const studentB = await login(request, 'e2e-outsider@example.test');
  const adminA = await login(request, 'e2e-owner@example.test');
  const reads = [
    `/api/v1/school/groups/${c.group.id}/`,
    `/api/v1/school/groups/${c.group.id}/members/`,
    `/api/v1/school/groups/${c.group.id}/analytics/`,
    `/api/v1/school/teacher/homeworks/${c.homeworkId}/roster/`,
    `/api/v1/school/teacher/homeworks/${c.homeworkId}/live/`,
    `/api/v1/teacher/studio/tests/${c.testId}/`,
    `/api/v1/school/student/homeworks/${c.homeworkId}/`,
  ];
  for (const who of [adminB, teacherB, studentB]) {
    for (const url of reads) {
      const r = await request.get(`${API}${url}`, { headers: auth(who.tokens) });
      expect(r.status(), `${url}`).toBeGreaterThanOrEqual(400);
    }
  }
  // Center B teacher cannot assign Center A's private test or add A's student.
  const tb = auth(teacherB.tokens);
  const gB = await (await request.post(`${API}/api/v1/school/groups/`, { headers: tb, data: { name: `B ${Date.now()}`, subject: 'uzbek' } })).json();
  expect((await request.post(`${API}/api/v1/teacher/studio/tests/${c.testId}/assign/`, { headers: tb, data: { group_id: gB.id, due_at: new Date(Date.now() + 86_400_000).toISOString() } })).status()).toBeGreaterThanOrEqual(400);
  expect((await request.post(`${API}/api/v1/school/groups/${gB.id}/members/`, { headers: tb, data: { add: [c.member.user.id] } })).status()).toBe(400);
  expect(shell(`from apps.courses.models import Homework; print(Homework.objects.filter(test_id=${c.testId}).count())`)).toBe('1');
  // Positive control: Center A's own admin reads Center A's group.
  expect((await request.get(`${API}/api/v1/school/groups/${c.group.id}/`, { headers: auth(adminA.tokens) })).status()).toBe(200);
});

// --------------------------------------------------------------------------- E

test('Scenario E: FREE group member takes the assigned private test with no paywall; FREE outsider blocked', async ({ browser, request }) => {
  const c = await classroom(request, Date.now());
  const outsider = await login(request, 'e2e-outsider@example.test');

  // Outsider: direct start and direct URL both refused, nothing created.
  const start = await request.post(`${API}/api/v1/tests/${c.testId}/start/`, { headers: auth(outsider.tokens), data: { mode: 'practice' } });
  expect(start.status()).toBe(403);
  expect(attempts(c.testId, 'e2e-outsider@example.test')).toBe('0');
  const op = await pageAs(browser, outsider.tokens, 390);
  await op.goto(`/tests/${c.testId}`);
  await expect(op.getByRole('button', { name: /Testni boshlash/ })).toHaveCount(0);
  await op.context().close();

  // Member (FREE): from /my-homework into the runner, no paywall, twice (resume).
  const before = shell(`from apps.payments.models import SubscriptionUsage as U; print(U.objects.filter(user__email='e2e-student1@example.test').count())`);
  const mp = await pageAs(browser, c.member.tokens, 390);
  await mp.goto('/my-homework');
  await mp.locator(`[data-homework-id="${c.homeworkId}"]`).getByRole('button', { name: /Boshlash/ }).click();
  await mp.getByRole('button', { name: /Testni boshlash|Davom ettirish/ }).first().click();
  const practice = mp.getByRole('button', { name: /Practice/ });
  if (await practice.isVisible().catch(() => false)) await practice.click();
  await expect(mp).toHaveURL(/\/(english-exam|take)\/\d+/);
  await expect(mp.getByText(/tarif bilan ochiladi|Tariflarni ko'rish/)).toHaveCount(0);
  await mp.goto(`/tests/${c.testId}`);
  await mp.getByRole('button', { name: /Testni boshlash|Davom ettirish/ }).first().click();
  if (await practice.isVisible().catch(() => false)) await practice.click();
  await expect(mp).toHaveURL(/\/(english-exam|take)\/\d+/);
  await expect(mp.getByText(/tarif bilan ochiladi|Tariflarni ko'rish/)).toHaveCount(0);
  expect(attempts(c.testId, 'e2e-student1@example.test')).toBe('1');
  const after = shell(`from apps.payments.models import SubscriptionUsage as U; print(U.objects.filter(user__email='e2e-student1@example.test').count())`);
  expect(after).toBe(before); // classroom work consumed no FREE quota
  await mp.context().close();
});

// --------------------------------------------------------------------------- F

test('Scenario F: PRO outsider — private test refused, explicitly published paid-catalog test allowed', async ({ request }) => {
  const c = await classroom(request, Date.now());
  const pro = await login(request, 'e2e-pro-outsider@example.test');
  const free = await login(request, 'e2e-outsider@example.test');
  const startAs = (who: Login) => request.post(`${API}/api/v1/tests/${c.testId}/start/`, { headers: auth(who.tokens), data: { mode: 'practice' } });

  expect((await startAs(pro)).status()).toBe(403); // a subscription never overrides private ownership
  // Teacher explicitly publishes the test to the paid catalog.
  shell(`from apps.tests.models import Test; Test.objects.filter(id=${c.testId}).update(access_type='PUBLIC', audience_mode='GROUP_AND_SUBSCRIBERS')`);
  const ok = await startAs(pro);
  expect([200, 201]).toContain(ok.status());
  expect((await startAs(free)).status()).toBe(403); // FREE outsider still refused
  expect(attempts(c.testId, 'e2e-outsider@example.test')).toBe('0');
});

// --------------------------------------------------------------------------- C / D

test('Scenario C: PowerPoint import — slides, table questions, notes key, image-only warning, then fix keys and publish', async ({ browser, request }) => {
  const teacher = await login(request, 'e2e-teacher@example.test');
  const page = await pageAs(browser, teacher.tokens, 1280);
  await page.goto('/teacher/studio/new');
  await page.getByPlaceholder('Masalan: Reading Mock 3').fill(`PPTX ${Date.now()}`);
  await page.locator('main select').first().selectOption('uzbek');
  await page.getByRole('button', { name: /Keyingisi: Savollar/ }).click();
  await page.getByRole('tab', { name: 'Fayldan yuklash' }).click();
  await page.locator('input[type=file]').setInputFiles(path.join(FX, 'ona_tili_12.pptx'));
  const report = page.getByRole('list', { name: 'Import hisoboti' });
  await expect(report).toContainText('To‘liq savollar: 9');
  await expect(report).toContainText('Javob kaliti yo‘q: 3');
  const preview = page.locator('.studio-file-import');
  await expect(preview).toContainText('Slaydda faqat rasm bor');
  await expect(preview.getByRole('columnheader', { name: 'Slayd' })).toBeVisible();
  const table = page.getByRole('table', { name: 'Aniqlangan savollar' });
  await expect(table.getByRole('row')).toHaveCount(13); // header + 12 questions, nothing hidden
  await expect(table.getByRole('row', { name: /Sintaksis nimani o‘rganadi\?/ })).toContainText('12');
  await expect(preview).not.toContainText('darsda tushuntiring'); // notes commentary not imported
  await page.getByRole('button', { name: 'Tasdiqlash' }).click();
  await page.getByRole('tab', { name: 'Javoblar kaliti' }).click();
  for (const n of [10, 11, 12]) {
    await page.getByRole('radiogroup', { name: new RegExp(`\\b${n}$`) }).getByRole('radio', { name: 'A' }).click();
  }
  await page.getByRole('button', { name: /Keyingisi: Tekshirish/ }).click();
  await page.getByRole('button', { name: /^E'lon qilish$/ }).first().click();
  await expect(page.getByRole('button', { name: 'Biriktirish' })).toBeVisible();
  await page.context().close();
});

test('Scenario D: a scanned (image-only) PDF is refused with guidance, nothing imported', async ({ browser, request }) => {
  const teacher = await login(request, 'e2e-teacher@example.test');
  const page = await pageAs(browser, teacher.tokens, 1280);
  await page.goto('/teacher/studio/new');
  await page.getByPlaceholder('Masalan: Reading Mock 3').fill(`Scan ${Date.now()}`);
  await page.getByRole('button', { name: /Keyingisi: Savollar/ }).click();
  await page.getByRole('tab', { name: 'Fayldan yuklash' }).click();
  await page.locator('input[type=file]').setInputFiles(path.join(FX, 'scan.pdf'));
  await expect(page.locator('.studio-file-import [role=alert]')).toContainText('skaner');
  await expect(page.getByRole('list', { name: 'Import hisoboti' })).toHaveCount(0);
  await page.context().close();
});
