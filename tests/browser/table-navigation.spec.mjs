import {readFile} from 'node:fs/promises';
import {test, expect} from '@playwright/test';

const script = await readFile(new URL('../../src/quite_admin/static/table-navigation.js', import.meta.url), 'utf8');
const css = await readFile(new URL('../../src/quite_admin/static/table-navigation.css', import.meta.url), 'utf8');
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll("'", '&#39;');
const tables = Array.from({length: 1993}, (_, index) => ({id: `table_${index}`, name: `table_${index}`, label: `Table ${index}`, group: `Group ${index % 5}`, url: `/admin/models/table_${index}/`}));

async function install(page, catalog = tables, {user = 'test-user', mount = '/admin/', current = '', buttons = true, enhance = true} = {}) {
  const nativeGroups = [...new Set(catalog.map(item => item.group))].map(group => `<details class="nav-group" data-group="${escape(group)}" ${catalog.some(item => item.group === group && item.id === current) ? 'open data-current-group' : ''}><summary>${escape(group)}</summary>${catalog.filter(item => item.group === group).map(item => `<a class="nav-link" href="${escape(item.url)}" data-table-link="${escape(item.id)}">${escape(item.label)}</a>`).join('')}</details>`).join('');
  await page.setContent(`<div data-admin-shell data-storage-key="${escape(mount)}" data-user-key="${escape(user)}" data-current-table="${escape(current)}">${buttons ? '<button data-table-search hidden>Search tables</button>' : ''}<a class="sidebar-home" href="/admin/" data-home-link>Home</a><div data-table-directory data-catalog="${escape(JSON.stringify(catalog))}" hidden></div><details data-home-catalog><summary>All tables ${catalog.length}</summary><nav data-collection-navigation>${nativeGroups}</nav></details><dialog class="table-search-dialog" data-table-search-dialog aria-label="Search tables"><button data-table-search-close>Close</button><input type="search" data-table-search-input aria-label="Search tables"><p data-table-search-count role="status"></p><p data-table-search-notice hidden></p><ul class="table-search-results" data-table-search-results></ul><p data-table-search-more hidden></p></dialog></div>`);
  if (!enhance) return;
  await page.addStyleTag({content: css});
  // Reuse a single script instance across client-side route renders.
  if (!await page.evaluate(() => typeof window.quiteAdminInitTables === 'function')) await page.addScriptTag({content: script});
  else await page.evaluate(() => window.quiteAdminInitTables(document));
}

test.beforeEach(async ({page}) => {
  await page.route('http://table-directory.test/**', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>Table directory fixture</title>'}));
  await page.goto('http://table-directory.test/health');
});

test('global modal keeps a 1993-table catalog searchable with bounded results and native keyboard links', async ({page}) => {
  await install(page);
  const trigger = page.locator('[data-table-search]');
  await trigger.click();
  const dialog = page.locator('[data-table-search-dialog]');
  const input = dialog.locator('input');
  await expect(input).toBeFocused();
  await expect(dialog.locator('li')).toHaveCount(60);
  await expect(dialog.locator('[data-table-search-count]')).toHaveText('Matching tables: 1993');
  await expect(dialog.locator('[data-table-search-more]')).toBeVisible();
  await input.fill('TaBlE_1988');
  await expect(dialog.locator('li')).toHaveCount(1);
  await expect(dialog.locator('a')).toHaveAttribute('href', '/admin/models/table_1988/');
  await input.press('ArrowDown');
  await expect(dialog.locator('a')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toHaveAttribute('open', '');
  await expect(trigger).toBeFocused();
  await page.keyboard.press('Control+k');
  await input.fill('group 4 table_199');
  await expect(dialog.locator('li')).toHaveCount(1);
  await expect(dialog.locator('a')).toContainText('Table 199');
  await input.fill('nothing matches');
  await expect(dialog.locator('li')).toHaveCount(0);
  await expect(dialog.locator('[data-table-search-count]')).toHaveText('No matching tables.');
  await input.fill('table_1988');
  await input.press('Enter');
  await expect(page).toHaveURL('http://table-directory.test/admin/models/table_1988/');
});

test('pins and recents store only authorized slugs, cap sizes, isolate users and recover from malformed storage', async ({page}) => {
  await install(page, tables.slice(0, 20), {current: 'table_3'});
  const initial = await page.evaluate(() => {
    const api = document.querySelector('[data-admin-shell]').quiteAdminTables;
    for (let i = 0; i < 20; i++) { api.remember('table_' + i); api.togglePin('table_' + i); }
    api.remember('forbidden'); api.togglePin('forbidden');
    return {recent: api.recent().map(item => item.id), pins: api.pins().map(item => item.id), saved: JSON.parse(localStorage.getItem('quite-admin:tables:["/admin/","test-user"]'))};
  });
  expect(initial.recent).toEqual(Array.from({length: 8}, (_, i) => `table_${19 - i}`));
  expect(initial.pins).toHaveLength(12);
  expect(initial.saved).toEqual({recent: initial.recent, pins: initial.pins, groups: []});
  await install(page, tables.slice(0, 2));
  expect(await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.pins().map(item => item.id))).toEqual(['table_0', 'table_1']);
  expect(await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.recent())).toEqual([]);
  await install(page, tables.slice(0, 2), {user: 'other-user'});
  expect(await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.pins())).toEqual([]);
  await page.evaluate(() => localStorage.setItem('quite-admin:tables:["/other/","test-user"]', '{broken'));
  await install(page, tables.slice(0, 2), {mount: '/other/'});
  expect(await page.evaluate(() => {
    const api = document.querySelector('[data-admin-shell]').quiteAdminTables;
    api.togglePin('table_1'); return api.pins().map(item => item.id);
  })).toEqual(['table_1']);
});

