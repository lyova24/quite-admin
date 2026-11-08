import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username', {exact: true}).fill('admin');
  await page.getByLabel('Password', {exact: true}).fill('browser-test-password');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
}

const homeSearch = page => page.locator('[data-dashboard] [data-table-search]').first();
const searchDialog = page => page.locator('[data-table-search-dialog]');
const searchInput = page => searchDialog(page).locator('[data-table-search-input]');
const searchResults = page => searchDialog(page).locator('[data-table-search-results]');

test('Home opens global search with focus and keyboard shortcuts also work from table lists', async ({page}) => {
  await login(page);
  await expect(page.getByRole('heading', {name: 'Quite Admin', exact: true})).toBeVisible();
  await expect(page.locator('[data-home-pinned-section]')).toBeVisible();
  await expect(page.locator('[data-home-recent-section]')).toBeVisible();
  await expect(searchDialog(page)).toBeHidden();
  const opener = homeSearch(page);
  await expect(opener).toContainText('Find a table');
  await opener.click();
  const input = searchInput(page);
  await expect(input).toBeFocused();
  await input.fill('ENTRIES');
  await expect(searchResults(page).locator('a')).toHaveCount(1);
  await expect(searchResults(page).locator('a')).toHaveAttribute('href', '/admin/models/entries/');
  await input.fill('data');
  await expect(searchResults(page).locator('a')).toHaveCount(1);
  await expect(searchResults(page).locator('a')).toContainText('Entries');
  await input.fill('there-is-no-such-table');
  await expect(searchResults(page).locator('a')).toHaveCount(0);
  await expect(searchDialog(page).locator('[data-table-search-count]')).toHaveText('No matching tables.');
  await page.keyboard.press('Escape');
  await expect(searchDialog(page)).toBeHidden();
  await expect(opener).toBeFocused();
  await page.keyboard.press('Control+k');
  await expect(input).toBeFocused();
  await input.fill('entries');
  await input.press('Enter');
  await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
  const listButton = page.locator('[data-filter-add]');
  await expect(listButton).toBeVisible();
  await listButton.focus();
  await expect(listButton).toBeFocused();
  for (const shortcut of ['Control+k', 'Meta+k']) {
    await page.keyboard.press(shortcut);
    await expect(searchInput(page)).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(searchDialog(page)).toBeHidden();
    await expect(listButton).toBeFocused();
  }
});

test('Home pins persist, removing pins keeps focus useful and visited tables appear in recent', async ({page}) => {
  await login(page);
  await homeSearch(page).click();
  await searchInput(page).fill('entries');
  await searchDialog(page).locator('[data-table-pin="entries"]').click();
  await expect(searchDialog(page).locator('[data-table-pin="entries"]')).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  const pinned = page.locator('[data-home-pinned]');
  await expect(pinned.locator('[data-home-table="entries"]')).toBeVisible();
  await page.reload();
  await expect(pinned.locator('[data-home-table="entries"]')).toBeVisible();
  await page.locator('[data-home-pinned-section] [data-table-search]').click();
  await searchInput(page).fill('customers');
  await searchDialog(page).locator('[data-table-pin="customers"]').click();
  await page.keyboard.press('Escape');
  await expect(pinned.locator('[data-home-table]')).toHaveCount(2);
  await pinned.locator('[data-home-unpin="entries"]').click();
  await expect(pinned.locator('[data-home-table="entries"]')).toHaveCount(0);
  await expect(pinned.locator('[data-home-unpin="customers"]')).toBeFocused();
  await pinned.locator('[data-home-unpin="customers"]').click();
  await expect(pinned.locator('[data-home-table]')).toHaveCount(0);
  await expect(homeSearch(page)).toBeFocused();
  await homeSearch(page).click();
  await searchInput(page).fill('entries');
  await searchInput(page).press('Enter');
  await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
  await page.goto('/admin/');
  await expect(page.locator('[data-home-recent] [data-home-table]').first()).toHaveAttribute('data-home-table', 'entries');
  await expect(page.locator('[data-home-recent] [data-home-table="entries"]')).toBeVisible();
});

