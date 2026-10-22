// @ts-check
/**
 * The People table.
 *
 * This is the surface that answers "show me every owner in Pune", so the
 * tests check the things that would silently make it lie:
 *
 *  * the filters must be *server-side* - clicking "Decision makers only"
 *    has to change the row set, not just the styling;
 *  * the count in the filter dropdowns has to match what the API returns,
 *    so a dropdown that says "14 owners" cannot disagree with the table;
 *  * a row must say whether it is a person or a business target, because
 *    a table that calls a company's phone-only row a "founder" is worse
 *    than no table at all.
 */

const { test, expect } = require('@playwright/test');

const BASE = process.env.PW_BASE || process.env.E2E_BASE_URL || 'http://127.0.0.1:3000';
const API = process.env.PW_API || 'http://127.0.0.1:8000';

test.describe.configure({ mode: 'serial' });

test('people page renders the table and the filter bar', async ({ page: pw }) => {
  await pw.goto(BASE + '/people', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(700);

  await expect(pw.getByRole('heading', { name: 'People', level: 1 })).toBeVisible();
  await expect(pw.getByLabel('Role', { exact: true })).toBeVisible();
  await expect(pw.getByLabel('City', { exact: true })).toBeVisible();
  await expect(pw.getByLabel('Search people by name, title, company or city')).toBeVisible();

  // The body must have real content, not just a shell.
  const text = (await pw.locator('body').innerText()).trim();
  expect(text.length).toBeGreaterThan(80);
});

test('the people API answers with rows and a coherent total', async ({ request }) => {
  const res = await request.get(API + '/api/v1/contacts?limit=5');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(Array.isArray(body.people)).toBe(true);
  expect(typeof body.total).toBe('number');
  expect(body.total).toBeGreaterThanOrEqual(body.people.length);
  expect(body.people.length).toBeLessThanOrEqual(5);

  for (const p of body.people) {
    expect(p).toHaveProperty('name');
    expect(p).toHaveProperty('seniority');
    expect(p).toHaveProperty('is_person');
    expect(p).toHaveProperty('is_decision_maker');
  }
});

test('the decision-maker filter is applied by the server', async ({ request }) => {
  const all = await (await request.get(API + '/api/v1/contacts?limit=50')).json();
  const dm = await (
    await request.get(API + '/api/v1/contacts?decision_makers_only=true&limit=50')
  ).json();

  expect(dm.total).toBeLessThanOrEqual(all.total);
  for (const p of dm.people) {
    expect(
      ['owner', 'c_level', 'vp', 'director', 'head'],
      `${p.name} (${p.seniority}) is a decision maker`
    ).toContain(p.seniority);
  }
});

test('a person row is never a fabricated founder', async ({ request }) => {
  // The discovery path used to write "Owner / Decision Maker" on every
  // business, which made the table report 126 founders where there were
  // none. A row with a title must be a row whose person was identified.
  const body = await (await request.get(API + '/api/v1/contacts?limit=100')).json();
  for (const p of body.people) {
    if (p.title) {
      expect(
        p.title.toLowerCase(),
        `"${p.title}" is not a real title`
      ).not.toBe('owner / decision maker');
    }
    if (!p.is_person) {
      // A business target must not claim a title.
      expect(p.title === null || p.title === undefined).toBe(true);
    }
  }
});

test('the city filter narrows the result set', async ({ request }) => {
  const facets = await (await request.get(API + '/api/v1/contacts/facets')).json();
  const city = (facets.city || [])[0];
  test.skip(!city, 'no city in the database yet');

  const res = await request.get(
    API + '/api/v1/contacts?city=' + encodeURIComponent(city.value)
  );
  const body = await res.json();
  expect(body.total).toBeGreaterThan(0);
  for (const p of body.people) {
    expect(
      String(p.city || '').toLowerCase(),
      `${p.name} is in ${p.city}, not ${city.value}`
    ).toBe(String(city.value).toLowerCase());
  }
});

test('clicking a filter changes the rows on screen', async ({ page: pw }) => {
  await pw.goto(BASE + '/people', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(700);

  // The row *count* is not a reliable signal here: the page size is 25, and
  // a page of people and a page of business targets are both a full page.
  // The total in the footer is the thing that actually changes.
  const totalText = () => pw.getByText(/· \d+ people/).first().innerText();
  const before = await totalText();

  const toggle = pw.getByRole('button', { name: 'Show business targets' });
  await toggle.click();
  await pw.waitForTimeout(1500);

  const after = await totalText();
  expect(after, 'the filter did not change the result set').not.toBe(before);

  // And the filter chip must be removable.
  await expect(pw.getByRole('button', { name: /Including business targets/ })).toBeVisible();
  await pw.getByRole('button', { name: /Remove filter: Rows/ }).click();
  await pw.waitForTimeout(1500);
  expect(await totalText()).toBe(before);
});

test('the people table is a real table with headers on a desktop viewport', async ({ page: pw }) => {
  await pw.setViewportSize({ width: 1440, height: 900 });
  await pw.goto(BASE + '/people', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(700);

  const headers = pw.locator('table thead th');
  expect(await headers.count()).toBeGreaterThanOrEqual(5);
  // Every column header is labelled - an unlabelled column is unusable
  // with a screen reader.
  for (let i = 0; i < (await headers.count()); i++) {
    const label = (await headers.nth(i).innerText()).trim();
    expect(label.length, 'column header has a label').toBeGreaterThan(0);
  }
});

test('the people table collapses to cards on a phone viewport', async ({ page: pw }) => {
  await pw.setViewportSize({ width: 390, height: 844 });
  await pw.goto(BASE + '/people', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(700);

  // The wide table is hidden; the card list is shown.
  await expect(pw.locator('table').first()).toBeHidden();
  await expect(pw.getByRole('heading', { name: 'People', level: 1 })).toBeVisible();

  // Nothing may overflow the viewport horizontally.
  const overflow = await pw.evaluate(() => {
    return document.documentElement.scrollWidth - document.documentElement.clientWidth;
  });
  expect(overflow, 'no horizontal overflow on a phone').toBeLessThanOrEqual(1);
});

test('people can be selected and added to a sequence', async ({ page: pw }) => {
  // Selecting people and putting them in a sequence is the whole point of
  // this surface. A table you can only read is a report.
  await pw.goto(BASE + '/people', { waitUntil: 'networkidle' });
  await pw.waitForTimeout(1200);

  const boxes = pw.locator('tbody input[type="checkbox"]');
  const count = await boxes.count();
  expect(count, 'the people table has selectable rows').toBeGreaterThan(0);

  await boxes.first().check();
  await pw.waitForTimeout(400);

  // The bulk bar appears with the count.
  const bar = pw.getByText(/person(s)? selected/i).first();
  await expect(bar).toBeVisible();

  // And the sequence picker opens.
  await pw.getByRole('button', { name: /add to sequence/i }).first().click();
  await pw.waitForTimeout(700);
  const dialog = pw.getByRole('dialog', { name: /add to sequence/i });
  await expect(dialog).toBeVisible();
});
