import {test, expect} from '@playwright/test';

const home = page => page.locator('[data-dashboard]');
const catalog = page => home(page).locator('[data-home-catalog]');
const option = (page, view) => home(page).locator(`[data-home-view-option="${view}"]`);

async function login(page, mount = '/admin') {
  await page.goto(`${mount}/login`);
  await page.getByLabel('Username', {exact:true}).fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await expect(option(page, 'cards')).toBeVisible();
}

async function savedTables(page) {
  return page.evaluate(() => {
    const shell = document.querySelector('[data-admin-shell]');
    return localStorage.getItem('quite-admin:tables:' + JSON.stringify([shell.dataset.storageKey, shell.dataset.userKey]));
  });
}

test('Cards hides the catalog and switching views preserves shortcuts without duplicating tables', async ({page}) => {
  await login(page);
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
  await expect(option(page, 'cards')).toHaveAttribute('aria-pressed', 'true');
  await expect(catalog(page)).not.toHaveAttribute('open', '');
  await expect(catalog(page)).toBeHidden();
  const group = catalog(page).locator('[data-group="Data"]');
  const expansion = await catalog(page).locator('details').evaluateAll(groups => groups.map(group => group.open));
  await page.evaluate(() => {
    const tables = document.querySelector('[data-admin-shell]').quiteAdminTables;
    tables.togglePin('entries'); tables.remember('customers');
  });
  const saved = await savedTables(page);
  await option(page, 'list').press('Enter');
  await expect(option(page, 'list')).toBeFocused();
  await expect(option(page, 'list')).toHaveAttribute('aria-pressed', 'true');
  await expect(home(page)).toHaveAttribute('data-home-view', 'list');
  await expect(catalog(page)).toBeVisible();
  await expect(home(page).locator('[data-home-shortcuts]')).toBeHidden();
  await expect(catalog(page).locator(':scope > summary')).toBeHidden();
  await expect(catalog(page).locator('a[data-table-link]')).toHaveCount(2);
  expect(await catalog(page).locator('details').evaluateAll(groups => groups.every(group => group.open))).toBe(true);
  await group.locator('summary').press('Enter');
  await expect(group).not.toHaveAttribute('open', '');
  expect(await savedTables(page)).toBe(saved);
  await option(page, 'cards').press('Space');
  await expect(option(page, 'cards')).toBeFocused();
  await expect(catalog(page)).toBeHidden();
  await expect(catalog(page)).not.toHaveAttribute('open', '');
  expect(await catalog(page).locator('details').evaluateAll(groups => groups.map(group => group.open))).toEqual(expansion);
  await expect(home(page).locator('[data-home-pinned] [data-home-table="entries"]')).toBeVisible();
  await expect(home(page).locator('[data-home-recent] [data-home-table="customers"]')).toBeVisible();
  expect(await savedTables(page)).toBe(saved);
  await option(page, 'list').click();
  await option(page, 'cards').click();
  await expect(catalog(page)).toBeHidden();
  await expect(catalog(page)).not.toHaveAttribute('open', '');
});

test('Home view persists through table navigation and reload and synchronizes across tabs', async ({page, context}) => {
  await login(page);
  const other = await context.newPage();
  await other.goto('/admin/');
  await expect(option(other, 'cards')).toBeVisible();
  await option(page, 'list').click();
  await expect(home(other)).toHaveAttribute('data-home-view', 'list');
  await catalog(page).locator('[data-table-link="entries"]').click();
  await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
  await page.locator('.sidebar-home').click();
  await expect(home(page)).toHaveAttribute('data-home-view', 'list');
  await page.reload();
  await expect(home(page)).toHaveAttribute('data-home-view', 'list');
  await page.keyboard.press('Control+k');
  await expect(page.locator('[data-table-search-input]')).toBeFocused();
  await page.keyboard.press('Escape');
  await other.evaluate(() => {
    const shell = document.querySelector('[data-admin-shell]');
    const key = 'quite-admin:home-view:' + JSON.stringify([shell.dataset.storageKey, shell.dataset.userKey]);
    localStorage.setItem(key, '{invalid');
  });
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
  await option(page, 'list').click();
  await other.evaluate(() => localStorage.clear());
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
  await page.reload();
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
});

test('view preference is isolated by mount and user and cleanup leaves a usable native catalog', async ({page}) => {
  await login(page);
  await option(page, 'list').click();
  await login(page, '/dark');
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
  await page.goto('/admin/');
  await expect(home(page)).toHaveAttribute('data-home-view', 'list');
  await page.evaluate(() => {
    const dashboard = document.querySelector('[data-dashboard]');
    dashboard.quiteAdminDashboardCleanup();
    document.querySelector('[data-admin-shell]').dataset.userKey = 'another-user';
    window.quiteAdminDashboard(document);
  });
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
  await option(page, 'list').click();
  await page.evaluate(() => document.querySelector('[data-dashboard]').quiteAdminDashboardCleanup());
  await expect(home(page).locator('[data-home-view-controls]')).toBeHidden();
  await expect(catalog(page)).toBeVisible();
  await expect(catalog(page)).not.toHaveAttribute('open', '');
  await catalog(page).locator(':scope > summary').press('Enter');
  await expect(catalog(page)).toHaveAttribute('open', '');
  await page.evaluate(() => window.quiteAdminDashboard(document));
  await expect(home(page)).toHaveAttribute('data-home-view', 'list');
  await option(page, 'cards').click();
  await expect(catalog(page)).toHaveAttribute('open', '');
});

