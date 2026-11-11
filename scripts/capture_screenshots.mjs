// Capture the real Python example; never connect to a running application or its DB.
import {spawn} from 'node:child_process';
import {mkdtemp, rm, mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium, expect} from '@playwright/test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = join(root, 'docs/assets/screenshots');
const temporary = await mkdtemp(join(tmpdir(), 'quite-admin-screenshots-'));
const port = Number(process.env.QUITE_ADMIN_SCREENSHOT_PORT || 8131);
const baseURL = `http://127.0.0.1:${port}`;
const password = 'fictional-screenshot-example';
const firstRecord = Buffer.from(JSON.stringify(['1'])).toString('base64url');
const python = process.env.QUITE_ADMIN_PYTHON || join(root, '.venv/bin/python');
const server = spawn(python, ['-m', 'uvicorn', 'scripts.screenshot_app:app', '--host', '127.0.0.1', '--port', String(port), '--no-access-log'], {
  cwd: root,
  env: {...process.env,
    QUITE_ADMIN_SCREENSHOT_DIRECTORY: temporary,
    QUITE_ADMIN_PASSWORD: password,
    QUITE_ADMIN_SECRET: 'fictional-screenshot-secret-material-for-local-use-only',
    QUITE_ADMIN_LANGUAGE: 'en',
    QUITE_ADMIN_TITLE: 'Quite Admin',
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverOutput = '';
server.stdout.on('data', chunk => {serverOutput += chunk;});
server.stderr.on('data', chunk => {serverOutput += chunk;});
let browser;
try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`Screenshot server failed: ${serverOutput}`);
    // A busy port must fail rather than capture an unrelated running application.
    if (serverOutput.includes(`Uvicorn running on ${baseURL}`)) {
      try {ready = (await fetch(baseURL + '/health')).ok;} catch {}
    }
    if (ready) break;
    await delay(200);
  }
  if (!ready) throw new Error(`Screenshot server did not become ready: ${serverOutput}`);
  browser = await chromium.launch(process.env.QUITE_ADMIN_BROWSER_EXECUTABLE
    ? {executablePath: process.env.QUITE_ADMIN_BROWSER_EXECUTABLE} : {});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1,
    baseURL, locale: 'en-US', timezoneId: 'UTC', colorScheme: 'dark', reducedMotion: 'reduce'});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.clock.setFixedTime(new Date('2026-11-11T12:00:00Z'));
  await mkdir(output, {recursive: true});
  async function capture(name) {
    await page.evaluate(() => document.fonts.ready);
    await page.mouse.move(1430, 990);
    await page.screenshot({path: join(output, name + '.png'), animations: 'disabled'});
    console.log(`Captured ${name}.png`);
  }
  async function open(path) {
    await page.goto('/admin' + path);
    await expect(page.locator('[data-admin-shell]')).toBeVisible();
  }
  await page.goto('/admin/');
  await expect(page.getByRole('button', {name: 'Sign in', exact: true})).toBeVisible();
  await capture('login');
  await page.getByLabel('Username', {exact: true}).fill('admin');
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.locator('[data-dashboard]')).toBeVisible();

  // Populate Home through the same controls a user sees.
  for (const slug of ['products', 'customers', 'orders']) {
    await open(`/models/${slug}/`);
    await page.locator(`[data-table-pin="${slug}"]`).click();
  }
  await open('/');
  await capture('overview');
  await page.locator('[data-home-view-option="list"]').click();
  await expect(page.locator('[data-dashboard]')).toHaveAttribute('data-home-view', 'list');
  await capture('home-table-list');

  await open('/models/products/?f.active.eq=true&f.price.gte=18');
  await expect(page.locator('.active-filters')).toContainText('Price');
  await capture('products');
  await page.locator('[data-filter-add]').click();
  const filter = page.locator('#filter-editor');
  await filter.locator('[data-field="f.price"]').click();
  await filter.locator('#filter-operator').selectOption('between');
  await filter.locator('#filter-value-0').fill('18');
  await filter.locator('#filter-value-1').fill('45');
  await capture('filters');
  await filter.getByRole('button', {name: 'Cancel', exact: true}).click();
  await page.locator('[data-list-field="price"] [data-inline-endpoint]').first().click();
  await expect(page.locator('[data-inline-dialog]')).toBeVisible();
  await page.locator('[data-inline-control] input').fill('19.50');
  await capture('inline-edit');
  await page.locator('[data-inline-cancel]').click();

  await open(`/models/products/${firstRecord}`);
  await expect(page.locator('[name=name]')).toHaveValue('Everyday notebook');
  await capture('record');
  await page.locator('#section-relations').scrollIntoViewIfNeeded();
  await page.locator('[data-relation-picker] summary').click();
  await expect(page.locator('.picker-results .picker-option')).toHaveCount(4);
  await page.locator('.picker-panel').scrollIntoViewIfNeeded();
  await capture('relationships');
  await open(`/models/customers/${firstRecord}`);
  await expect(page.locator('#field-joined_at')).toBeVisible();
  await capture('fields');

  await open(`/models/schedules/${firstRecord}`);
  const start = page.locator('.form-temporal').filter({has: page.locator('#field-starts_at-time')});
  await start.locator('summary').click();
  await start.getByRole('button', {name: 'Choose date', exact: true}).click();
  await expect(page.locator('.form-date-panel:not([hidden])')).toBeVisible();
  await capture('date-time-form');
  await page.keyboard.press('Escape');
  await page.locator('#label-settings').scrollIntoViewIfNeeded();
  await page.getByRole('button', {name: 'Format JSON', exact: true}).click();
  await capture('json-editor');

  // Record real writes so the journal displays persisted Before / After values.
  await open(`/models/products/${firstRecord}`);
  await page.locator('[name=price]').fill('19.50');
  await page.locator('[name=stock]').fill('132');
  await page.getByRole('button', {name: 'Save changes', exact: true}).click();
  await expect(page.locator('[name=price]')).toHaveValue('19.50');
  await open(`/models/notes/${firstRecord}`);
  await page.locator('[name=body]').fill('Review the new catalog.\nConfirm stock before launch.');
  await page.getByRole('button', {name: 'Save changes', exact: true}).click();
  await open('/history');
  await expect(page.locator('.activity-event')).toHaveCount(2);
  await page.getByRole('button', {name: 'Expand all changes', exact: true}).click();
  await capture('activity-history');
  await page.locator('[data-history-period] > summary').click();
  const period = page.getByRole('dialog', {name: 'Choose period', exact: true});
  await period.getByRole('tab', {name: 'Date range', exact: true}).click();
  await period.getByLabel('Date from (UTC)', {exact: true}).fill('2026-11-01');
  await period.getByLabel('Date to (UTC)', {exact: true}).fill('2026-11-11');
  await capture('activity-period');

  await open('/schema');
  const schema = page.locator('[data-schema-workspace]');
  await expect(schema).toHaveAttribute('data-schema-ready', 'true');
  await schema.locator('[data-junction-action]').first().click();
  await expect(schema.getByRole('button', {name: /^product_tags · product_tags/})).toBeVisible();
  await schema.locator('[data-node="products"]').press('Enter');
  await expect(schema.locator('[data-node="products"]')).toHaveAttribute('aria-expanded', 'true');
  await schema.locator('[data-schema-fit]').click();
  await capture('database-schema');
  expect(errors).toEqual([]);
  console.log('Updated all 14 documentation screenshots from the current Python interface.');
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
  if (server.exitCode === null) await new Promise(resolve => server.once('exit', resolve));
  await rm(temporary, {recursive: true, force: true});
}
