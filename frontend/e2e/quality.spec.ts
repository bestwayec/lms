import { test, expect, type Page } from '@playwright/test';

const initialUser = { id: 42, email: 'student@example.test', first_name: 'Student', full_name: 'Student Test', role: 'student', active_subject: 'english', onboarding_completed: true, exam_target: 'ielts', target_exam: 'ielts', target_grade: 'Band 7.0', daily_goal_minutes: 30, reminder_slot: 'evening', plan: 'FREE' };
const emptyDashboard = { subject: 'english', tier: 'free', resume: null, recent: [], weak_parts: [], recommended_practice: [], goal: null, daily_goal: { goal_minutes: 30, completed_minutes: 0, goal_questions: 30, completed_questions: 0, target_exam: 'ielts', target_grade: 'Band 7.0' }, indicators: { tests_taken: 0, average_percentage: null, best_percentage: null, best_grade: null, best_sections: {}, best_overall: null, essays: { count: 0, recent: [] }, streak: 0 } };

async function mockApp(page: Page, options: { role?: string; onboarded?: boolean; dashboardFailure?: boolean } = {}) {
  let user = { ...initialUser, role: options.role || 'student', onboarding_completed: options.onboarded ?? true };
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.stack || e.message));
  await page.addInitScript(() => { localStorage.setItem('lms_lang', 'uz'); sessionStorage.setItem('lms_access', 'local-test'); });
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/school/teacher/')) return route.fulfill({ json: { groups: [], student_count: 0, published_tests: 0, active_topics: 0, recent_results: [] } });
    if (path.endsWith('/school/analytics/')) return route.fulfill({ json: { labels: [], attempts: [], avg_percentage: [], totals: { attempts: 0, passed: 0 } } });
    if (path.endsWith('/school/essay-leaderboard/')) return route.fulfill({ json: { podium: [], results: [], total_essays: 0, total_students: 0 } });
    if (path.endsWith('/referrals/my-code/')) return route.fulfill({ json: { referral_code: 'LOCAL', referral_link: 'https://grandec.uz/r/LOCAL', referred_count: 0 } });
    if (path === '/api/auth/me/') return route.fulfill({ json: user });
    if (path === '/api/auth/onboarding/') {
      user = { ...user, ...route.request().postDataJSON(), onboarding_completed: true };
      return route.fulfill({ json: { onboarding_completed: true, user } });
    }
    if (path === '/api/v1/dashboard/') return route.fulfill(options.dashboardFailure ? { status: 503, json: { detail: 'Unavailable' } } : { json: emptyDashboard });
    if (path.endsWith('/gamification/streak/')) return route.fulfill({ json: { current_streak: 0, week_days: Array.from({ length: 7 }, (_, i) => ({ day: String(i), date: '2026-11-12', is_active: false })) } });
    if (path.endsWith('/billing/entitlement/')) return route.fulfill({ json: { tier: 'free', is_admin: false, is_unlimited: false, limits: {} } });
    return route.fulfill({ json: { results: [], count: 0, enabled: false } });
  });
  return errors;
}

