import {readFile} from 'node:fs/promises';
import {test, expect} from '@playwright/test';

const dashboardScript = await readFile(new URL('../../src/quite_admin/static/dashboard.js', import.meta.url), 'utf8');
const tableScript = await readFile(new URL('../../src/quite_admin/static/table-navigation.js', import.meta.url), 'utf8');
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll("'", '&#39;');
const catalog = Array.from({length:12}, (_, index) => ({id:`table_${index}`,name:`table_${index}`,label:`Table ${index}`,group:'Data',url:`/admin/models/table_${index}/`}));
const homeSearch = page => page.locator('[data-dashboard] [data-table-search]').first();
const recent = page => page.locator('[data-home-recent]');
const remove = (page, id) => recent(page).locator(`[data-home-remove-recent="${id}"]`);

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username', {exact:true}).fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in',exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/$/);
}

async function visitTables(page) {
  await login(page);
  await page.goto('/admin/models/entries/');
  await page.goto('/admin/models/customers/');
  await page.goto('/admin/');
}

async function install(page, {user='alice', items=catalog, messages={}} = {}) {
  await page.evaluate(() => document.querySelector('[data-dashboard]')?.quiteAdminDashboardCleanup?.());
  await page.setContent(`<div data-admin-shell data-storage-key="/admin/" data-user-key="${escape(user)}"><div data-table-directory data-catalog="${escape(JSON.stringify(items))}" hidden></div><main data-dashboard data-messages="${escape(JSON.stringify(messages))}"><button data-table-search hidden>Find a table</button><section data-home-pinned-section hidden><div data-home-pinned></div><p data-home-pinned-empty>No pinned tables.</p></section><section data-home-recent-section hidden><div data-home-recent></div><p data-home-recent-empty>No recent tables.</p></section></main><dialog data-table-search-dialog><button data-table-search-close>Close</button><input data-table-search-input><p data-table-search-count></p><p data-table-search-notice hidden></p><ul data-table-search-results></ul><p data-table-search-more hidden></p></dialog></div>`);
  if (!await page.evaluate(() => typeof window.quiteAdminInitTables === 'function')) await page.addScriptTag({content:tableScript});
  else await page.evaluate(() => window.quiteAdminInitTables(document));
  if (!await page.evaluate(() => typeof window.quiteAdminDashboard === 'function')) await page.addScriptTag({content:dashboardScript});
  else await page.evaluate(() => window.quiteAdminDashboard(document));
}

test('removing a recent table does not navigate or unpin it, persists, and a later visit restores it', async ({page}) => {
  await visitTables(page);
  await page.evaluate(() => {
    const tables = document.querySelector('[data-admin-shell]').quiteAdminTables;
    tables.togglePin('entries');
  });
  const pinned = page.locator('[data-home-pinned] [data-home-table="entries"]');
  await expect(pinned).toBeVisible();
  await expect(remove(page,'entries')).toHaveAccessibleName('Remove from recently opened: Entries');
  await expect(recent(page).locator('a button')).toHaveCount(0);
  const navigations=[];
  page.on('request', request => {if(request.isNavigationRequest()) navigations.push(request.url());});
  await remove(page,'entries').click();
  await expect(recent(page).locator('[data-home-table="entries"]')).toHaveCount(0);
  await expect(pinned).toBeVisible();
  expect(navigations).toEqual([]);
  await page.reload();
  await expect(recent(page).locator('[data-home-table="entries"]')).toHaveCount(0);
  await expect(recent(page).locator('[data-home-table="customers"]')).toBeVisible();
  await expect(pinned).toBeVisible();
  await page.goto('/admin/models/entries/');
  await page.goto('/admin/');
  await expect(recent(page).locator('[data-home-table]').first()).toHaveAttribute('data-home-table','entries');
  await expect(pinned).toBeVisible();
});

test('recent remove buttons support Enter and Space and restore focus to the next button or search', async ({page}) => {
  await visitTables(page);
  await remove(page,'customers').press('Enter');
  await expect(remove(page,'customers')).toHaveCount(0);
  await expect(remove(page,'entries')).toBeFocused();
  await remove(page,'entries').press('Space');
  await expect(recent(page).locator('[data-home-table]')).toHaveCount(0);
  await expect(page.locator('[data-home-recent-empty]')).toBeVisible();
  await expect(homeSearch(page)).toBeFocused();
});

test.describe('recent state boundaries', () => {
  test.beforeEach(async ({page}) => {
    await page.route('http://recent-tables.test/**', route => route.fulfill({contentType:'text/html',body:'<!doctype html><title>Recent tables fixture</title>'}));
    await page.goto('http://recent-tables.test/health');
  });

  test('removal respects the eight-item history limit, keeps pins and isolates users after rerender', async ({page}) => {
    await install(page);
    const state = await page.evaluate(() => {
      const tables = document.querySelector('[data-admin-shell]').quiteAdminTables;
      for(let index=0;index<12;index++) tables.remember(`table_${index}`);
      tables.togglePin('table_11');
      return tables.recent().map(item=>item.id);
    });
    expect(state).toEqual(['table_11','table_10','table_9','table_8','table_7','table_6','table_5','table_4']);
    await expect(recent(page).locator('[data-home-table]')).toHaveCount(6);
    await remove(page,'table_11').click();
    await expect(remove(page,'table_10')).toBeFocused();
    await expect(recent(page).locator('[data-home-table="table_5"]')).toBeVisible();
    await expect(page.locator('[data-home-pinned] [data-home-table="table_11"]')).toBeVisible();
    await install(page,{user:'bob'});
    await expect(recent(page).locator('[data-home-table]')).toHaveCount(0);
    await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.remember('table_11'));
    await remove(page,'table_11').click();
    await install(page,{user:'alice'});
    await expect(recent(page).locator('[data-home-table="table_11"]')).toHaveCount(0);
    await expect(page.locator('[data-home-pinned] [data-home-table="table_11"]')).toBeVisible();
    expect(await page.evaluate(() => document.querySelector('[data-admin-shell]').quiteAdminTables.recent().length)).toBe(7);
  });

  test('localized removal labels escape metadata and blocked storage keeps changes usable in memory', async ({page}) => {
    await page.evaluate(() => Object.defineProperty(window,'localStorage',{get(){throw new Error('Storage disabled');}}));
    const name='Orders <img src=x onerror=alert(1)>';
    await install(page,{items:[{...catalog[0],label:name}],messages:{removeRecent:'Убрать из недавно открытых: {name}'}});
    await page.evaluate(() => {
      const tables=document.querySelector('[data-admin-shell]').quiteAdminTables;
      tables.remember('table_0');tables.togglePin('table_0');
    });
    await expect(remove(page,'table_0')).toHaveAccessibleName(`Убрать из недавно открытых: ${name}`);
    await expect(recent(page).locator('img')).toHaveCount(0);
    await expect(recent(page).locator('a button')).toHaveCount(0);
    await remove(page,'table_0').click();
    await expect(recent(page).locator('[data-home-table]')).toHaveCount(0);
    await expect(page.locator('[data-home-pinned] [data-home-table="table_0"]')).toBeVisible();
    await expect(homeSearch(page)).toBeFocused();
  });
});