test('view switching works when storage is blocked and a fresh page still defaults to Cards', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {get() { throw new Error('Storage disabled'); }}));
  await login(page);
  await option(page, 'list').click();
  await expect(home(page)).toHaveAttribute('data-home-view', 'list');
  await expect(catalog(page).locator('[data-table-link="entries"]')).toBeVisible();
  await option(page, 'cards').click();
  await expect(home(page).locator('[data-home-shortcuts]')).toBeVisible();
  await option(page, 'list').click();
  await page.reload();
  await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
  expect(errors).toEqual([]);
});

test('Table list stars share favorites with search, Cards and record-list headings without navigating', async ({page}) => {
  await login(page);
  await option(page, 'list').click();
  const star = catalog(page).locator('[data-table-pin="entries"]');
  await expect(star).toHaveAccessibleName('Pin table: Entries');
  await expect(star.locator('svg')).toBeVisible();
  await expect(catalog(page).locator('a button')).toHaveCount(0);
  await star.press('Enter');
  await expect(page).toHaveURL(/\/admin\/$/);
  await expect(star).toHaveAttribute('aria-pressed', 'true');
  await expect(star).toHaveAccessibleName('Unpin table: Entries');
  await page.keyboard.press('Control+k');
  await page.locator('[data-table-search-input]').fill('entries');
  const searchStar = page.locator('[data-table-search-dialog] [data-table-pin="entries"]');
  await expect(searchStar).toHaveAttribute('aria-pressed', 'true');
  await searchStar.click();
  await page.keyboard.press('Escape');
  await expect(star).toHaveAttribute('aria-pressed', 'false');
  await star.press('Space');
  await option(page, 'cards').click();
  const pinned = home(page).locator('[data-home-pinned] [data-home-table="entries"]');
  await expect(pinned).toBeVisible();
  await home(page).locator('[data-home-unpin="entries"]').click();
  await option(page, 'list').click();
  await expect(star).toHaveAttribute('aria-pressed', 'false');
  await star.click();
  await catalog(page).locator('[data-table-link="entries"]').click();
  const headingStar = page.locator('.list-heading [data-table-pin="entries"]');
  await expect(headingStar).toHaveAttribute('aria-pressed', 'true');
  await headingStar.click();
  await page.locator('.sidebar-home').click();
  await expect(star).toHaveAttribute('aria-pressed', 'false');
  await page.reload();
  await expect(star).toHaveAttribute('aria-pressed', 'false');
});

test('both Home views fit narrow screens with long table names and enlarged text', async ({page}) => {
  await page.route('**/assets/admin.css', async route => {
    const response = await route.fetch();
    await route.fulfill({response, body:(await response.text()) + '\n:root { --ui-font-size: 200%; }'});
  });
  await page.setViewportSize({width:390, height:844});
  await login(page);
  await page.evaluate(() => {
    const link = document.querySelector('[data-home-catalog] .table-catalog-link');
    link.querySelector('span').textContent = 'Long table name '.repeat(10);
    const name = document.createElement('code'); name.textContent = 'long_technical_name_'.repeat(10); link.append(name);
  });
  for (const width of [390,800,1280]) {
    await page.setViewportSize({width, height:844});
    for (const view of ['list','cards']) {
      await option(page, view).click();
      await expect(option(page, view)).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (view === 'list') {
        for (const star of await catalog(page).locator('[data-table-pin]').all()) {
          const bounds = await star.boundingBox();
          expect(bounds.x).toBeGreaterThanOrEqual(0);
          expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        }
        for (const text of await catalog(page).locator('.table-catalog-link > span, .table-catalog-link > code').all()) {
          expect(await text.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
        }
      }
    }
  }
});

test.describe('browser demo', () => {
  test.use({baseURL:'http://127.0.0.1:8128'});
  test('the shared view survives demo language changes, navigation and reload', async ({page}) => {
    await page.goto('/');
    await page.getByLabel('Username', {exact:true}).fill('admin');
    await page.getByLabel('Password', {exact:true}).fill('admin');
    await page.getByRole('button', {name:'Sign in', exact:true}).click();
    await expect(home(page)).toHaveAttribute('data-home-view', 'cards');
    await option(page, 'list').click();
    const count = await catalog(page).locator('a[data-table-link]').count();
    expect(count).toBeGreaterThan(2);
    await page.locator('#demo-language').selectOption('ru');
    await expect(home(page)).toHaveAttribute('data-home-view', 'list');
    await expect(home(page).getByRole('group', {name:'Вид главной',exact:true})).toBeVisible();
    await expect(option(page, 'cards')).toHaveText('Карточки');
    await expect(option(page, 'list')).toHaveText('Список таблиц');
    await catalog(page).locator('[data-table-link="products"]').click();
    await expect(page).toHaveURL(/#\/models\/products\/$/);
    await page.locator('.sidebar-home').click();
    await expect(home(page)).toHaveAttribute('data-home-view', 'list');
    await page.reload();
    await expect(home(page)).toHaveAttribute('data-home-view', 'list');
    await expect(catalog(page).locator('a[data-table-link]')).toHaveCount(count);
    await option(page, 'cards').click();
    await expect(home(page).locator('[data-home-shortcuts]')).toBeVisible();
  });
});
