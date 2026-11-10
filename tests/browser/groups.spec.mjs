import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
}

test('Home remembers the list view with groups initially open while table pages keep a compact rail', async ({page}) => {
  await login(page);
  const home = page.locator('[data-dashboard]');
  const catalog = page.locator('[data-home-catalog]');
  await expect(home).toHaveAttribute('data-home-view', 'cards');
  await expect(catalog).toBeHidden();
  await page.locator('[data-home-view-option="list"]').click();
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).toHaveAttribute('open', '');
  await group.locator('summary').click();
  await expect(group).not.toHaveAttribute('open', '');
  await page.reload();
  await expect(home).toHaveAttribute('data-home-view', 'list');
  await expect(catalog).toBeVisible();
  await expect(group).toHaveAttribute('open', '');
  await group.locator('summary').click();
  await page.goto('/admin/models/entries/');
  await expect(page.locator('[data-home-catalog]')).toHaveCount(0);
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
  await expect(page.locator('[data-sidebar-toggle], [data-sidebar-resizer]')).toHaveCount(0);
  await page.goto('/admin/');
  await expect(home).toHaveAttribute('data-home-view', 'list');
  await expect(group).toHaveAttribute('open', '');
  await page.locator('[data-home-view-option="cards"]').click();
  await expect(catalog).toBeHidden();
  await page.reload();
  await expect(home).toHaveAttribute('data-home-view', 'cards');
  await expect(catalog).toBeHidden();
  await expect(page.locator('[data-home-shortcuts]')).toBeVisible();
});

test('Home catalog groups remain usable when browser storage is unavailable', async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
  await login(page);
  const catalog = page.locator('[data-home-catalog]');
  await expect(catalog).toBeHidden();
  await page.locator('[data-home-view-option="list"]').click();
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).toHaveAttribute('open', '');
  await group.locator('summary').press('Enter');
  await expect(group).not.toHaveAttribute('open', '');
  await group.locator('summary').press('Enter');
  await expect(group).toHaveAttribute('open', '');
  await page.reload();
  await expect(page.locator('[data-dashboard]')).toHaveAttribute('data-home-view', 'cards');
  await expect(catalog).toBeHidden();
  await page.locator('[data-home-view-option="list"]').click();
  await expect(group).toHaveAttribute('open', '');
});

test('Home offers search and shortcuts while the directory keeps native table navigation', async ({page}) => {
  await login(page);
  await expect(page.locator('[data-dashboard] h1')).toHaveText('Quite Admin');
  await expect(page.locator('main [data-dashboard-table]')).toHaveCount(0);
  await page.locator('[data-home-view-option="list"]').click();
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).toHaveAttribute('open', '');
  await group.locator('[data-table-link="entries"]').click();
  await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
});
