import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
}

test('Home catalog groups remember choices while table pages keep a compact rail', async ({page}) => {
  await login(page);
  await page.locator('[data-home-catalog] > summary').click();
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).not.toHaveAttribute('open', '');
  await group.locator('summary').click();
  await expect(group).toHaveAttribute('open', '');
  await page.reload();
  await page.locator('[data-home-catalog] > summary').click();
  await expect(group).toHaveAttribute('open', '');
  await group.locator('summary').click();
  await page.goto('/admin/models/entries/');
  await expect(page.locator('[data-home-catalog]')).toHaveCount(0);
  await page.goto('/admin/');
  await page.locator('[data-home-catalog] > summary').click();
  await expect(group).not.toHaveAttribute('open', '');
});

test('Home catalog groups remain usable when browser storage is unavailable', async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
  await login(page);
  await page.locator('[data-home-catalog] > summary').click();
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).not.toHaveAttribute('open', '');
  await group.locator('summary').press('Enter');
  await expect(group).toHaveAttribute('open', '');
  await page.reload();
  await page.locator('[data-home-catalog] > summary').click();
  await expect(group).not.toHaveAttribute('open', '');
});

test('Home offers search and shortcuts while the directory keeps native table navigation', async ({page}) => {
  await login(page);
  await expect(page.locator('[data-dashboard] h1')).toHaveText('Quite Admin');
  await expect(page.locator('main [data-dashboard-table]')).toHaveCount(0);
  await page.locator('[data-home-catalog] > summary').click();
  const group = page.locator('.nav-group[data-group="Data"]');
  await group.locator('summary').press('Enter');
  await group.locator('[data-table-link="entries"]').click();
  await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
});