test('search stays focused and fully visible on a short mobile screen', async ({page}) => {
  await page.setViewportSize({width: 390, height: 400});
  await login(page);
  await homeSearch(page).click();
  await expect(searchInput(page)).toBeFocused();
  await expect(searchInput(page)).toBeInViewport();
  const bounds = await searchDialog(page).boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(400);
  await searchInput(page).fill('entries');
  await searchInput(page).press('ArrowDown');
  await expect(searchResults(page).locator('a')).toBeFocused();
  await expect(searchResults(page).locator('a')).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(homeSearch(page)).toBeFocused();
});

test.describe('without JavaScript', () => {
  test.use({javaScriptEnabled: false});
  test('the full Home catalog remains browsable without JavaScript', async ({page}) => {
    await login(page);
    await expect(page.locator('[data-table-search]:visible')).toHaveCount(0);
    const directory = page.locator('[data-home-catalog]');
    await directory.locator(':scope > summary').press('Enter');
    const group = directory.locator('[data-group="Data"]');
    await group.locator('summary').press('Enter');
    const link = directory.locator('[data-table-link="entries"]');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/admin\/models\/entries\/$/);
    await expect(page.locator('[data-home-catalog]')).toHaveCount(0);
    await page.locator('.sidebar-home').click();
    await expect(directory).toBeVisible();
  });
});

test.describe('browser demo', () => {
  test.use({baseURL: 'http://127.0.0.1:8128'});
  test('shared search finds labels, names and groups, localizes empty results and persists Home shortcuts', async ({page}) => {
    await page.goto('/');
    await page.getByLabel('Username', {exact: true}).fill('admin');
    await page.getByLabel('Password', {exact: true}).fill('admin');
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    await homeSearch(page).click();
    await expect(searchInput(page)).toBeFocused();
    await searchInput(page).fill('Customer Profiles');
    await expect(searchResults(page).locator('a')).toHaveCount(1);
    await expect(searchResults(page).locator('a')).toContainText('Customer Profiles');
    await searchInput(page).fill('customer_profiles');
    await expect(searchResults(page).locator('a')).toHaveCount(1);
    await expect(searchResults(page).locator('a')).toHaveAttribute('href', '#/models/customer_profiles/');
    await searchInput(page).fill('Catalog');
    await expect(searchResults(page).locator('a')).toHaveCount(2);
    await searchInput(page).fill('nothing-matches');
    await expect(searchDialog(page).locator('[data-table-search-count]')).toHaveText('No matching tables.');
    await page.keyboard.press('Escape');
    await expect(homeSearch(page)).toBeFocused();
    await page.locator('#demo-language').selectOption('ru');
    await expect(homeSearch(page)).toContainText('Найти таблицу');
    await homeSearch(page).click();
    await expect(searchInput(page)).toBeFocused();
    await expect(searchInput(page)).toHaveAttribute('placeholder', 'Поиск таблиц');
    await searchInput(page).fill('такой-таблицы-нет');
    await expect(searchDialog(page).locator('[data-table-search-count]')).toHaveText('Таблицы не найдены.');
    await searchInput(page).fill('customer_profiles');
    await searchDialog(page).locator('[data-table-pin="customer_profiles"]').click();
    await page.keyboard.press('Escape');
    const pinned = page.locator('[data-home-pinned] [data-home-table="customer_profiles"]');
    await expect(pinned).toBeVisible();
    await page.reload();
    await expect(pinned).toBeVisible();
    await pinned.click();
    await expect(page).toHaveURL(/#\/models\/customer_profiles\/$/);
    await page.locator('.sidebar-home').click();
    await expect(page.locator('[data-home-recent] [data-home-table="customer_profiles"]')).toBeVisible();
    await page.locator('[data-home-unpin="customer_profiles"]').click();
    await expect(pinned).toHaveCount(0);
    await expect(homeSearch(page)).toBeFocused();
  });
});
