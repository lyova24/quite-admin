import {test, expect} from '@playwright/test';

async function login(page, demo = false) {
  await page.goto(demo ? 'http://127.0.0.1:8128/' : '/admin/');
  await page.getByLabel('Username', {exact: true}).fill('admin');
  await page.getByLabel('Password', {exact: true}).fill(demo ? 'admin' : 'browser-test-password');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Sign in', exact: true})).toHaveCount(0);
  if (demo) await page.locator('[data-tour-consent]').getByRole('button', {name: 'Not now', exact: true}).click();
}

async function openCustomer(page) {
  await login(page);
  await page.goto('/admin/models/customers/WyI1MSJd');
  const picker = page.locator('[data-relation-picker]').filter({has: page.locator('select[multiple]')}).first();
  await expect(picker.locator('.picker-trigger')).toBeVisible();
  return picker;
}

async function formGeometry(picker) {
  return picker.evaluate(root => {
    const box = node => {
      const rect = node.getBoundingClientRect();
      return {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height};
    };
    return {
      form: box(root.closest('.record-form')),
      field: box(root.parentElement),
      following: box(root.parentElement.querySelector('[data-overlay-following]')),
      scrollX, scrollY,
    };
  });
}

async function expectFitsViewport(page, locator) {
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds.x).toBeGreaterThanOrEqual(-1);
  expect(bounds.y).toBeGreaterThanOrEqual(-1);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(page.viewportSize().height + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const width of [390, 1512]) {
  test(`opening a relation overlays the following form content without moving it at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 844});
    const picker = await openCustomer(page);
    await picker.evaluate(root => {
      const marker = document.createElement('p');
      marker.dataset.overlayFollowing = '';
      marker.className = 'field-help';
      marker.textContent = 'The next field stays in its original position.';
      root.after(marker);
      root.loadOptions = async () => ({
        items: Array.from({length: 25}, (_, index) => ({key: 'candidate-' + index, label: 'Candidate ' + index})),
        total: 50,
        has_next: true,
      });
    });
    const trigger = picker.locator('.picker-trigger');
    await trigger.scrollIntoViewIfNeeded();
    const closed = await formGeometry(picker);
    await trigger.click();
    await expect(picker.getByRole('checkbox')).toHaveCount(25);
    await expect(picker.getByRole('searchbox')).toBeFocused();
    expect(await formGeometry(picker)).toEqual(closed);
    await expectFitsViewport(page, picker.locator('.picker-panel'));
    await picker.getByRole('searchbox').press('Escape');
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(await formGeometry(picker)).toEqual(closed);
  });

  test(`a relation near the viewport bottom opens upward and keeps its long results inside ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 700});
    const picker = await openCustomer(page);
    await picker.evaluate(root => {
      const spacer = document.createElement('div');
      spacer.style.height = innerHeight + 'px';
      root.closest('.record-form').before(spacer);
      const end = document.createElement('div');
      end.style.height = innerHeight + 'px';
      root.closest('.record-form').after(end);
      root.loadOptions = async () => ({
        items: Array.from({length: 25}, (_, index) => ({
          key: 'candidate-' + index,
          label: 'Candidate ' + index + ': ' + 'a related record with a long descriptive label '.repeat(3),
        })),
        total: 50,
        has_next: true,
      });
      root.querySelector('.picker-trigger').scrollIntoView({block: 'end'});
      scrollBy(0, 112);
    });
    const trigger = picker.locator('.picker-trigger');
    const before = await trigger.boundingBox();
    expect(before.y).toBeGreaterThan(page.viewportSize().height / 2);
    await trigger.click();
    await expect(picker.getByRole('checkbox')).toHaveCount(25);
    const panel = picker.locator('.picker-panel');
    await expectFitsViewport(page, panel);
    const panelBounds = await panel.boundingBox();
    const triggerBounds = await trigger.boundingBox();
    expect(panelBounds.y + panelBounds.height).toBeLessThanOrEqual(triggerBounds.y + 1);
    expect(await picker.locator('.picker-results').evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
    await picker.getByRole('searchbox').press('Escape');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toBeFocused();
  });
}