test('blocked storage keeps pins usable; rerender cleanup prevents duplicate shortcuts and respects other dialogs', async ({page}) => {
  await page.evaluate(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
  await install(page, tables.slice(0, 2));
  await page.locator('[data-table-search]').click();
  await page.locator('[data-table-pin="table_0"]').click();
  await expect(page.locator('[data-table-pin="table_0"]')).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await install(page, tables.slice(0, 2));
  await page.evaluate(() => { const dialog = document.createElement('dialog'); dialog.id = 'other-dialog'; document.body.append(dialog); dialog.showModal(); });
  await page.keyboard.press('Control+k');
  await expect(page.locator('[data-table-search-dialog]')).not.toHaveAttribute('open', '');
  await page.evaluate(() => document.querySelector('#other-dialog').close());
  await page.keyboard.press('Control+k');
  await expect(page.locator('[data-table-search-dialog]')).toHaveAttribute('open', '');
  await page.evaluate(() => document.querySelector('[data-table-search]').hidden = true);
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-table-search-dialog]')).not.toHaveAttribute('open', '');
  await expect(page.locator('[data-home-link]')).toBeFocused();
});

test('Unicode search escapes metadata, pin controls are siblings and native groups remain keyboard accessible', async ({page}) => {
  const catalog = [{id: 'cafe', name: 'cafes', label: 'Café <img src=x onerror=alert(1)>', group: 'Références', url: '/admin/models/cafe/'}];
  await install(page, catalog, {current: 'cafe'});
  await page.locator('[data-home-catalog] > summary').press('Enter');
  await page.locator('[data-group] summary').press('Enter');
  await page.locator('[data-group] summary').press('Enter');
  await expect(page.locator('[data-group]')).toHaveAttribute('open', '');
  await page.locator('[data-table-search]').click();
  await page.locator('[data-table-search-input]').fill('CAFE references');
  await expect(page.locator('[data-table-search-results] a')).toContainText(catalog[0].label);
  await expect(page.locator('[data-table-search-results] img')).toHaveCount(0);
  await expect(page.locator('[data-table-search-results] a button')).toHaveCount(0);
  await expect(page.locator('[data-table-pin]')).toHaveAttribute('aria-label', `Pin table: ${catalog[0].label}`);
});

test('group choices use slug-only persistence, reveal the current group and stay isolated by user', async ({page}) => {
  await install(page, tables.slice(0, 3));
  await page.locator('[data-home-catalog] > summary').click();
  await page.locator('[data-group="Group 0"] summary').click();
  await expect(page.locator('[data-group="Group 0"]')).toHaveAttribute('open', '');
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('quite-admin:tables:["/admin/","test-user"]')).groups)).toEqual(['table_0']);
  await install(page, tables.slice(0, 3), {current: 'table_1'});
  await expect(page.locator('[data-group="Group 0"]')).toHaveAttribute('open', '');
  await expect(page.locator('[data-group="Group 1"]')).toHaveAttribute('open', '');
  await install(page, tables.slice(0, 3), {user: 'other-user'});
  await expect(page.locator('[data-group="Group 0"]')).not.toHaveAttribute('open', '');
});

test('global shortcut works on pages without search buttons or a visible catalog', async ({page}) => {
  await install(page, tables.slice(0, 2), {buttons: false});
  await page.locator('[data-home-catalog]').evaluate(node => node.remove());
  await expect(page.locator('[data-table-directory]')).toBeHidden();
  await expect(page.locator('[data-table-search]')).toHaveCount(0);
  await page.keyboard.press('Control+k');
  await expect(page.locator('[data-table-search-input]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-home-link]')).toBeFocused();
});

test.describe('without JavaScript', () => {
  test.use({javaScriptEnabled: false});
  test('all 1993 Home table links remain available through native collapsible groups', async ({page}) => {
    await install(page, tables, {enhance: false});
    const catalog = page.locator('[data-home-catalog]');
    await expect(catalog.locator('a[data-table-link]')).toHaveCount(1993);
    await expect(catalog).not.toHaveAttribute('open', '');
    await expect(page.locator('[data-table-directory]')).toBeHidden();
    await catalog.locator(':scope > summary').press('Enter');
    const group = catalog.locator('[data-group="Group 2"]');
    await group.locator('summary').press('Enter');
    const link = group.locator('[data-table-link="table_1992"]');
    await expect(link).toBeVisible();
    await link.press('Enter');
    await expect(page).toHaveURL('http://table-directory.test/admin/models/table_1992/');
  });
});
