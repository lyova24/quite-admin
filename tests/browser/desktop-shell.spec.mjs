import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/$/);
}

test('the fixed rail contains navigation icons and a profile without extra layout controls', async ({page}) => {
  await login(page);
  const sidebar = page.locator('#admin-sidebar');
  await expect(sidebar).toHaveCSS('width', '56px');
  await expect(page.locator('.sidebar-rail')).toHaveCSS('width', '56px');
  await expect(page.locator('.sidebar-panel, [data-sidebar-toggle], [data-sidebar-resizer], .rail-search')).toHaveCount(0);
  await expect(page.locator('.topbar')).toBeHidden();
  await expect(sidebar.locator('[data-table-directory], [data-table-search]')).toHaveCount(0);
  await expect(page.locator('.sidebar-home')).toHaveAttribute('href', '/admin/');
  await expect(page.locator('.sidebar-home')).toHaveAccessibleName('Home');
  await expect(page.locator('.sidebar-home')).not.toHaveAttribute('aria-expanded');
  await expect(page.locator('.sidebar-rail-navigation').getByRole('link', {name:'Database schema',exact:true})).toBeVisible();
  await expect(page.locator('.sidebar-rail-navigation').getByRole('link', {name:'Activity history',exact:true})).toBeVisible();
  await expect(page.locator('.sidebar-footer [data-profile-toggle]')).toHaveAccessibleName('Profile');
  await expect(page.getByRole('button', {name:'Sign out',exact:true})).toBeHidden();
  await page.locator('.sidebar-home').hover();
  await expect(page.locator('[data-table-directory]')).toBeHidden();
});

test('inner pages show the admin identity on the right and use text Home breadcrumbs', async ({page}) => {
  await login(page);
  for (const path of ['/admin/models/entries/', '/admin/schema', '/admin/history']) {
    await page.goto(path);
    const header = page.locator('.topbar'), brand = header.locator('.service-brand');
    await expect(header).toBeVisible();
    await expect(brand).toBeVisible();
    await expect(brand).toHaveAttribute('href', '/admin/');
    await expect(brand.locator('.brand-mark, .brand-logo')).toBeVisible();
    await expect(brand.locator('span').last()).not.toBeEmpty();
    const bounds = await header.boundingBox(), identity = await brand.boundingBox();
    expect(bounds.x + bounds.width - identity.x - identity.width).toBeLessThan(40);
    expect(identity.x).toBeGreaterThan(bounds.x + bounds.width / 2);
    await expect(header.locator('.breadcrumbs svg')).toHaveCount(0);
  }
  await page.goto('/admin/models/entries/');
  const home = page.locator('.breadcrumbs a').first();
  await expect(home).toHaveText('Home');
  await expect(home).toHaveAttribute('href', '/admin/');
  await home.click();
  await expect(page.locator('.topbar')).toBeHidden();
  await expect(page.locator('.home-identity')).toBeVisible();
});

test('the profile opens to the avatar right, closes with Escape and outside clicks, and posts logout', async ({page}) => {
  await login(page);
  const profile = page.locator('[data-profile-toggle]'), popover = page.locator('[data-profile-popover]');
  await profile.click();
  await expect(popover).toBeVisible();
  await expect(profile).toHaveAttribute('aria-expanded', 'true');
  const avatar = await profile.boundingBox(), menu = await popover.boundingBox();
  expect(menu.x).toBeGreaterThanOrEqual(avatar.x + avatar.width);
  expect(menu.y + menu.height).toBeLessThanOrEqual(avatar.y + avatar.height + 1);
  expect(await popover.evaluate(el => getComputedStyle(el).boxShadow)).toContain('rgba(0, 0, 0');
  await page.keyboard.press('Escape');
  await expect(popover).toBeHidden();
  await expect(profile).toBeFocused();
  await profile.click();
  await page.locator('.content').click({position:{x:10,y:10}});
  await expect(popover).toBeHidden();
  await profile.click();
  const request = page.waitForRequest(request => new URL(request.url()).pathname === '/admin/logout');
  await page.getByRole('button', {name:'Sign out',exact:true}).click();
  expect((await request).method()).toBe('POST');
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test('profile focus dismissal does not intercept the shared modal Escape key', async ({page}) => {
  await login(page);
  await page.locator('[data-profile-toggle]').click();
  await page.keyboard.press('Control+k');
  await expect(page.locator('[data-table-search-dialog]')).toBeVisible();
  await expect(page.locator('[data-profile-popover]')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-table-search-dialog]')).toBeHidden();
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
});

test('the right-side profile fits a short narrow viewport with enlarged text', async ({page}) => {
  await page.setViewportSize({width:390,height:200});
  await login(page);
  await page.evaluate(() => {document.documentElement.style.fontSize='32px';});
  const profile = page.locator('[data-profile-toggle]'), popover = page.locator('[data-profile-popover]');
  await expect(profile).toBeInViewport();
  await profile.click();
  const menu = await popover.boundingBox(), avatar = await profile.boundingBox();
  expect(menu.x).toBeGreaterThanOrEqual(avatar.x + avatar.width);
  expect(menu.x + menu.width).toBeLessThanOrEqual(390);
  expect(menu.y).toBeGreaterThanOrEqual(0);
  expect(menu.y + menu.height).toBeLessThanOrEqual(200);
  await page.getByRole('button', {name:'Sign out',exact:true}).focus();
  await expect(page.getByRole('button', {name:'Sign out',exact:true})).toBeFocused();
  await expect(page.getByRole('button', {name:'Sign out',exact:true})).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(profile).toBeFocused();
});

test('touch Home navigates on the first tap without opening a table panel', async ({browser, baseURL}) => {
  const context = await browser.newContext({baseURL,hasTouch:true,viewport:{width:390,height:844}});
  const page = await context.newPage();
  try {
    await login(page);
    await page.goto('/admin/models/entries/');
    const navigation = page.waitForRequest(request => request.isNavigationRequest() && new URL(request.url()).pathname === '/admin/');
    await page.locator('.sidebar-home').tap();
    await navigation;
    await expect(page.locator('.sidebar-panel, [data-table-directory-trigger]')).toHaveCount(0);
    await expect(page.locator('[data-table-directory]')).toBeHidden();
  } finally { await context.close(); }
});
