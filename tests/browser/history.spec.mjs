import {test, expect} from '@playwright/test';

async function openPeriod(page, tab) {
  await page.locator('[data-history-period] > summary').click();
  const panel = page.getByRole('dialog', {name: 'Choose period', exact: true});
  if (tab) await panel.getByRole('tab', {name: tab, exact: true}).click();
  return panel;
}

async function chooseFilter(page, field, value) {
  await page.locator('[data-filter-add]').click();
  const dialog = page.locator('#filter-editor');
  await dialog.locator('[data-field="' + field + '"]').click();
  const result = dialog.locator('.filter-related-results').getByRole('button', {name: value, exact: typeof value === 'string'});
  await result.click();
  await dialog.getByRole('button', {name: 'Apply filter', exact: true}).click();
  await expect(dialog).not.toBeVisible();
}

test.beforeEach(async ({page}) => {
  await page.goto('/admin/');
  await page.locator('[name=username]').fill('admin');
  await page.locator('[name=password]').fill('browser-test-password');
  await Promise.all([
    page.waitForURL(url => url.pathname === '/admin/'),
    page.getByRole('button', {name: 'Sign in', exact: true}).click(),
  ]);
});

test('history filters the authenticated user and collection in journal cards', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/admin/models/entries/');
  await page.getByRole('link', {name: 'Activity history', exact: true}).click();
  await chooseFilter(page, 'subject', /admin/);
  await chooseFilter(page, 'collection', 'Entries');
  await chooseFilter(page, 'action', 'Browse records');
  const cards = page.locator('.activity-event');
  await expect(cards.first()).toContainText('admin');
  await expect(cards.first()).toContainText('Entries');
  await expect(cards.first()).toContainText('Browse records');
  await expect(cards.first()).toContainText('Success');
  await expect(page.locator('.activity-journal')).not.toContainText('Alex Smith');
  await expect(page.getByLabel('Collection', {exact: true})).toHaveValue('entries');
  const period = await openPeriod(page, 'Quick select');
  await period.getByRole('button', {name: 'Today', exact: true}).click();
  const today = await page.locator('[data-history-period]').getAttribute('data-today');
  await page.getByRole('link', {name: 'Remove: Collection: Entries', exact: true}).click();
  await expect(page.locator('.active-filters')).toContainText('User: admin');
  await expect(page.locator('.active-filters')).not.toContainText('Collection: Entries');
  await expect(page.locator('[name=date]')).toHaveValue(today);
  await page.getByRole('navigation', {name: 'Activity view'}).getByRole('link', {name: 'Table', exact: true}).click();
  await page.getByRole('link', {name: 'Clear all', exact: true}).click();
  await expect(page.locator('[data-filter-edit]')).toHaveCount(0);
  await expect(page.locator('[name=date_mode]')).toHaveValue('day');
  await expect(page.locator('[name=date]')).toHaveValue(today);
  await expect(page.getByRole('table', {name: 'Activity history', exact: true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('persisted field changes show before and after with working expand controls', async ({page}) => {
  const name = 'history-' + crypto.randomUUID();
  await page.goto('/admin/models/entries/new');
  await page.locator('[name=name]').fill(name);
  await page.getByRole('button', {name: 'Create record', exact: true}).click();
  await expect(page.locator('[name=name]')).toHaveValue(name);
  await page.locator('[name=name]').fill(name + '-changed');
  await page.getByRole('button', {name: 'Save changes', exact: true}).click();
  await expect(page.locator('[name=name]')).toHaveValue(name + '-changed');
  await page.getByRole('link', {name: 'Activity history', exact: true}).click();
  await expect(page.getByLabel('Action', {exact: true})).toHaveValue('changes');
  const card = page.locator('.activity-event').filter({hasText: name + '-changed'}).first();
  await expect(card.locator('.activity-before')).toContainText(name);
  await expect(card.locator('.activity-after')).toContainText(name + '-changed');
  await expect(card.getByRole('table', {name: 'Field changes'})).toBeVisible();
  await page.getByRole('button', {name: 'Collapse all changes', exact: true}).click();
  await expect(card.getByRole('table', {name: 'Field changes'})).toBeHidden();
  await page.getByRole('button', {name: 'Expand all changes', exact: true}).click();
  await expect(card.getByRole('table', {name: 'Field changes'})).toBeVisible();
  const day = (await card.locator('time').getAttribute('datetime')).slice(0, 10);
  await expect(page.locator('[data-history-period] > summary')).toContainText('Any date');
  const period = await openPeriod(page, 'Specific day');
  await expect(period.getByLabel('Date from (UTC)', {exact: true})).toBeDisabled();
  await period.getByLabel('Date (UTC)', {exact: true}).fill(day);
  await period.getByRole('button', {name: 'Apply period', exact: true}).click();
  await expect(card).toBeVisible();
  const views = page.getByRole('navigation', {name: 'Activity view'});
  await expect(views.getByRole('link', {name: 'Journal', exact: true})).toHaveAttribute('aria-current', 'page');
  await views.getByRole('link', {name: 'Table', exact: true}).click();
  const row = page.getByRole('table', {name: 'Activity history', exact: true}).locator('tbody tr').filter({hasText: name + '-changed'}).first();
  await expect(page.locator('.activity-journal')).toHaveCount(0);
  await expect(views.getByRole('link', {name: 'Table', exact: true})).toHaveAttribute('aria-current', 'page');
  await expect(row.locator('.activity-changes')).not.toHaveAttribute('open');
  await row.locator('summary').click();
  await expect(row.locator('.activity-before')).toContainText(name);
  await expect(row.locator('.activity-after')).toContainText(name + '-changed');
  await chooseFilter(page, 'subject', /admin/);
  await chooseFilter(page, 'collection', 'Entries');
  await expect(page.getByRole('table', {name: 'Activity history', exact: true})).toBeVisible();
  await expect(page.getByLabel('Collection', {exact: true})).toHaveValue('entries');
  await expect(page.locator('[name=date_mode]')).toHaveValue('day');
  await expect(page.getByLabel('Date (UTC)', {exact: true})).toHaveValue(day);
  await page.reload();
  await expect(page.getByRole('table', {name: 'Activity history', exact: true})).toBeVisible();
  await views.getByRole('link', {name: 'Journal', exact: true}).click();
  await expect(page.locator('.activity-journal')).toBeVisible();
  await expect(page.getByLabel('User', {exact: true})).toHaveValue('admin');
  await expect(page.getByLabel('Collection', {exact: true})).toHaveValue('entries');
  await expect(page.locator('[name=date_mode]')).toHaveValue('day');
  await expect(page.getByLabel('Date (UTC)', {exact: true})).toHaveValue(day);
  await openPeriod(page, 'Date range');
  await expect(page.getByLabel('Date (UTC)', {exact: true})).toBeDisabled();
  await expect(page.getByLabel('Date from (UTC)', {exact: true})).toHaveValue(day);
  await expect(page.getByLabel('Date to (UTC)', {exact: true})).toHaveValue(day);
  await page.getByLabel('Date from (UTC)', {exact: true}).fill('2000-01-01');
  await page.getByLabel('Date to (UTC)', {exact: true}).fill('2000-01-01');
  await period.getByRole('button', {name: 'Apply period', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'No activity found', exact: true})).toBeVisible();
  await openPeriod(page, 'Quick select');
  await period.getByRole('button', {name: 'Any date', exact: true}).click();
  await expect(card).toBeVisible();
  await page.getByRole('link', {name: 'Clear all', exact: true}).click();
  await expect(page.locator('[name=date_mode]')).toHaveValue('all');
  await expect(page.getByLabel('Date from (UTC)', {exact: true})).toHaveValue('');
  await expect(page.getByLabel('Date to (UTC)', {exact: true})).toHaveValue('');
  await chooseFilter(page, 'action', 'Changes only');
  await expect(card).toBeVisible();
});

test('user lookup in the shared filter editor uses bounded searches', async ({page}) => {
  await page.goto('/admin/history');
  await page.locator('[data-filter-add]').click();
  const dialog = page.locator('#filter-editor');
  const search = dialog.getByRole('searchbox', {name: 'Search values', exact: true});
  await search.fill('nobody-with-this-subject');
  await expect(dialog.locator('.filter-related-results button')).toHaveCount(0);
  await search.fill('adm');
  const result = dialog.locator('.filter-related-results button');
  await expect(result).toHaveCount(1);
  await expect(result).toContainText('admin');
  await result.click();
  await dialog.getByRole('button', {name: 'Apply filter', exact: true}).click();
  await expect(page.locator('.active-filters')).toContainText('admin');
});

test('period popover cancels drafts, supports keyboard navigation and applies quick presets', async ({page}) => {
  await page.goto('/admin/history');
  const period = await openPeriod(page, 'Specific day');
  await period.getByLabel('Date (UTC)', {exact: true}).fill('2000-01-01');
  await period.getByRole('button', {name: 'Cancel', exact: true}).click();
  await expect(period).toBeHidden();
  await expect(page.locator('[name=date_mode]')).toHaveValue('all');
  await openPeriod(page, 'Specific day');
  const selected = period.getByRole('tab', {name: 'Specific day', exact: true});
  await selected.press('ArrowRight');
  await expect(period.getByRole('tab', {name: 'Date range', exact: true})).toHaveAttribute('aria-selected', 'true');
  await period.getByLabel('Date from (UTC)', {exact: true}).fill('2024-02-29');
  await period.getByLabel('Date to (UTC)', {exact: true}).fill('2024-02-28');
  await expect(period.locator('[data-period-error]')).toBeVisible();
  await period.getByLabel('Date to (UTC)', {exact: true}).press('Escape');
  await expect(period).toBeHidden();
  await expect(page.locator('[name=date_mode]')).toHaveValue('all');
  await openPeriod(page, 'Quick select');
  const today = await page.locator('[data-history-period]').getAttribute('data-today');
  await period.getByRole('button', {name: 'Today', exact: true}).click();
  await expect(page.locator('[data-history-period] > summary')).toContainText('Today');
  await expect(page.locator('[name=date_mode]')).toHaveValue('day');
  await expect(page.locator('[name=date]')).toHaveValue(today);
  await openPeriod(page, 'Specific day');
  await period.getByLabel('Date (UTC)', {exact: true}).fill('2000-01-01');
  await page.locator('[data-filter-add]').press('Enter');
  await expect(period).toBeHidden();
  await expect(page.locator('[name=date]')).toHaveValue(today);
  await page.locator('#filter-editor').getByRole('button', {name: 'Cancel', exact: true}).click();
  await openPeriod(page, 'Specific day');
  await period.getByRole('group', {name: 'Choose date: Date (UTC)', exact: true}).locator('[data-iso="' + today + '"]').press('ArrowRight');
  await page.getByRole('heading', {name: 'Activity history', exact: true}).click();
  await expect(period).toBeHidden();
  await expect(page.locator('[name=date]')).toHaveValue(today);
});