for (const path of ['/tests', '/essays', '/pricing']) {
  test(`anonymous direct and client navigation: ${path}`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.stack || e.message));
    // Guest route tests must work in CI without a running Django server.
    await page.route('**/api/**', (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/session/status/')) return route.fulfill({ json: { authenticated: false, user: null, tokens: null } });
      return route.fulfill({ json: { results: [], count: 0, my_plan_id: null, enabled: false } });
    });
    await page.goto('/');
    await page.locator(`a[href="${path}"]`).first().click();
    await expect(page).toHaveURL(path === '/pricing' ? /\/pricing$/ : /\/login$/);
    await page.goto(path);
    await expect(page).toHaveURL(path === '/pricing' ? /\/pricing$/ : /\/login$/);
    await expect(page.locator('.error-boundary')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test('onboarding rejection preserves selections, retry saves once and survives refresh', async ({ page }) => {
  const errors = await mockApp(page, { onboarded: false });
  await page.goto('/onboarding');
  await page.getByRole('button', { name: /IELTS Academic/ }).click();
  await page.getByRole('button', { name: 'Davom etish →' }).click();
  await page.getByRole('button', { name: 'Davom etish →' }).click();
  let count = 0;
  await page.route('**/api/auth/onboarding/', async (route) => { count++; return route.fulfill({ status: 400, json: { detail: 'Rejected' } }); });
  await page.getByRole('button', { name: /Tayyor! LMS/ }).click();
  await expect(page.getByRole('alert')).toContainText('Reja saqlanmadi');
  await expect(page).toHaveURL(/onboarding/);
  expect(await page.evaluate(() => localStorage.getItem('grandec_onboarding_done'))).toBeNull();
  await page.unroute('**/api/auth/onboarding/');
  // Reinstall the successful canonical response; route order is newest first.
  const saved = { ...initialUser, onboarding_completed: true };
  await page.route('**/api/auth/onboarding/', async (route) => { count++; await new Promise((r) => setTimeout(r, 200)); return route.fulfill({ json: { onboarding_completed: true, user: saved } }); });
  await page.getByRole('button', { name: 'Qayta urinish' }).dblclick();
  await expect(page).toHaveURL(/dashboard/);
  expect(count).toBe(2);
  await page.route('**/api/auth/me/', (route) => route.fulfill({ json: saved }));
  await page.reload();
  await expect(page.getByRole('dialog', { name: /Smart Onboarding/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('timeout does not complete onboarding and allows retry', async ({ page }) => {
  await mockApp(page, { onboarded: false });
  await page.addInitScript(() => { AbortSignal.timeout = () => AbortSignal.abort(new DOMException('Timeout', 'TimeoutError')); });
  await page.goto('/onboarding');
  await page.getByRole('button', { name: /O‘tkazib yuborish/ }).click();
  await expect(page.getByRole('alert')).toContainText('Reja saqlanmadi');
  await expect(page).toHaveURL(/onboarding/);
  await expect(page.getByRole('button', { name: /O‘tkazib yuborish/ })).toBeEnabled();
});

test('empty dashboard uses no invented scores or active days', async ({ page }) => {
  const errors = await mockApp(page);
  await page.goto('/dashboard');
  await expect(page.getByText('Tahlil uchun hali yetarli natijalar yo‘q.', { exact: false })).toBeVisible();
  await expect(page.locator('.dsh-week-chip.is-active')).toHaveCount(0);
  await expect(page.locator('.dsh-radar')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('dashboard API failure is retryable, with no performance cards', async ({ page }) => {
  await mockApp(page, { dashboardFailure: true });
  await page.goto('/dashboard');
  await expect(page.locator('.bento-grid')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Qayta/ }).first()).toBeVisible();
});

test('center admin enters scoped enterprise UI and cannot enter global panel', async ({ page }) => {
  await mockApp(page, { role: 'center_admin' });
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/enterprise/);
  await page.goto('/panel');
  await expect(page).toHaveURL(/enterprise/);
});

for (const theme of ['light', 'dark']) {
  test(`dashboard responsive layouts and goal editor (${theme})`, async ({ page }, testInfo) => {
    const errors = await mockApp(page);
    await page.addInitScript((value) => localStorage.setItem('theme_v2', value), theme);
    await page.goto('/dashboard');
    await expect(page.locator('.bento-grid')).toBeVisible();
    for (const width of [320, 375, 390, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `overflow at ${width}`).toBeTruthy();
      const groupFits = await page.locator('.dsh-group-code').evaluate((input) => { const form = input.closest('form')!.getBoundingClientRect(); const button = input.closest('form')!.querySelector('button')!.getBoundingClientRect(); return button.right <= form.right + 1; });
      expect(groupFits, `group join button clipped at ${width}`).toBeTruthy();
      if ([375, 1440].includes(width)) await page.screenshot({ path: testInfo.outputPath(`dashboard-${theme}-${width}.png`), fullPage: true });
    }
    await page.screenshot({ path: testInfo.outputPath(`dashboard-${theme}.png`), fullPage: true });
    await page.getByRole('button', { name: 'Maqsad', exact: true }).first().click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Eslatma vaqti' })).toBeVisible();
    await expect(page).toHaveURL(/dashboard/);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test('legacy local completion flags cannot hide a server-required onboarding flow', async ({ page }) => {
  await mockApp(page, { onboarded: false });
  await page.addInitScript(() => localStorage.setItem('grandec_onboarding_done', 'true'));
  await page.goto('/dashboard');
  await expect(page.getByRole('dialog', { name: /Smart Onboarding/ })).toBeVisible();
});

test('goal edit rejection stays open, retry persists one plan without introduction', async ({ page }) => {
  const errors = await mockApp(page);
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Maqsad', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('combobox').selectOption('morning');
  await page.route('**/api/auth/onboarding/', (route) => route.fulfill({ status: 400, json: { detail: 'Rejected' } }));
  await page.getByRole('button', { name: /Rejani saqlash/ }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('combobox')).toHaveValue('morning');
  await page.unroute('**/api/auth/onboarding/');
  const request = page.waitForRequest('**/api/auth/onboarding/');
  await page.getByRole('button', { name: /Rejani saqlash/ }).click();
  expect((await request).postDataJSON().reminder_slot).toBe('morning');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page).toHaveURL(/dashboard/);
  expect(errors).toEqual([]);
});

test('a stale lazy module after deployment recovers once via full reload', async ({ page }) => {
  await mockApp(page);
  await page.goto('/dashboard');
  await expect(page.locator('.bento-grid')).toBeVisible();
  let failed = false;
  await page.route('**/src/pages/Tests.tsx*', async (route) => {
    if (!failed) { failed = true; return route.abort('failed'); }
    return route.continue();
  });
  const reloaded = page.waitForEvent('load');
  await page.locator('a[href="/tests"]').first().click();
  await reloaded;
  await expect(page).toHaveURL(/tests$/);
  await expect(page.locator('.error-boundary')).toHaveCount(0);
  await expect.poll(() => failed).toBe(true);
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('grandec:chunk-reload-at'))).not.toBeNull();
});

test('student direct URLs cannot enter teacher or global admin routes', async ({ page }) => {
  const errors = await mockApp(page);
  for (const route of ['/panel', '/teacher']) {
    await page.goto(route);
    await expect(page).toHaveURL(/dashboard$/);
    await expect(page.locator('.bento-grid')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('teacher dashboard loads without student onboarding', async ({ page }) => {
  const errors = await mockApp(page, { role: 'teacher', onboarded: false });
  await page.goto('/dashboard');
  await expect(page.locator('.error-boundary')).toHaveCount(0);
  await expect(page.getByRole('dialog', { name: /Smart Onboarding/ })).toHaveCount(0);
  await expect(page.locator('.bento-grid')).toHaveCount(0);
  await expect(page.getByRole('main')).toContainText(/Test|Guruh|Ustoz/);
  await page.goto('/dashboard?tab=live');
  await expect(page.getByRole('button', { name: 'Test QR-kodi va kirish kodi' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Jonli Natijalar Tablosi' })).toBeDisabled();
  expect(errors).toEqual([]);
});

test('unlimited platform admin pricing route redirects to the panel', async ({ page }) => {
  await mockApp(page, { role: 'admin' });
  await page.goto('/pricing');
  await expect(page).toHaveURL(/panel$/);
  await expect(page.locator('.public-plans')).toHaveCount(0);
});

test('teacher live controls use the created test identity and canonical QR route', async ({ page }) => {
  const errors = await mockApp(page, { role: 'teacher' });
  const created = { ok: true, test_id: 1007, mock_code: 'LOCAL7', title: 'Local fixture exam', questions_count: 4, time_limit: 60, passing_score: 50 };
  await page.route('**/api/tests/mock/create/', (route) => route.fulfill({ json: created }));
  await page.goto('/dashboard?tab=live');
  await page.getByPlaceholder('Milliy Sertifikat Mock Test #1').fill(created.title);
  await page.locator('textarea[required]').fill('ABCD');
  await page.getByRole('button', { name: '⚡ 1-soniyada Mock Test Yaratish', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Test QR-kodi va kirish kodi' })).toBeEnabled();
  await page.getByRole('button', { name: 'Test QR-kodi va kirish kodi' }).click();
  const modal = page.getByRole('dialog');
  await expect(modal).toContainText('LOCAL7');
  await expect(modal.locator('a[href="http://127.0.0.1:5173/tests/1007"]')).toBeVisible();
  expect(errors).toEqual([]);
});

test('subject changes only after server confirmation and preserves goal on failure', async ({ page }) => {
  await mockApp(page);
  let fail = true;
  await page.route('**/api/v1/profile/switch-subject/', async (route) => {
    if (fail) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
    const payload = route.request().postDataJSON();
    return route.fulfill({ json: { ok: true, active_subject: payload.subject, exam_target: 'undecided', target_grade: '', daily_plan_summary: {} } });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard');
  const switcher = page.locator('.subject-switcher-scroll:visible').first();
  const english = switcher.getByRole('button', { name: /Ingliz/i });
  const biology = switcher.getByRole('button', { name: /Biolog/i });
  await expect(english).toHaveAttribute('aria-pressed', 'true');
  await biology.click();
  await expect(page.getByRole('alert').filter({ hasText: 'saqlanmadi' }).first()).toBeVisible();
  await expect(english).toHaveAttribute('aria-pressed', 'true');
  expect(await page.evaluate(() => localStorage.getItem('lms_subject'))).not.toBe('biology');
  fail = false;
  await biology.click();
  await expect(biology).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Imtihon maqsadi').first()).toHaveValue('undecided');
});

for (const width of [375, 1440]) {
  test(`OMR lists only the active subject and requires explicit test selection at ${width}px`, async ({ page }) => {
    await mockApp(page);
    await page.route('**/api/v1/tests/scan-omr/', (route) => route.fulfill({ json: { ok: true, count: 2, tests: [
      { id: 1, title: 'English test', mock_code: '', exam_type: 'cefr', subject: 'english', total_questions: 10, time_limit_minutes: 30 },
      { id: 2, title: 'Biology test', mock_code: '', exam_type: 'national', subject: 'biology', total_questions: 10, time_limit_minutes: 30 },
    ] } }));
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/tests/scan-omr');
    const select = page.locator('select.omr-input').first();
    await expect(select).toBeVisible();
    await expect(select).toHaveValue('');
    await expect(select.locator('option')).toContainText(['Testni tanlang', 'English test']);
    await expect(select.locator('option', { hasText: 'Biology test' })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await select.selectOption('1');
    await expect(select).toHaveValue('1');
  });
}
