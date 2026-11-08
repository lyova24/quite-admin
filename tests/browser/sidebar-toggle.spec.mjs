import {test, expect} from '@playwright/test';

async function login(page, mount = '/admin') {
  await page.goto(mount + '/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await expect(page).toHaveURL(new RegExp(mount + '/$'));
}

test('old collapse preferences do not hide or expand the fixed rail on any admin mount', async ({page}) => {
  await page.addInitScript(() => {
    localStorage.setItem('quite-admin:sidebar:/admin/', 'collapsed');
    localStorage.setItem('quite-admin:sidebar:/dark/', 'expanded');
    localStorage.setItem('quite-admin:sidebar-width:/admin/', '32rem');
  });
  await login(page);
  for (const path of ['/admin/','/admin/models/entries/','/admin/schema']) {
    await page.goto(path);
    await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
    await expect(page.locator('[data-sidebar-toggle], [data-sidebar-resizer]')).toHaveCount(0);
  }
  await page.reload();
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
  await login(page, '/dark');
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
});

test('the fixed rail and profile work without storage and tolerate repeated initialization', async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled');}}));
  await login(page, '/cursor');
  await page.evaluate(() => {window.quiteAdminNavigation(); window.quiteAdminNavigation(); window.quiteAdminResizeSidebar();});
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
  const profile = page.locator('[data-profile-toggle]');
  await profile.press('Enter');
  await expect(page.locator('[data-profile-popover]')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-profile-popover]')).toBeHidden();
  await expect(profile).toBeFocused();
});

test('mobile content remains active beside the rail after reload and viewport changes', async ({page}) => {
  await page.setViewportSize({width:390,height:400});
  await login(page);
  for (const size of [390,1280,390]) {
    await page.setViewportSize({width:size,height:400});
    await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
    await expect(page.locator('.main')).toHaveJSProperty('inert', false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.reload();
  await expect(page.locator('.main')).toHaveJSProperty('inert', false);
  await expect(page.locator('[data-sidebar-dismiss]')).toHaveCount(0);
});

test('navigation and the native profile remain usable without JavaScript', async ({browser, baseURL}) => {
  const context = await browser.newContext({javaScriptEnabled:false,baseURL});
  const page = await context.newPage();
  try {
    await login(page);
    await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
    await page.locator('.sidebar-rail-navigation').getByRole('link', {name:'Database schema',exact:true}).click();
    await expect(page).toHaveURL(/\/admin\/schema$/);
    await page.locator('.sidebar-home').press('Enter');
    await expect(page).toHaveURL(/\/admin\/$/);
    await page.locator('[data-profile-toggle]').press('Enter');
    await expect(page.getByRole('button', {name:'Sign out',exact:true})).toBeVisible();
  } finally { await context.close(); }
});