test('multiple selection survives outside dismissal, Escape and keyboard tabbing out of the overlay', async ({page}) => {
  const picker = await openCustomer(page);
  const trigger = picker.locator('.picker-trigger');
  const values = () => picker.locator('select').evaluate(select => [...select.selectedOptions].map(option => option.value));
  await trigger.click();
  const search = picker.getByRole('searchbox');
  await expect(search).toBeFocused();
  const options = picker.getByRole('checkbox');
  await expect(options.first()).toBeVisible();
  const first = options.first();
  const key = await first.getAttribute('data-key');
  const wasChecked = await first.isChecked();
  await search.press('ArrowDown');
  await expect(first).toBeFocused();
  await first.press('Space');
  await expect(first).toBeChecked({checked: !wasChecked});
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  const chosen = await values();
  expect(chosen.includes(key)).toBe(!wasChecked);

  // The empty edge of the fixed rail is outside the picker and has no navigation target.
  await page.mouse.click(3, page.viewportSize().height / 2);
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  expect(await values()).toEqual(chosen);
  await expect(page).toHaveURL(/\/customers\/WyI1MSJd$/);

  await trigger.click();
  await expect(search).toBeFocused();
  await search.press('Escape');
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(trigger).toBeFocused();
  expect(await values()).toEqual(chosen);

  await trigger.click();
  const lastControl = picker.locator('.picker-panel input:visible:not(:disabled), .picker-panel button:visible:not(:disabled)').last();
  await lastControl.focus();
  await lastControl.press('Tab');
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  expect(await values()).toEqual(chosen);
  expect(await picker.evaluate(root => root.contains(document.activeElement))).toBe(false);
});

test('opening another relationship closes the previous overlay without changing its selection', async ({page}) => {
  await login(page, true);
  const seed = await (await page.request.get('http://127.0.0.1:8128/seed.json')).json();
  const customer = seed.collections.customers.records[0];
  await page.goto(`http://127.0.0.1:8128/#/models/customers/${encodeURIComponent(customer.key)}`);
  const pickers = page.locator('[data-relation-picker].is-enhanced');
  expect(await pickers.count()).toBeGreaterThanOrEqual(2);
  const first = pickers.nth(0), second = pickers.nth(1);
  const firstTrigger = first.locator('.picker-trigger');
  const secondTrigger = second.locator('.picker-trigger');
  const chosen = await first.locator('select').evaluate(select => [...select.selectedOptions].map(option => option.value));
  await firstTrigger.click();
  await expect(firstTrigger).toHaveAttribute('aria-expanded', 'true');
  await expect(first.getByRole('searchbox')).toBeFocused();
  await secondTrigger.focus();
  await secondTrigger.press('Enter');
  await expect(firstTrigger).toHaveAttribute('aria-expanded', 'false');
  await expect(secondTrigger).toHaveAttribute('aria-expanded', 'true');
  await expect(second.getByRole('searchbox')).toBeFocused();
  await expect(page.locator('.picker-menu[open]')).toHaveCount(1);
  expect(await first.locator('select').evaluate(select => [...select.selectedOptions].map(option => option.value))).toEqual(chosen);
  await second.getByRole('searchbox').press('Escape');
  await expect(secondTrigger).toBeFocused();
  await expect(page.locator('.picker-menu[open]')).toHaveCount(0);
});

async function watchSelectionChanges(picker) {
  await picker.evaluate(root => {
    root.selectionChanges = 0;
    root.querySelector('select').addEventListener('change', () => { root.selectionChanges++; });
  });
}

async function expectSelectionChanges(picker, count) {
  await expect.poll(() => picker.evaluate(root => root.selectionChanges)).toBe(count);
}

async function clickRowText(row) {
  // A real pointer sequence, including time for focusout handlers before mouseup.
  await row.locator('.picker-option-text > span').first().click({position: {x: 8, y: 8}, delay: 80});
}

async function clickRowPadding(row) {
  const bounds = await row.boundingBox();
  await row.click({position: {x: bounds.width - 3, y: bounds.height / 2}, delay: 80});
}

