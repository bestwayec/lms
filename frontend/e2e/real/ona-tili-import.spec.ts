import { test, expect, type APIRequestContext, type Page, type Browser } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Real backend, real UI (no route mocks).
 * A: Ona tili teacher imports 20 questions from DOCX, corrects a wrong key,
 *    publishes, assigns; the student completes; the teacher sees the result.
 * C: Exam Runner 4.0 — no chemistry tools, navigate, refresh, resume, finish.
 * D: the runner in uz/ru/en keeps the Uzbek questions exactly as authored.
 * E: teacher flow at 360px, student at 390px, no horizontal overflow.
 * Fixtures come from tests/import_fixtures.py (Q20's key is deliberately wrong).
 */

const API = 'http://127.0.0.1:8000';
const PASSWORD = 'E2e-Journey-2026!';
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const FX = process.env.E2E_FIXTURES || '/tmp/e2e-fixtures';
// Correct keys; the DOCX carries D for Q20, the right answer is A.
const KEYS = 'BBBABAABAAABAAAAAAAA'.split('');

type Tokens = { access: string; refresh: string };
type Login = { tokens: Tokens; user: { id: number } };

function py(args: string[]): string {
  return execFileSync(process.env.E2E_PYTHON || 'python', args, {
    cwd: REPO,
    env: { ...process.env, DJANGO_SETTINGS_MODULE: 'config.settings.e2e' },
  }).toString().trim();
}

test.beforeAll(() => {
  py(['-m', 'tests.import_fixtures', FX]);
});

async function login(request: APIRequestContext, email: string): Promise<Login> {
  const r = await request.post(`${API}/api/auth/login/`, { data: { email, password: PASSWORD } });
  expect(r.status()).toBe(200);
  return r.json();
}

async function pageAs(browser: Browser, tokens: Tokens, width: number, lang = 'uz'): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width, height: 860 }, hasTouch: width < 768 });
  const page = await ctx.newPage();
  await page.addInitScript(([a, r, l]) => {
    sessionStorage.setItem('lms_access', a);
    sessionStorage.setItem('lms_refresh', r);
    localStorage.setItem('lms_lang', l);
  }, [tokens.access, tokens.refresh, lang]);
  return page;
}

function optionByText(page: Page, text: string, qNum?: number, total?: number) {
  // Scope to the card of the current question: during the slide transition the
  // previous card is briefly still in the DOM.
  const card = qNum
    ? page.locator('.take-test-card').filter({ hasText: `Savollar ${qNum}/${total}` })
    : page.locator('.take-test-card');
  return card.locator('.exam-opt').filter({ has: page.locator('.exam-opt-text', { hasText: new RegExp(`^${text}$`) }) });
}

async function noOverflow(page: Page) {
  const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(sw).toBeLessThanOrEqual(iw);
}

