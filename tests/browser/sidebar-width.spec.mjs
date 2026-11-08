import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/$/);
}

test('the rail has a fixed width on desktop and mobile with no resize handle', async ({page}) => {
  await login(page);
  for (const width of [1280,800,390,280]) {
    await page.setViewportSize({width,height:900});
    await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
    await expect(page.locator('[data-sidebar-resizer]')).toHaveCount(0);
    expect(await page.locator('.main').evaluate(el => el.getBoundingClientRect().left)).toBe(56);
  }
});

test('legacy width tokens and stored values do not resize the rail', async ({page}) => {
  await page.addInitScript(() => localStorage.setItem('quite-admin:sidebar-width:/admin/', '32rem'));
  await login(page);
  await page.evaluate(() => {
    document.documentElement.style.setProperty('--sidebar-width', '30rem');
    document.querySelector('[data-admin-shell]').style.setProperty('--sidebar-user-width', '32rem');
  });
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
  await page.evaluate(() => window.quiteAdminResizeSidebar());
  await expect(page.locator('#admin-sidebar')).toHaveCSS('width', '56px');
});

test('many page icons scroll independently while the avatar remains reachable', async ({page}) => {
  await page.setViewportSize({width:390,height:250});
  await login(page);
  await page.locator('.sidebar-rail-navigation').evaluate(nav => {
    const original = nav.querySelector('a');
    for (let index=0; index<80; index++) {
      const link = original.cloneNode(true);
      link.setAttribute('aria-label', 'Long custom page title '.repeat(15));
      nav.append(link);
    }
    nav.scrollTop = nav.scrollHeight;
  });
  await expect(page.locator('[data-profile-toggle]')).toBeInViewport();
  const fits = await page.locator('.sidebar-rail-navigation').evaluate(nav => nav.scrollWidth <= nav.clientWidth);
  expect(fits).toBe(true);
  await page.locator('[data-profile-toggle]').click();
  await expect(page.locator('[data-profile-popover]')).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
