// @ts-check
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const BASE = process.env.PW_BASE || 'http://127.0.0.1:3000';
const API = process.env.PW_API || 'http://127.0.0.1:8000';
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
    if (document.querySelector('nextjs-error-overlay, [data-nextjs-dialog], [data-nextjs-toast]')) {
      out.push('next error overlay/toast present');
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

test.describe.configure({ mode: 'serial' });

const findings = [];

test('API health and core endpoints respond', async ({ request }) => {
  const checks = [
    '/health', '/api/v1/leads', '/api/v1/campaigns', '/api/v1/analytics/stats',
    '/api/v1/mailboxes', '/api/v1/scraper/jobs', '/api/v1/icp',
    '/api/v1/icp/sources/list', '/api/v1/campaigns/india/advisor',
  ];
  for (const p of checks) {
    const res = await request.get(API + p);
    if (res.status() !== 200) findings.push(`API ${p} -> ${res.status()} (want 200)`);
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
    if (crashes.length) findings.push(`${page.name}: ${crashes.join('; ')}`);

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
  for (const h of new Set(hrefs)) {
    await pw.goto(BASE + h, { waitUntil: 'domcontentloaded' });
    await pw.waitForTimeout(350);
    await expect(pw.locator('body')).toBeVisible();
  }
});

test('leads table shows data and bulk-select affordances', async ({ page: pw }) => {
  await pw.goto(BASE + '/leads', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(900);
  const rows = pw.locator('tbody tr');
  const count = await rows.count();
  if (count === 0) findings.push('leads: table has 0 rows');
  const boxes = pw.locator('tbody input[type="checkbox"]');
  if (count > 0 && (await boxes.count()) === 0) {
    findings.push('leads: rows present but no checkbox (bulk select missing)');
  }
  if (count > 0) {
    await boxes.first().check();
    await pw.waitForTimeout(600);
    const body = await pw.locator('body').innerText();
    if (!/sequence/i.test(body)) {
      findings.push('leads: selecting a row reveals no sequence action');
    }
  }
  await pw.screenshot({ path: path.join(SHOTS, 'leads-selected.png'), fullPage: true });
});

test('find page exposes India-first search controls', async ({ page: pw }) => {
  await pw.goto(BASE + '/find', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(700);
  const body = await pw.locator('body').innerText();
  if (!/india|delhi|mumbai|city|keyword/i.test(body)) {
    findings.push('find: no India/city/keyword search controls found');
  }
  await pw.screenshot({ path: path.join(SHOTS, 'find-controls.png'), fullPage: true });
});

test('sequences and campaigns render content', async ({ page: pw }) => {
  for (const p of ['/sequences', '/campaigns', '/settings']) {
    await pw.goto(BASE + p, { waitUntil: 'networkidle' });
    await pw.waitForTimeout(800);
    const body = await pw.locator('body').innerText();
    if (body.trim().length < 50) findings.push(`${p}: rendered almost no content`);
    await pw.screenshot({ path: path.join(SHOTS, `${p.slice(1)}-panel.png`), fullPage: true });
  }
});

// --- Interaction tests: these verify features actually WORK, not just render ---

test('AI Lead Finder: parse an intent into a structured ICP draft', async ({ page: pw }) => {
  await pw.goto(BASE + '/find', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(500);

  const textarea = pw.locator('textarea').first();
  if ((await textarea.count()) === 0) {
    findings.push('find: no intent textarea to type into');
    return;
  }
  await textarea.fill('dentists in Rohini Delhi with a website and good reviews');
  // The parse button is the primary action (Wand2 "Parse intent" or similar).
  const parseBtn = pw.getByRole('button', { name: /parse|extract|understand|magic/i }).first();
  if ((await parseBtn.count()) === 0) {
    findings.push('find: no parse button found');
    return;
  }
  await parseBtn.click();
  // Wait for the draft fields to populate from the parsed intent.
  await pw.waitForTimeout(2500);
  const body = await pw.locator('body').innerText();
  // After a successful parse, niche/area inputs should reflect the intent.
  const nicheVal = await pw.locator('input').first().inputValue().catch(() => '');
  if (!/dent/i.test(body) && !/dent/i.test(nicheVal)) {
    findings.push('find: parse did not populate draft fields with the niche');
  }
  await pw.screenshot({ path: path.join(SHOTS, 'find-parsed.png'), fullPage: true });
});

test('Sequences: add a step and the step editor appears', async ({ page: pw }) => {
  await pw.goto(BASE + '/sequences', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(600);

  const addBtn = pw.getByRole('button', { name: /add step|new step|\+ step|add email/i }).first();
  if ((await addBtn.count()) === 0) {
    findings.push('sequences: no "add step" button');
    return;
  }
  const before = await pw.locator('body').innerText();
  await addBtn.click();
  await pw.waitForTimeout(800);
  const after = await pw.locator('body').innerText();
  // A new step should add a "Subject line" placeholder to the editor.
  const subjectInputs = pw.locator('input[placeholder*="Subject" i]');
  if ((await subjectInputs.count()) === 0) {
    findings.push('sequences: adding a step produced no subject editor');
  } else if (after === before) {
    findings.push('sequences: add-step click changed nothing on the page');
  }
  await pw.screenshot({ path: path.join(SHOTS, 'sequences-editor.png'), fullPage: true });
});

test('Settings: open the Add Mailbox modal and its form fields render', async ({ page: pw }) => {
  await pw.goto(BASE + '/settings', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(600);

  const addBtn = pw.getByRole('button', { name: /add mailbox|add smtp|connect|new mailbox/i }).first();
  if ((await addBtn.count()) === 0) {
    findings.push('settings: no add-mailbox button');
    return;
  }
  await addBtn.click();
  await pw.waitForTimeout(700);
  // The modal should expose an email input and a password input.
  const emailInput = pw.locator('input[placeholder*="@"]');
  const pwdInput = pw.locator('input[type="password"]');
  if ((await emailInput.count()) === 0) {
    findings.push('settings: add-mailbox modal missing email field');
  }
  if ((await pwdInput.count()) === 0) {
    findings.push('settings: add-mailbox modal missing password field');
  }
  await pw.screenshot({ path: path.join(SHOTS, 'settings-modal.png'), fullPage: true });
});

test('Sidebar: collapse toggle actually collapses the rail', async ({ page: pw }) => {
  await pw.goto(BASE, { waitUntil: 'networkidle' });
  await pw.waitForTimeout(500);

  const toggle = pw.getByRole('button', { name: /collapse|expand|panel/i }).first();
  if ((await toggle.count()) === 0) {
    findings.push('sidebar: no collapse toggle button');
    return;
  }
  const widthBefore = await pw.locator('aside, nav').first().evaluate((el) => el.getBoundingClientRect().width).catch(() => 0);
  await toggle.click();
  await pw.waitForTimeout(600);
  const widthAfter = await pw.locator('aside, nav').first().evaluate((el) => el.getBoundingClientRect().width).catch(() => 0);
  if (widthBefore > 0 && widthAfter > 0 && Math.abs(widthAfter - widthBefore) < 8) {
    findings.push(`sidebar: collapse did not change rail width (${widthBefore}->${widthAfter})`);
  }
  await pw.screenshot({ path: path.join(SHOTS, 'sidebar-collapsed.png'), fullPage: true });
});

test('Leads: filters/search narrow the table', async ({ page: pw }) => {
  await pw.goto(BASE + '/leads', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(900);

  const search = pw.locator('input[type="search"], input[placeholder*="search" i], input[placeholder*="filter" i]').first();
  if ((await search.count()) === 0) {
    findings.push('leads: no search/filter input found');
    return;
  }
  const rowsBefore = await pw.locator('tbody tr').count();
  await search.fill('zzzz-no-such-lead-zzzz');
  await pw.waitForTimeout(1200);
  const rowsAfter = await pw.locator('tbody tr').count();
  if (rowsBefore > 0 && rowsAfter >= rowsBefore) {
    findings.push(`leads: search did not narrow results (${rowsBefore} -> ${rowsAfter})`);
  }
});

test('mobile viewport renders without horizontal overflow', async ({ page: pw }) => {
  await pw.setViewportSize({ width: 390, height: 844 });
  for (const p of ['/', '/leads']) {
    await pw.goto(BASE + p, { waitUntil: 'networkidle' });
    await pw.waitForTimeout(600);
    const overflow = await pw.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 4) findings.push(`mobile ${p}: horizontal overflow ${overflow}px`);
    await pw.screenshot({ path: path.join(SHOTS, `mobile-${p === '/' ? 'dashboard' : 'leads'}.png`), fullPage: true });
  }
});

test.afterAll(() => {
  fs.writeFileSync(path.join(SHOTS, 'findings.json'), JSON.stringify(findings, null, 2));
  if (findings.length) console.log('\nFINDINGS:\n' + findings.map((f) => ' - ' + f).join('\n'));
});
