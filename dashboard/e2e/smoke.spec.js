// @ts-check
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const BASE = process.env.PW_BASE || process.env.E2E_BASE_URL || 'http://127.0.0.1:3000';
// Two bases, because the suite checks two different things:
//
//  * `/health` is not under `/api`, so the dashboard's rewrite does not cover
//    it - it has to be asked of the backend directly.
//  * everything else is asked through the dashboard's own `/api` proxy,
//    which is the path the browser actually takes. Testing the backend
//    directly would test a route the product never uses.
//
// PW_API overrides the direct backend base (CI runs the API on 8000).
const DIRECT_API = process.env.PW_API || 'http://127.0.0.1:8000';
const PROXY_BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000';
const SHOTS = path.join(__dirname, '..', 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

/**
 * Real crash detection.
 *
 * `nextjs-portal` is Next.js's dev-tools overlay and is ALWAYS mounted in
 * `next dev` - it is not a crash signal. Judging health on it produced seven
 * false "runtime crash" findings. Instead we look for the things that actually
 * indicate a broken render: a React error overlay, or a root that mounted
 * nothing at all.
 */
async function realCrashes(pw) {
  return pw.evaluate(() => {
    const out = [];
    // React/Next error overlay (dev builds inject this on a thrown render error)
    if (document.querySelector('nextjs-error-overlay')) {
      out.push('next error overlay present');
    }
    // A root that mounted nothing at all.
    const bodyText = (document.body?.innerText || '').trim();
    if (bodyText.length < 20) out.push(`body nearly empty (${bodyText.length} chars)`);
    return out;
  });
}

const PAGES = [
  { name: 'dashboard', path: '/' },
  { name: 'find', path: '/find' },
  { name: 'scrape', path: '/scrape' },
  { name: 'leads', path: '/leads' },
  { name: 'sequences', path: '/sequences' },
  { name: 'campaigns', path: '/campaigns' },
  { name: 'settings', path: '/settings' },
];

/**
 * Pages the nav has to reach. `/campaigns` is only a legacy alias that
 * redirects to `/sequences`, so the nav links to the latter.
 */
const NAV_PAGES = PAGES.filter((p) => p.path !== '/campaigns');

test.describe.configure({ mode: 'serial' });

/** Non-fatal observations worth writing to disk. */
const findings = [];

test('API health and core endpoints respond', async ({ request }) => {
  const checks = [
    '/leads', '/campaigns', '/analytics/stats',
    '/mailboxes', '/scraper/jobs', '/icp',
    '/icp/sources/list', '/campaigns/india/advisor',
  ];
  // Health lives outside /api, so it is asked of the backend directly.
  const health = await request.get(DIRECT_API + '/health');
  expect(health.status(), '/health should respond').toBe(200);
  for (const p of checks) {
    const res = await request.get(PROXY_BASE + '/api/v1' + p);
    expect(res.status(), `${p} should respond`).toBe(200);
  }
});

for (const page of PAGES) {
  test(`page renders without errors: ${page.name}`, async ({ page: pw }) => {
    const errors = [];
    pw.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    pw.on('pageerror', (e) => errors.push(String(e)));

    const res = await pw.goto(BASE + page.path, { waitUntil: 'networkidle' });
    await pw.waitForTimeout(700);

    expect(res && res.status(), `${page.name} HTTP status`).toBeLessThan(400);
    await expect(pw.locator('body')).toBeVisible();

    const text = (await pw.locator('body').innerText()).trim();
    expect(text.length, `${page.name} rendered body text`).toBeGreaterThan(50);

    const crashes = await realCrashes(pw);
    expect(crashes, `${page.name} crashed`).toEqual([]);

    await pw.screenshot({ path: path.join(SHOTS, `${page.name}.png`), fullPage: true });
    if (errors.length) findings.push(`${page.name} console: ${errors[0].slice(0, 160)}`);
    expect(errors, `${page.name} console errors`).toEqual([]);
  });
}


test('sidebar navigation reaches every page', async ({ page: pw }) => {
  await pw.goto(BASE, { waitUntil: 'networkidle' });
  const links = pw.locator('a[href^="/"]');
  const n = await links.count();
  expect(n, 'nav links present').toBeGreaterThan(3);
  const hrefs = [];
  for (let i = 0; i < n; i++) {
    const h = await links.nth(i).getAttribute('href');
    if (h && PAGES.some((p) => p.path === h)) hrefs.push(h);
  }
  expect(hrefs.length, 'sidebar links to known pages').toBeGreaterThan(3);
  for (const h of new Set(hrefs)) {
    const res = await pw.goto(BASE + h, { waitUntil: 'domcontentloaded' });
    await pw.waitForTimeout(350);
    expect(res && res.status(), `${h} should not 404`).toBeLessThan(400);
    await expect(pw.locator('body')).toBeVisible();
  }
});

test('leads table shows data and bulk-select affordances', async ({ page: pw }) => {
  await pw.goto(BASE + '/leads', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(900);
  const rows = pw.locator('tbody tr');
  const count = await rows.count();
  expect(count, 'leads table has rows').toBeGreaterThan(0);
  // The empty state means the backend returned nothing — that is a failure,
  // not a pass.
  await expect(
    pw.getByText(/no leads (found|match)/i).first(),
    'leads: table is empty (backend returned no leads)',
  ).toHaveCount(0);

  const boxes = pw.locator('tbody input[type="checkbox"]');
  expect(await boxes.count(), 'rows expose a bulk-select checkbox').toBeGreaterThan(0);

  // A lead without an enriched contact has a disabled checkbox — pick one
  // that can actually be selected.
  const selectable = pw.locator('tbody input[type="checkbox"]:not([disabled])').first();
  expect(await selectable.count(), 'leads: no selectable row').toBeGreaterThan(0);
  await selectable.check();
  await pw.waitForTimeout(600);
  // Selecting a row must reveal the bulk action bar with the sequence action.
  const bulkBar = pw.getByRole('button', { name: /add to sequence/i });
  await expect(bulkBar, 'selecting a row reveals a sequence action').toBeVisible();

  await pw.screenshot({ path: path.join(SHOTS, 'leads-selected.png'), fullPage: true });
});

test('find page exposes India-first search controls', async ({ page: pw }) => {
  await pw.goto(BASE + '/find', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(700);
  const body = await pw.locator('body').innerText();
  expect(body, 'find: no India/city/keyword search controls found').toMatch(/india|delhi|mumbai|city|keyword/i);
  await pw.screenshot({ path: path.join(SHOTS, 'find-controls.png'), fullPage: true });
});

test('sequences and campaigns render content', async ({ page: pw }) => {
  for (const p of ['/sequences', '/campaigns', '/settings']) {
    await pw.goto(BASE + p, { waitUntil: 'networkidle' });
    await pw.waitForTimeout(800);
    const body = await pw.locator('body').innerText();
    expect(body.trim().length, `${p} rendered almost no content`).toBeGreaterThan(50);
    await pw.screenshot({ path: path.join(SHOTS, `${p.slice(1)}-panel.png`), fullPage: true });
  }
});

// --- Interaction tests: these verify features actually WORK, not just render ---

test('AI Lead Finder: parse an intent into a structured ICP draft', async ({ page: pw }) => {
  await pw.goto(BASE + '/find', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(500);

  const textarea = pw.locator('textarea').first();
  expect(await textarea.count(), 'find: no intent textarea to type into').toBeGreaterThan(0);
  await textarea.fill('dentists in Rohini Delhi with a website and good reviews');

  // The parse button is the primary action (Wand2 "Parse intent" or similar).
  const parseBtn = pw.getByRole('button', { name: /draft|parse|extract|understand|magic/i }).first();
  expect(await parseBtn.count(), 'find: no parse button found').toBeGreaterThan(0);
  await parseBtn.click();

  // Wait for the draft fields to populate from the parsed intent.
  await pw.waitForTimeout(2500);
  const body = await pw.locator('body').innerText();
  const nicheVal = await pw.locator('input').first().inputValue().catch(() => '');
  expect(
    /dent/i.test(body) || /dent/i.test(nicheVal),
    'find: parse did not populate draft fields with the niche',
  ).toBe(true);
  await pw.screenshot({ path: path.join(SHOTS, 'find-parsed.png'), fullPage: true });
});

test('Sequences: add a step and the step editor appears', async ({ page: pw }) => {
  await pw.goto(BASE + '/sequences', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(600);

  // The step editor lives inside an open sequence, so the page has to be in
  // that state first. Either a sequence is already open, or one is created.
  let addBtn = pw.getByRole('button', { name: /add (a )?(follow-?up )?step|new step|\+ step|add email/i }).first();
  if ((await addBtn.count()) === 0) {
    const createBtn = pw.getByRole('button', { name: /new sequence|create sequence/i }).first();
    expect(await createBtn.count(), 'sequences: no way to open a sequence editor').toBeGreaterThan(0);
    await createBtn.click();
    await pw.waitForTimeout(900);
    addBtn = pw.getByRole('button', { name: /add (a )?(follow-?up )?step|new step|\+ step|add email/i }).first();
  }
  expect(await addBtn.count(), 'sequences: no "add step" button').toBeGreaterThan(0);
  const before = await pw.locator('body').innerText();
  await addBtn.click();
  await pw.waitForTimeout(800);
  const after = await pw.locator('body').innerText();

  // A new step should add a "Subject line" placeholder to the editor.
  const subjectInputs = pw.locator('input[placeholder*="Subject" i]');
  expect(await subjectInputs.count(), 'sequences: adding a step produced no subject editor').toBeGreaterThan(0);
  expect(after, 'sequences: add-step click changed nothing on the page').not.toBe(before);
  await pw.screenshot({ path: path.join(SHOTS, 'sequences-editor.png'), fullPage: true });
});

test('Settings: open the Add Mailbox modal and its form fields render', async ({ page: pw }) => {
  await pw.goto(BASE + '/settings', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(600);

  const addBtn = pw.getByRole('button', { name: /add mailbox|add smtp|connect|new mailbox/i }).first();
  expect(await addBtn.count(), 'settings: no add-mailbox button').toBeGreaterThan(0);
  await addBtn.click();
  await pw.waitForTimeout(700);

  // The modal should expose an email input and a password input.
  const emailInput = pw.locator('input[placeholder*="@"]');
  const pwdInput = pw.locator('input[type="password"]');
  expect(await emailInput.count(), 'settings: add-mailbox modal missing email field').toBeGreaterThan(0);
  expect(await pwdInput.count(), 'settings: add-mailbox modal missing password field').toBeGreaterThan(0);
  await pw.screenshot({ path: path.join(SHOTS, 'settings-modal.png'), fullPage: true });
});

test('Sidebar: collapse toggle actually collapses the rail', async ({ page: pw }) => {
  await pw.goto(BASE, { waitUntil: 'networkidle' });
  await pw.waitForTimeout(500);

  const toggle = pw.getByRole('button', { name: /collapse|expand|panel/i }).first();
  expect(await toggle.count(), 'sidebar: no collapse toggle button').toBeGreaterThan(0);
  const widthBefore = await pw.locator('aside, nav').first().evaluate((el) => el.getBoundingClientRect().width).catch(() => 0);
  await toggle.click();
  await pw.waitForTimeout(600);
  const widthAfter = await pw.locator('aside, nav').first().evaluate((el) => el.getBoundingClientRect().width).catch(() => 0);
  expect(widthBefore, 'sidebar: rail had no measurable width').toBeGreaterThan(0);
  expect(
    Math.abs(widthAfter - widthBefore),
    `sidebar: collapse did not change rail width (${widthBefore}->${widthAfter})`,
  ).toBeGreaterThanOrEqual(8);
  await pw.screenshot({ path: path.join(SHOTS, 'sidebar-collapsed.png'), fullPage: true });
});

test('Leads: filters/search narrow the table', async ({ page: pw }) => {
  await pw.goto(BASE + '/leads', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(900);

  // The page-level filter box (NOT the global Cmd+K box in the top bar).
  const search = pw.getByPlaceholder(/search by business name/i).first();
  expect(await search.count(), 'leads: no search/filter input found').toBeGreaterThan(0);

  const rowsBefore = await pw.locator('tbody tr').count();
  expect(rowsBefore, 'leads: table has no rows to filter').toBeGreaterThan(0);
  // Real data must be on screen before we can claim the filter narrowed it.
  await expect(
    pw.getByText(/no leads (found|match)/i).first(),
    'leads: table shows no data rows',
  ).toHaveCount(0);

  await search.fill('zzzz-no-such-lead-zzzz');
  await pw.waitForTimeout(1500);
  await expect(
    pw.getByText(/no leads (found|match)/i).first(),
    'leads: search did not narrow results',
  ).toBeVisible();
});

test('Leads: global Cmd+K search lands on a filtered table', async ({ page: pw }) => {
  await pw.goto(BASE, { waitUntil: 'networkidle' });
  await pw.waitForTimeout(500);

  // The top bar search is the flagship affordance: it must carry the term
  // into /leads?search=... and the table must actually filter on it.
  const globalSearch = pw.getByLabel('Search leads').first();
  expect(await globalSearch.count(), 'topbar: global search box missing').toBeGreaterThan(0);
  await globalSearch.fill('averyunlikelysearchname');
  await globalSearch.press('Enter');
  await pw.waitForURL(/\/leads\?search=/, { timeout: 15000 });
  await pw.waitForTimeout(1500);

  const url = pw.url();
  expect(url, 'topbar: search did not navigate to /leads?search=').toContain('/leads?search=');
  // The leads page mirrors the query param back into its own filter box.
  const pageSearch = pw.getByPlaceholder(/search by business name/i).first();
  expect(
    await pageSearch.inputValue(),
    'leads: ?search= did not seed the filter box',
  ).toBe('averyunlikelysearchname');
});

test('Launching a sequence asks for confirmation first', async ({ page: pw }) => {
  await pw.goto(BASE + '/sequences', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(800);

  // Open the first sequence — the detail slide-over holds the Launch action.
  const row = pw.locator('tbody tr').first();
  if (await row.count() === 0) {
    findings.push('sequences: no sequence rows, launch confirmation not exercised');
    return;
  }
  await row.click();
  await pw.waitForTimeout(800);

  const launchBtn = pw.getByRole('button', { name: /^launch$/i }).first();
  if (await launchBtn.count() === 0) {
    findings.push('sequences: no launchable sequence found, launch confirmation not exercised');
    return;
  }
  await launchBtn.click();
  await pw.waitForTimeout(500);

  // Launch sends real cold email — it must be behind a confirmation that
  // states the blast radius.
  const dialog = pw.getByRole('alertdialog');
  await expect(dialog, 'launch must be confirmed before sending').toBeVisible();
  await expect(dialog).toContainText(/recipient/i);
  await expect(dialog).toContainText(/step/i);
});

test('mobile viewport renders without horizontal overflow', async ({ page: pw }) => {
  await pw.setViewportSize({ width: 390, height: 844 });
  for (const p of ['/', '/leads']) {
    await pw.goto(BASE + p, { waitUntil: 'networkidle' });
    await pw.waitForTimeout(600);
    // `body` is overflow-hidden, so the document never scrolls horizontally —
    // measuring it was a guaranteed false negative. Measure the main content
    // column instead, which is the thing that actually overflows.
    const overflow = await pw.evaluate(() => {
      const main = document.querySelector('main');
      if (!main) return -1;
      return main.scrollWidth - main.clientWidth;
    });
    expect(overflow, `mobile ${p}: main column overflows horizontally`).toBeLessThanOrEqual(4);
    await pw.screenshot({ path: path.join(SHOTS, `mobile-${p === '/' ? 'dashboard' : 'leads'}.png`), fullPage: true });
  }
});

test('mobile: the navigation drawer reaches every page', async ({ page: pw }) => {
  await pw.setViewportSize({ width: 390, height: 844 });
  await pw.goto(BASE, { waitUntil: 'networkidle' });
  await pw.waitForTimeout(500);

  const menu = pw.getByRole('button', { name: /open navigation/i }).first();
  expect(await menu.count(), 'mobile: no hamburger button').toBeGreaterThan(0);
  await menu.click();
  await pw.waitForTimeout(400);

  const drawer = pw.getByRole('dialog', { name: /navigation/i });
  await expect(drawer, 'mobile: drawer did not open').toBeVisible();
  const hrefs = await drawer.locator('a[href^="/"]').evaluateAll((els) =>
    els.map((e) => e.getAttribute('href')),
  );
  for (const p of NAV_PAGES) {
    expect(hrefs, `mobile: drawer cannot reach ${p.path}`).toContain(p.path);
  }
});

test.afterAll(() => {
  fs.writeFileSync(path.join(SHOTS, 'findings.json'), JSON.stringify(findings, null, 2));
  if (findings.length) console.log('\nFINDINGS:\n' + findings.map((f) => ' - ' + f).join('\n'));
});
