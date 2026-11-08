import {readFile} from 'node:fs/promises';
import {test, expect} from '@playwright/test';

const script = await readFile(new URL('../../src/quite_admin/static/table-navigation.js', import.meta.url), 'utf8');
const css = await readFile(new URL('../../src/quite_admin/static/table-navigation.css', import.meta.url), 'utf8');
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll("'", '&#39;');
const tables = Array.from({length: 14}, (_, index) => ({id: `table_${index}`, name: `table_${index}`, label: `Table ${index}`, group: 'Data', url: `/admin/models/table_${index}/`}));

async function install(page, catalog = tables, user = 'admin') {
  await page.setContent(`<div data-admin-shell data-storage-key="/admin/" data-user-key="${escape(user)}" data-current-table="table_13"><a data-home-link href="/admin/">Home</a><div data-table-directory data-catalog="${escape(JSON.stringify(catalog))}" hidden></div><h1>Table 13 <button type="button" class="table-list-pin" data-table-pin="table_13" hidden></button><button type="button" data-table-pin="forbidden" hidden></button></h1><span data-table-pin-notice role="status" hidden></span><dialog class="table-search-dialog" data-table-search-dialog><button data-table-search-close>Close</button><input type="search" data-table-search-input aria-label="Search tables"><p data-table-search-count role="status"></p><p data-table-search-notice hidden></p><ul class="table-search-results" data-table-search-results></ul><p data-table-search-more hidden></p></dialog></div>`);
  await page.addStyleTag({content: css});
  if (await page.evaluate(() => typeof window.quiteAdminInitTables === 'function')) await page.evaluate(() => window.quiteAdminInitTables(document));
  else await page.addScriptTag({content: script});
}

test.describe('catalog controls', () => {
  test.beforeEach(async ({page}) => {
    await page.route('http://table-favorites.test/**', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>Favorites fixture</title>'}));
    await page.goto('http://table-favorites.test/');
  });

  test('listing and search SVG stars share state, labels and persistence', async ({page}) => {
    await install(page);
    const listing = page.locator('.table-list-pin');
    await expect(listing).toBeVisible();
    await expect(listing).toHaveAttribute('aria-pressed', 'false');
    await expect(listing).toHaveAttribute('aria-label', 'Pin table: Table 13');
    await expect(listing.locator('svg')).toBeVisible();
    await expect(listing.locator('svg')).toHaveCSS('fill', 'none');
    await listing.click();
    await expect(listing).toHaveAttribute('aria-pressed', 'true');
    await expect(listing).toHaveAttribute('aria-label', 'Unpin table: Table 13');
    expect(await listing.locator('svg').evaluate(node => getComputedStyle(node).fill)).not.toBe('none');
    // Safari does not focus a button on a mouse click. Start the shortcut from
    // explicit keyboard focus so Escape can restore that actual opener.
    await listing.focus();
    await page.keyboard.press('Control+k');
    await page.locator('[data-table-search-input]').fill('table_13');
    const modal = page.locator('[data-table-search-results] [data-table-pin="table_13"]');
    await expect(modal.locator('svg')).toBeVisible();
    await expect(modal).toHaveAttribute('aria-pressed', 'true');
    await modal.click();
    await expect(modal).toHaveAttribute('aria-pressed', 'false');
    await expect(listing).toHaveAttribute('aria-pressed', 'false');
    await page.keyboard.press('Escape');
    await expect(listing).toBeFocused();
    await listing.click();
    await install(page);
    await expect(listing).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-table-pin="forbidden"]')).toBeHidden();
    await install(page, tables, 'other-user');
    await expect(listing).toHaveAttribute('aria-pressed', 'false');
    await install(page, tables.slice(0, 2));
    await expect(listing).toBeHidden();
    expect(await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.pins())).toEqual([]);
  });

  test('the twelve-pin limit gives listing feedback and permits a replacement after unpinning', async ({page}) => {
    await install(page);
    await page.evaluate(() => {
      const api = document.querySelector('[data-admin-shell]').quiteAdminTables;
      for (let index = 0; index < 12; index++) api.togglePin('table_' + index);
    });
    const listing = page.locator('.table-list-pin');
    await listing.click();
    await expect(listing).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('[data-table-pin-notice]')).toHaveText('Pin up to 12 tables.');
    await expect(page.locator('[data-table-pin-notice]')).toBeVisible();
    await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.togglePin('table_0'));
    await listing.click();
    await expect(listing).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-table-pin-notice]')).toBeHidden();
    expect(await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.pins().length)).toBe(12);
  });

  test('listing stars still toggle when browser storage is blocked', async ({page}) => {
    await page.evaluate(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
    await install(page);
    const listing = page.locator('.table-list-pin');
    await listing.press('Enter');
    await expect(listing).toHaveAttribute('aria-pressed', 'true');
    await listing.press('Space');
    await expect(listing).toHaveAttribute('aria-pressed', 'false');
  });
});

test('record-list favorite persists and appears on Home, with the same state in search', async ({page}) => {
  await page.goto('/admin/login');
  await page.getByLabel('Username', {exact: true}).fill('admin');
  await page.getByLabel('Password', {exact: true}).fill('browser-test-password');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await page.goto('/admin/models/entries/');
  const listing = page.locator('.list-heading [data-table-pin="entries"]');
  await expect(listing).toBeVisible();
  await expect(listing.locator('svg')).toBeVisible();
  await listing.click();
  await expect(listing).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(listing).toHaveAttribute('aria-pressed', 'true');
  await page.goto('/admin/');
  await expect(page.locator('[data-home-pinned] [data-home-table="entries"]')).toBeVisible();
  await page.locator('[data-dashboard] [data-table-search]').first().click();
  await page.locator('[data-table-search-input]').fill('entries');
  const modal = page.locator('[data-table-search-results] [data-table-pin="entries"]');
  await expect(modal).toHaveAttribute('aria-pressed', 'true');
  await modal.click();
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-home-pinned] [data-home-table="entries"]')).toHaveCount(0);
  await page.goto('/admin/models/entries/');
  await expect(listing).toHaveAttribute('aria-pressed', 'false');
});
