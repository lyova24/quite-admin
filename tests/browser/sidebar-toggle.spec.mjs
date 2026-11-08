import {test, expect} from '@playwright/test';

async function login(page, mount = '/admin') {
  await page.goto(mount + '/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact: true}).fill('browser-test-password');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
}

test('sidebar toggle stays reachable, supports keyboard and persists only for its admin mount', async ({page}) => {
  await login(page);
  const shell = page.locator('[data-admin-shell]'), sidebar = page.locator('#admin-sidebar');
  const toggle = page.locator('[data-sidebar-toggle]');
  await expect(toggle).toHaveAccessibleName('Hide sidebar');
  await toggle.press('Enter');
  await expect(sidebar).toBeHidden();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toHaveAccessibleName('Show sidebar');
  await expect(shell).toHaveClass(/is-sidebar-collapsed/);
  await expect(toggle).toBeFocused();
  await page.goto('/admin/models/entries/');
  await expect(sidebar).toBeHidden();
  await page.reload();
  await expect(sidebar).toBeHidden();
  await login(page, '/dark');
  await expect(sidebar).toBeVisible();
  await page.goto('/admin/');
  await expect(sidebar).toBeHidden();
  await toggle.press('Space');
  await expect(sidebar).toBeVisible();
  await page.reload();
  await expect(sidebar).toBeVisible();
});

test('sidebar toggle works without storage and repeated initialization adds no handlers', async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
  await login(page, '/cursor');
  await expect(page.locator('[data-sidebar-toggle]')).toBeVisible();
  await page.evaluate(() => {window.quiteAdminNavigation(); window.quiteAdminNavigation();});
  const toggle = page.locator('[data-sidebar-toggle]'), sidebar = page.locator('#admin-sidebar');
  await toggle.click();
  await expect(sidebar).toBeHidden();
  await toggle.click();
  await expect(sidebar).toBeVisible();
  await toggle.click();
  await page.reload();
  await expect(sidebar).toBeVisible();
});

test('mobile sidebar can be hidden and restored without leaving horizontal overflow', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await login(page);
  const sidebar = page.locator('#admin-sidebar'), toggle = page.locator('[data-sidebar-toggle]');
  await page.evaluate(() => {
    const nav = document.querySelector('.sidebar nav');
    for (let index = 0; index < 60; index++) {
      const link = document.createElement('a'); link.className = 'nav-link';
      link.href = '#'; link.textContent = 'Table ' + index; nav.append(link);
    }
  });
  await expect(sidebar).toBeVisible();
  await toggle.click();
  await expect(sidebar).toBeHidden();
  await expect(toggle).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await toggle.press('Space');
  await expect(sidebar).toBeVisible();
  await expect(toggle).toBeInViewport();
  await expect(toggle).toBeFocused();
});

test('server-rendered sidebar and groups remain navigable without JavaScript', async ({browser, baseURL}) => {
  const context = await browser.newContext({javaScriptEnabled: false, baseURL});
  const page = await context.newPage();
  try {
    await login(page);
    await expect(page.locator('#admin-sidebar')).toBeVisible();
    await expect(page.locator('[data-sidebar-toggle]')).toBeHidden();
    const group = page.locator('.nav-group[data-group="Data"]');
    await group.locator('summary').press('Enter');
    await group.getByRole('link', {name: 'Entries', exact: true}).click();
    await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
  } finally {
    await context.close();
  }
});