test('single relation text and empty row padding select exactly once, alongside native and keyboard controls', async ({page}) => {
  await page.setViewportSize({width: 1512, height: 900});
  await login(page);
  await page.goto('/admin/models/entries/new');
  const picker = page.locator('[data-relation-picker]').filter({
    has: page.locator('[name="__relation__to_customers_by_customer_id"]'),
  });
  const trigger = picker.locator('.picker-trigger');
  const search = picker.getByRole('searchbox');
  const select = picker.locator('select');
  async function findCustomer(id, label) {
    if (!(await picker.locator('details').evaluate(node => node.open))) await trigger.click();
    await expect(search).toBeFocused();
    await search.fill(id);
    const row = picker.locator('.picker-option').filter({hasText: label});
    await expect(row).toHaveCount(1);
    await expect(row.getByRole('radio')).toBeEnabled();
    return row;
  }
  let row = await findCustomer('52', 'Maria Jones');
  await watchSelectionChanges(picker);
  await clickRowText(row);
  await expect(select).toHaveValue('WyI1MiJd');
  await expectSelectionChanges(picker, 1);
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');

  row = await findCustomer('51', 'Alex Johnson');
  await clickRowPadding(row);
  await expect(select).toHaveValue('WyI1MSJd');
  await expectSelectionChanges(picker, 2);
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');

  row = await findCustomer('52', 'Maria Jones');
  await row.getByRole('radio').check();
  await expect(select).toHaveValue('WyI1MiJd');
  await expectSelectionChanges(picker, 3);

  row = await findCustomer('51', 'Alex Johnson');
  await search.press('ArrowDown');
  await expect(row.getByRole('radio')).toBeFocused();
  await row.getByRole('radio').press('Space');
  await expect(select).toHaveValue('WyI1MSJd');
  await expectSelectionChanges(picker, 4);
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(page).toHaveURL(/\/entries\/new$/);
});

test('multiple relation text and row padding toggle once and retain direct checkbox and keyboard behavior', async ({page}) => {
  await page.setViewportSize({width: 1512, height: 900});
  const picker = await openCustomer(page);
  const trigger = picker.locator('.picker-trigger');
  await trigger.click();
  const search = picker.getByRole('searchbox');
  await expect(picker.getByRole('checkbox').first()).toBeEnabled();
  const clear = picker.getByRole('button', {name: 'Clear selection', exact: true});
  if (await clear.isVisible()) await clear.click();
  if (!(await picker.locator('details').evaluate(node => node.open))) await trigger.click();
  await expect(picker.getByRole('checkbox').first()).toBeEnabled();
  const row = picker.locator('.picker-option').first();
  const check = row.getByRole('checkbox');
  const key = await check.getAttribute('data-key');
  const values = () => picker.locator('select').evaluate(select => [...select.selectedOptions].map(option => option.value));
  expect(await values()).toEqual([]);
  await watchSelectionChanges(picker);

  await search.focus();
  await clickRowText(row);
  expect(await values()).toEqual([key]);
  await expectSelectionChanges(picker, 1);
  await expect(check).toBeChecked();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');

  await search.focus();
  await clickRowText(row);
  expect(await values()).toEqual([]);
  await expectSelectionChanges(picker, 2);
  await expect(check).not.toBeChecked();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');

  await search.focus();
  await clickRowPadding(row);
  expect(await values()).toEqual([key]);
  await expectSelectionChanges(picker, 3);
  await check.uncheck();
  expect(await values()).toEqual([]);
  await expectSelectionChanges(picker, 4);

  await search.focus();
  await search.press('ArrowDown');
  await expect(check).toBeFocused();
  await check.press('Space');
  expect(await values()).toEqual([key]);
  await expectSelectionChanges(picker, 5);
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await check.press('Escape');
  await expect(trigger).toBeFocused();
  expect(await values()).toEqual([key]);
});

for (const width of [390, 1512]) {
  test(`short relationship options and search stay compact without overflowing at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 844});
    await login(page);
    await page.goto('/admin/models/entries/new');
    const picker = page.locator('[data-relation-picker]').filter({
      has: page.locator('[name="__relation__to_customers_by_customer_id"]'),
    });
    await picker.locator('.picker-trigger').click();
    await picker.getByRole('searchbox').fill('52');
    await expect(picker.getByRole('radio')).toHaveCount(1);
    await expect(picker.getByRole('radio')).toBeEnabled();
    const panel = picker.locator('.picker-panel');
    await expectFitsViewport(page, panel);
    const geometry = await panel.evaluate(panel => ({
      width: panel.getBoundingClientRect().width,
      rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
      searchHeight: panel.querySelector('input[type=search]').getBoundingClientRect().height,
      rowHeights: [...panel.querySelectorAll('.picker-option')].map(row => row.getBoundingClientRect().height),
    }));
    expect(geometry.width).toBeLessThanOrEqual(32 * geometry.rem + 1);
    expect(geometry.searchHeight).toBeLessThanOrEqual(36);
    expect(geometry.rowHeights.length).toBeGreaterThan(0);
    for (const height of geometry.rowHeights) expect(height).toBeLessThanOrEqual(38);
    await picker.getByRole('searchbox').press('Escape');
  });
}