async function teacherImportsPublishesAssigns(page: Page, title: string, groupId: number) {
  await page.goto('/teacher/studio/new');
  await page.getByPlaceholder('Masalan: Reading Mock 3').fill(title);
  await page.locator('main select').first().selectOption('uzbek');
  await noOverflow(page);
  await page.getByRole('button', { name: /Keyingisi: Savollar/ }).click();
  await page.getByRole('tab', { name: 'Fayldan yuklash' }).click();
  await page.locator('input[type=file]').setInputFiles(path.join(FX, 'ona_tili_20.docx'));
  const report = page.getByRole('list', { name: 'Import hisoboti' });
  await expect(report).toContainText('To‘liq savollar: 20');
  await expect(report).toContainText('Javob kaliti yo‘q: 0');
  // Unicode preserved exactly in the preview.
  await expect(page.locator('.studio-file-import')).toContainText('“O‘tkan kunlar” romani muallifi kim?');
  await noOverflow(page);
  await page.getByRole('button', { name: 'Tasdiqlash' }).click();
  // Correct the wrong key (D → A) in the answer matrix.
  await page.getByRole('tab', { name: 'Javoblar kaliti' }).click();
  const q20 = page.getByRole('radiogroup', { name: /20$/ });
  await expect(q20.getByRole('radio', { name: 'D' })).toHaveAttribute('aria-checked', 'true');
  await q20.getByRole('radio', { name: 'A' }).click();
  await expect(q20.getByRole('radio', { name: 'A' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: /Keyingisi: Tekshirish/ }).click();
  await page.getByRole('button', { name: /^E'lon qilish$/ }).first().click();
  await expect(page.getByRole('button', { name: 'Biriktirish' })).toBeVisible();
  await page.getByRole('button', { name: 'Biriktirish' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('select').selectOption(String(groupId));
  const due = new Date(Date.now() + 2 * 86_400_000);
  const local = new Date(due.getTime() - due.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  await dialog.locator('input[type=datetime-local]').fill(local);
  await noOverflow(page);
  const assigned = page.waitForResponse((r) => r.url().includes('/assign/') && r.request().method() === 'POST');
  await dialog.getByRole('button', { name: /Biriktirish|Topshiriq berish|Yuborish/ }).last().click();
  expect((await assigned).status()).toBe(201);
}


for (const teacherWidth of [1280, 360]) {
  test(`Scenario A/E: Ona tili DOCX import → correct key → publish → assign → student 20/20 (teacher ${teacherWidth}px)`, async ({ browser, request }) => {
    const stamp = Date.now();
    const title = `Ona tili DOCX ${stamp}`;
    const groupName = `Ona tili 9-A ${stamp}`;
    const teacher = await login(request, 'e2e-teacher@example.test');
    const student = await login(request, 'e2e-student1@example.test');
    const T = { Authorization: `Bearer ${teacher.tokens.access}` };
    const group = await (await request.post(`${API}/api/v1/school/groups/`, { headers: T, data: { name: groupName, subject: 'uzbek' } })).json();
    expect((await request.post(`${API}/api/v1/school/groups/${group.id}/members/`, { headers: T, data: { add: [student.user.id] } })).status()).toBe(200);

    // ---------------- teacher, UI only ----------------
    const tp = await pageAs(browser, teacher.tokens, teacherWidth);
    const errors: string[] = [];
    tp.on('pageerror', (e) => errors.push(e.message));
    await teacherImportsPublishesAssigns(tp, title, group.id);
    await tp.context().close();

    // ---------------- student at 390px ----------------
    const sp = await pageAs(browser, student.tokens, 390);
    sp.on('pageerror', (e) => errors.push(e.message));
    await sp.goto('/my-homework');
    const card = sp.locator('div', { has: sp.getByRole('heading', { name: title }) }).filter({ has: sp.getByRole('button', { name: /Boshlash/ }) }).last();
    await card.getByRole('button', { name: /Boshlash/ }).click();
    await sp.getByRole('button', { name: /Testni boshlash|Davom ettirish/ }).first().click();
    const practice = sp.getByRole('button', { name: /Practice/ });
    if (await practice.isVisible().catch(() => false)) await practice.click();
    // Studio tests have section/part structure and run on the CD/BMB kiosk engine (by design, any subject).
    await expect(sp).toHaveURL(/\/english-exam\/\d+/);
    const runnerUrl = sp.url();
    const countAnswers = () => py(['manage.py', 'shell', '--no-imports', '-c',
      `from apps.tests.models import StudentAnswer as A; print(A.objects.filter(attempt__test__title=${JSON.stringify(title)}).count())`]);

    // Focus kiosk: no app nav, no chemistry tools; Uzbek text exactly as authored.
    await expect(sp.locator('aside.sidebar')).toHaveCount(0);
    await expect(sp.getByRole('button', { name: /Mendeleyev|Eruvchanlik|Kalkulyator/ })).toHaveCount(0);
    await expect(sp.getByText('“O‘tkan kunlar” romani muallifi kim?')).toBeVisible();

    const pick = async (i: number) => {
      const q = sp.locator('fieldset.cd-question').nth(i);
      await q.scrollIntoViewIfNeeded();
      await q.locator('label.cd-option').nth('ABCD'.indexOf(KEYS[i])).click();
    };
    for (let i = 0; i < 10; i++) await pick(i);
    await noOverflow(sp);
    await expect.poll(countAnswers, { timeout: 20_000 }).toBe('10');
    // Refresh → resume with the 10 server-confirmed answers.
    await sp.reload();
    await expect(sp).toHaveURL(runnerUrl);
    for (const i of [0, 9]) {
      await expect(sp.locator('fieldset.cd-question').nth(i).locator('input:checked')).toHaveCount(1);
    }
    for (let i = 10; i < 20; i++) await pick(i);
    await expect.poll(countAnswers, { timeout: 20_000 }).toBe('20');
    await sp.getByRole('button', { name: /^Topshirish$|^Yakunlash$/ }).first().click();
    const confirm = sp.getByRole('dialog').getByRole('button', { name: /Topshirish|Yakunlash|Ha/ });
    if (await confirm.count()) await confirm.first().click();

    // ---------------- authoritative result ----------------
    const S = { Authorization: `Bearer ${student.tokens.access}` };
    await expect.poll(async () => {
      const list = await (await request.get(`${API}/api/v1/school/student/homeworks/`, { headers: S })).json();
      const hw = list.results.find((h: { title: string }) => h.title === title);
      return hw ? `${hw.status} ${hw.score_display}` : 'missing';
    }, { timeout: 30_000 }).toBe('graded 20.00/20.00'); // 20/20 only if the teacher's key fix was saved

    // ---------------- teacher sees it ----------------
    const list = await (await request.get(`${API}/api/v1/school/teacher/homeworks/`, { headers: T })).json();
    const hwId = list.results.find((h: { title: string }) => h.title === title).id;
    const roster = await (await request.get(`${API}/api/v1/school/teacher/homeworks/${hwId}/roster/`, { headers: T })).json();
    expect(roster.students.find((r: { student_id: number }) => r.student_id === student.user.id)).toMatchObject({ status: 'graded', score: 100 });
    await sp.context().close();
    expect(errors).toEqual([]);
  });
}

for (const [lang, exitLabel] of [['uz', 'Chiqish'], ['ru', 'Выйти'], ['en', 'Exit']] as const) {
  test(`Scenario D: runner in ${lang} keeps Uzbek questions exactly as authored`, async ({ browser, request }) => {
    const teacher = await login(request, 'e2e-teacher@example.test');
    const student = await login(request, 'e2e-student2@example.test');
    const T = { Authorization: `Bearer ${teacher.tokens.access}` };
    const text = 'Qaysi so‘zda tutuq belgisi to‘g‘ri yozilgan?';
    const built = await (await request.post(`${API}/api/v1/teacher/studio/tests/`, {
      headers: T, data: { title: `Lang ${lang} ${Date.now()}`, subject: 'uzbek', time_limit_minutes: 10,
        blocks: [{ type: 'mcq', section: 'GENERAL', title: 'Imlo', questions: [{ number: 1, text, options: ['ma’no', 'mano', 'ma‘no', 'ma-no'], answer: 'A' }] }] },
    })).json();
    await request.post(`${API}/api/v1/teacher/studio/tests/${built.test.id}/publish/`, { headers: T });
    const g = await (await request.post(`${API}/api/v1/school/groups/`, { headers: T, data: { name: `L ${lang} ${Date.now()}`, subject: 'uzbek' } })).json();
    await request.post(`${API}/api/v1/school/groups/${g.id}/members/`, { headers: T, data: { add: [student.user.id] } });
    const assign = await (await request.post(`${API}/api/v1/teacher/studio/tests/${built.test.id}/assign/`, { headers: T, data: { group_id: g.id, due_at: new Date(Date.now() + 86_400_000).toISOString() } })).json();
    // Teacher-assigned work starts through the homework layer (never the student's personal quota).
    const started = await (await request.post(`${API}/api/v1/school/student/homeworks/${assign.assignment.id}/start/`, { headers: { Authorization: `Bearer ${student.tokens.access}` } })).json();
    expect(started.attempt_id).toBeTruthy();
    const page = await pageAs(browser, student.tokens, 1280, lang);
    await page.goto(`/take/${started.attempt_id}`);
    await expect(page.getByText(text, { exact: false })).toBeVisible();
    await expect(page.locator('.take-test-card .exam-opt').nth(0)).toContainText('ma’no');
    await expect(page.getByRole('button', { name: exitLabel }).first()).toBeVisible();
    // Switching language mid-exam does not lose a selected answer.
    await page.locator('.take-test-card .exam-opt').nth(0).click();
    await page.evaluate(() => localStorage.setItem('lms_lang', 'en'));
    await page.reload();
    await expect(page.locator('.take-test-card .exam-opt').nth(0)).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByText(text, { exact: false })).toBeVisible();
    await page.context().close();
  });
}

test('Scenario C: legacy Ona tili test on /take — focus mode, one navigator, no tools, refresh/resume, finish', async ({ browser, request }) => {
  const stamp = Date.now();
  const title = `Ona tili legacy ${stamp}`;
  const teacher = await login(request, 'e2e-teacher@example.test');
  const student = await login(request, 'e2e-student2@example.test');
  // A test without section/part structure (bulk-import / converter style) — the /take runner.
  const testId = py(['manage.py', 'shell', '--no-imports', '-c', `
from apps.accounts.models import User
from apps.courses.models import Course
from apps.tests.models import Test, Question, Choice
t = User.objects.get(email='e2e-teacher@example.test')
c, _ = Course.objects.get_or_create(slug='e2e-legacy', defaults={'title': 'E2E legacy', 'teacher': t})
test = Test.objects.create(course=c, created_by=t, title=${JSON.stringify(title)}, subject='uzbek', status='published', is_active=True, time_limit_minutes=20, access_type='STUDENTS_ONLY', max_attempts=0)
for i in range(6):
    q = Question.objects.create(test=test, position=i + 1, text=f'{i+1}-savol: Qaysi so‘z to‘g‘ri yozilgan?', points=1, question_type='single')
    for j, opt in enumerate(['ma’no', 'mano', 'ma‘no', 'ma-no']):
        Choice.objects.create(question=q, text=opt, is_correct=(j == 0), position=j + 1)
print(test.id)`]);
  const T = { Authorization: `Bearer ${teacher.tokens.access}` };
  const g = await (await request.post(`${API}/api/v1/school/groups/`, { headers: T, data: { name: `C ${stamp}`, subject: 'uzbek' } })).json();
  await request.post(`${API}/api/v1/school/groups/${g.id}/members/`, { headers: T, data: { add: [student.user.id] } });
  const hw = await request.post(`${API}/api/v1/school/teacher/homeworks/`, {
    headers: T, data: { group_id: g.id, title, test_id: Number(testId), due_date: new Date(Date.now() + 86_400_000).toISOString() },
  });
  expect(hw.status(), await hw.text()).toBe(201);

  for (const width of [390, 1280]) {
    const sp = await pageAs(browser, student.tokens, width);
    const errors: string[] = [];
    sp.on('pageerror', (e) => errors.push(e.message));
    await sp.goto('/my-homework');
    const card = sp.locator('div', { has: sp.getByRole('heading', { name: title }) })
      .filter({ has: sp.getByRole('button', { name: /Boshlash|Davom ettirish/ }) }).last();
    await card.getByRole('button', { name: /Boshlash|Davom ettirish/ }).click();
    await sp.getByRole('button', { name: /Testni boshlash|Davom ettirish/ }).first().click();
    const practice = sp.getByRole('button', { name: /Practice/ });
    if (await practice.isVisible().catch(() => false)) await practice.click();
    await expect(sp).toHaveURL(/\/take\/\d+/);

    await expect(sp.locator('aside.sidebar')).toHaveCount(0);
    await expect(sp.getByRole('button', { name: /Mendeleyev|Eruvchanlik|Kalkulyator|Davriy/ })).toHaveCount(0);
    await expect(sp.getByText('SAVOLLAR XARITASI')).toHaveCount(0);
    await expect(sp.getByText('Variantni tanlang')).toHaveCount(0);
    await expect(sp.getByText('Matnli javob')).toHaveCount(0);
    await expect(sp.getByRole('button', { name: 'Keyingi savol' })).toHaveCount(1); // one navigator
    await noOverflow(sp);

    if (width === 390) {
      for (let i = 0; i < 3; i++) {
        const opt = optionByText(sp, 'ma’no', i + 1, 6);
        await opt.click();
        await expect(opt).toHaveAttribute('aria-pressed', 'true');
        await sp.getByRole('button', { name: 'Keyingi savol' }).click();
      }
      await expect.poll(() => py(['manage.py', 'shell', '--no-imports', '-c',
        `from apps.tests.models import StudentAnswer as A; print(A.objects.filter(attempt__test_id=${testId}).count())`]), { timeout: 20_000 }).toBe('3');
      await sp.reload();
      await expect(sp).toHaveURL(/\/take\/\d+/);
      for (let guard = 0; guard < 8; guard++) {
        const prev = sp.getByRole('button', { name: 'Oldingi savol' });
        if (await prev.isDisabled()) break;
        await prev.click();
      }
      // Options may be shuffled (stable per attempt): find the authored option by its text.
      await expect(optionByText(sp, 'ma’no')).toHaveAttribute('aria-pressed', 'true');
    } else {
      // Resume on desktop (same attempt): wait for the hydrated server state (3 saved)
      // before touching options — a second click on a picked option clears it.
      await expect(sp.getByText('3/6 ✓')).toBeVisible();
      // Finish the rest with one wrong answer → 5/6.
      for (let i = 0; i < 6; i++) {
        const opt = optionByText(sp, i === 5 ? 'mano' : 'ma’no', i + 1, 6);
        await expect(opt).toHaveCount(1);
        if ((await opt.getAttribute('aria-pressed')) !== 'true') await opt.click();
        await expect(opt).toHaveAttribute('aria-pressed', 'true');
        if (i < 5) await sp.getByRole('button', { name: 'Keyingi savol' }).click();
      }
      await expect.poll(() => py(['manage.py', 'shell', '--no-imports', '-c',
        `from apps.tests.models import StudentAnswer as A; print(A.objects.filter(attempt__test_id=${testId}).count())`]), { timeout: 20_000 }).toBe('6');
      await sp.getByRole('button', { name: 'Testni yakunlash' }).click();
      await sp.getByRole('button', { name: /Tasdiqlash/ }).last().click();
      const S = { Authorization: `Bearer ${student.tokens.access}` };
      await expect.poll(async () => {
        const list = await (await request.get(`${API}/api/v1/school/student/homeworks/`, { headers: S })).json();
        const h = list.results.find((x: { title: string }) => x.title === title);
        return h ? `${h.status} ${h.score_display}` : 'missing';
      }, { timeout: 30_000 }).toBe('graded 5.00/6.00');
    }
    expect(errors).toEqual([]);
    await sp.context().close();
  }
});

for (const file of ['ona_tili_20.csv', 'ona_tili_20.xlsx', 'ona_tili_20.pdf']) {
  test(`Scenario B: Smart Import of ${file} through the editor shows the real parsed content`, async ({ browser, request }) => {
    const teacher = await login(request, 'e2e-teacher@example.test');
    const page = await pageAs(browser, teacher.tokens, 1280);
    await page.goto('/teacher/studio/new');
    await page.getByPlaceholder('Masalan: Reading Mock 3').fill(`B ${file}`);
    await page.locator('main select').first().selectOption('uzbek');
    await page.getByRole('button', { name: /Keyingisi: Savollar/ }).click();
    await page.getByRole('tab', { name: 'Fayldan yuklash' }).click();
    await page.locator('input[type=file]').setInputFiles(path.join(FX, file));
    const report = page.getByRole('list', { name: 'Import hisoboti' });
    await expect(report).toContainText('To‘liq savollar: 20');
    const preview = page.locator('.studio-file-import');
    await expect(preview).toContainText('“O‘tkan kunlar” romani muallifi kim?');
    await expect(preview).toContainText('Abdulla Qodiriy');
    await page.getByRole('button', { name: 'Tasdiqlash' }).click();
    await page.getByRole('tab', { name: 'Javoblar kaliti' }).click();
    await expect(page.getByRole('radiogroup', { name: /\b2$/ }).getByRole('radio', { name: 'B' })).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByRole('radiogroup', { name: /20$/ }).getByRole('radio', { name: 'D' })).toHaveAttribute('aria-checked', 'true');
    await page.context().close();
  });
}

test('Scenario B: Smart Paste with Uzbek ‘ apostrophes and Cyrillic А/Б/В/Г options', async ({ browser, request }) => {
  const teacher = await login(request, 'e2e-teacher@example.test');
  const page = await pageAs(browser, teacher.tokens, 1280);
  await page.goto('/teacher/studio/new');
  await page.getByPlaceholder('Masalan: Reading Mock 3').fill('B paste');
  await page.getByRole('button', { name: /Keyingisi: Savollar/ }).click();
  await page.getByRole('tab', { name: 'Smart Paste' }).click();
  await page.getByRole('textbox', { name: 'Smart Paste' }).fill(
    '1. Qaysi gapda undalma mavjud?\nA) Bahor keldi.\nB) Do‘stim, kel!\nC) U o‘qidi.\nD) Kitob stolda.\nTo‘g‘ri javob: B\n\n' +
    '2. Қайси сўз от?\nА) китоб\nБ) ўқимоқ\nВ) чиройли\nГ) тез\nЖавоб: А',
  );
  await page.getByRole('button', { name: 'Bloklarga ajratish' }).click();
  await page.getByRole('tab', { name: 'Javoblar kaliti' }).click();
  await expect(page.getByRole('radiogroup', { name: /\b1$/ }).getByRole('radio', { name: 'B' })).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByRole('radiogroup', { name: /\b2$/ }).getByRole('radio', { name: 'A' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('tab', { name: 'Bloklar' }).click();
  await expect(page.locator('textarea').filter({ hasText: 'Қайси сўз от?' })).toHaveCount(1);
  await page.context().close();
});

test('Stage 1: at 360px a teacher starts a blank 20-question Ona tili test and tags its topic', async ({ browser, request }) => {
  const teacher = await login(request, 'e2e-teacher@example.test');
  const page = await pageAs(browser, teacher.tokens, 360);
  const title = `Blank 20 ${Date.now()}`;
  await page.goto('/teacher/studio/new');
  await page.getByPlaceholder('Masalan: Reading Mock 3').fill(title);
  await page.locator('main select').first().selectOption('uzbek');
  await page.getByRole('button', { name: /Keyingisi: Savollar/ }).click();
  await page.getByRole('tab', { name: 'Bloklar' }).click();
  await page.getByRole('button', { name: '20 ta savol' }).click();
  await expect(page.getByRole('textbox', { name: /^Savol matni \d+$/ })).toHaveCount(20);
  await page.getByLabel('Mavzu (tahlil uchun)').first().selectOption('imlo');
  await noOverflow(page);
  const saved = page.waitForResponse((r) => r.url().includes('/teacher/studio/tests/') && ['POST', 'PUT'].includes(r.request().method()));
  await page.getByRole('button', { name: 'Qoralamani saqlash' }).first().click();
  const body = await (await saved).json();
  const T = { Authorization: `Bearer ${teacher.tokens.access}` };
  const detail = await (await request.get(`${API}/api/v1/teacher/studio/tests/${body.test.id}/`, { headers: T })).json();
  expect(detail.blocks[0].topic).toBe('imlo');
  expect(detail.blocks[0].questions).toHaveLength(20);
  expect(detail.test.status).toBe('draft'); // empty questions cannot be published
  await page.context().close();
});
