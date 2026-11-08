import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
}

test('sidebar groups start collapsed, remember explicit choices and reveal the current table', async ({page}) => {
  await login(page);
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).not.toHaveAttribute('open', '');
  await group.locator('summary').click();
  await expect(group).toHaveAttribute('open', '');
  await page.reload();
  await expect(group).toHaveAttribute('open', '');
  await group.locator('summary').click();
  await page.goto('/admin/models/entries/');
  await expect(group).toHaveAttribute('open', '');
  await page.goto('/admin/');
  await expect(group).not.toHaveAttribute('open', '');
});

test('sidebar groups remain usable when browser storage is unavailable', async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
  await login(page);
  const group = page.locator('.nav-group[data-group="Data"]');
  await expect(group).not.toHaveAttribute('open', '');
  await group.locator('summary').press('Enter');
  await expect(group).toHaveAttribute('open', '');
  await page.reload();
  await expect(group).not.toHaveAttribute('open', '');
});
