import {test, expect} from '@playwright/test';

test.beforeEach(async ({page}) => {
  await page.goto('/admin/');
  await page.locator('[name=username]').fill('admin');
  await page.locator('[name=password]').fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
});

test('forms edit date and time directly and commit a calendar day with one click', async ({page}) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/admin/models/entries/new');
  const moment = page.locator('.form-temporal').filter({has:page.locator('#field-moment-time')});
  const raw = '2026-11-01T12:34:56.120000+03:00';
  await page.locator('#field-moment-date').fill('2026-11-01');
  await page.locator('#field-moment-time').fill('12:34:56');
  await moment.locator('summary').click();
  await moment.getByLabel('Fractional seconds (optional)', {exact:true}).fill('120000');
  await moment.getByLabel('UTC offset (optional)', {exact:true}).fill('+03:00');
  await moment.locator('summary').click();
  await expect(page.locator('[name=moment]')).toHaveValue(raw);
  await expect(page.locator('[name=moment]')).toBeHidden();
  const scroll = await page.evaluate(() => window.scrollY);
  await moment.getByRole('button', {name:'Choose date', exact:true}).click();
  const panel = page.locator('.form-date-panel:not([hidden])');
  await expect(panel.locator('input[type=date],input[type=time]')).toHaveCount(0);
  await expect(panel.getByRole('button', {name:'Apply', exact:true})).toHaveCount(0);
  expect(Math.abs(await page.evaluate(() => window.scrollY) - scroll)).toBeLessThan(24);
  await panel.getByRole('button', {name:'2026-11-02', exact:true}).click();
  await expect(panel).toBeHidden();
  await expect(page.locator('[name=moment]')).toHaveValue('2026-11-02' + raw.slice(10));
  await moment.getByRole('button', {name:'Choose date', exact:true}).click();
  await panel.getByRole('button', {name:'Next month', exact:true}).click();
  await panel.getByRole('button', {name:'Previous month', exact:true}).press('Escape');
  await expect(panel).toBeHidden();
  await expect(page.locator('[name=moment]')).toHaveValue('2026-11-02' + raw.slice(10));
  const clock = page.locator('.form-temporal').filter({has:page.locator('#field-clock-time')});
  await page.locator('#field-clock-time').fill('14:15:16');
  await clock.locator('summary').click();
  await clock.getByLabel('Fractional seconds (optional)', {exact:true}).fill('123456');
  await clock.getByLabel('UTC offset (optional)', {exact:true}).fill('-05:30');
  await clock.locator('summary').click();
  await expect(page.locator('[name=clock]')).toHaveValue('14:15:16.123456-05:30');
  await expect(clock.getByRole('button', {name:'Choose time', exact:true})).toHaveCount(0);
  await page.locator('[name=day]').fill('2026-11-01');
  const day = page.locator('.form-date-control').filter({has:page.locator('[name=day]')});
  await day.getByRole('button', {name:'Choose date', exact:true}).click();
  await panel.getByRole('button', {name:'2026-11-30', exact:true}).click();
  await expect(page.locator('[name=day]')).toHaveValue('2026-11-30');
  await page.locator('[name=name]').fill('picker-' + crypto.randomUUID());
  await page.getByRole('button', {name:'Create record', exact:true}).click();
  await expect(page.locator('[name=moment]')).toHaveValue('2026-11-02T12:34:56.120000');
  await expect(page.locator('[name=clock]')).toHaveValue('14:15:16.123456');
  expect(errors).toEqual([]);
});

test('incomplete form timestamps are validated and clearing a date clears the whole value', async ({page}) => {
  await page.goto('/admin/models/entries/new');
  const date = page.locator('#field-moment-date'), time = page.locator('#field-moment-time');
  await time.fill('12:30:00');
  await page.getByRole('button', {name:'Create record', exact:true}).click();
  await expect(date).toBeFocused();
  await expect(page.locator('[name=moment]')).toHaveValue('');
  await date.fill('2026-11-02');
  await expect(page.locator('[name=moment]')).toHaveValue(/^2026-11-02T12:30(?::00)?$/);
  await date.fill('');
  await expect(time).toHaveValue('');
  await expect(page.locator('[name=moment]')).toHaveValue('');
  const moment = page.locator('.form-temporal').filter({has:time});
  await moment.getByRole('button', {name:'Choose date', exact:true}).click();
  await page.locator('.form-date-panel:not([hidden])').getByRole('button', {name:'Today', exact:true}).click();
  await expect(time).toHaveValue(/^00:00(?::00)?$/);
  await expect(page.locator('[name=moment]')).not.toHaveValue('');
  await moment.locator('summary').click();
  const fraction = moment.getByLabel('Fractional seconds (optional)', {exact:true});
  await fraction.fill('abc');
  await moment.locator('summary').click();
  await page.getByRole('button', {name:'Create record', exact:true}).click();
  await expect(moment.locator('details')).toHaveAttribute('open');
  await expect(fraction).toBeFocused();
});

test('the compact form calendar fits a narrow date/time field', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await page.goto('/admin/models/entries/new');
  await page.locator('#field-moment-date').fill('2026-11-02');
  const moment = page.locator('.form-temporal').filter({has:page.locator('#field-moment-time')});
  await moment.getByRole('button', {name:'Choose date', exact:true}).click();
  const panel = page.locator('.form-date-panel:not([hidden])');
  const bounds = await panel.evaluate(el => {
    const rect = el.getBoundingClientRect(); return {left:rect.left, right:rect.right};
  });
  expect(bounds.left).toBeGreaterThanOrEqual(0);
  expect(bounds.right).toBeLessThanOrEqual(390);
  await panel.getByRole('button', {name:'2026-11-03', exact:true}).click();
  await expect(page.locator('#field-moment-date')).toHaveValue('2026-11-03');
});

test('a shared range panel edits both endpoints and rejects reversed bounds before applying', async ({page}) => {
  await page.goto('/admin/models/entries/');
  await page.locator('[data-filter-add]').click();
  const editor = page.locator('#filter-editor');
  await editor.locator('[data-field="f.moment"]').click();
  await editor.locator('#filter-operator').selectOption('between');
  const lower = '2026-11-01T12:00:00.123456', upper = '2026-11-02T18:00:00.123456';
  await editor.locator('#filter-value-0').fill(lower);
  await editor.locator('#filter-value-1').fill(upper);
  await editor.getByRole('button', {name:'Choose date range', exact:true}).click();
  const panel = editor.locator('.date-time-panel');
  await expect(panel.locator('.date-calendar-grid')).toHaveCount(2);
  await panel.getByLabel('From: Date', {exact:true}).fill('2026-11-03');
  await panel.getByRole('button', {name:'Apply', exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('lower bound');
  await expect(editor.locator('#filter-value-0')).toHaveValue(lower);
  await panel.getByLabel('From: Date', {exact:true}).fill('2026-11-01');
  await panel.getByRole('button', {name:'Apply', exact:true}).click();
  await editor.getByRole('button', {name:'Apply filter', exact:true}).click();
  await expect(editor).toBeHidden();
  expect(new URL(page.url()).searchParams.get('f.moment.gte')).toBe(lower);
  expect(new URL(page.url()).searchParams.get('f.moment.lte')).toBe(upper);
});

test('Escape closes the picker before its enclosing dialog, and clear discards invalid drafts', async ({page}) => {
  await page.goto('/admin/models/entries/');
  await page.locator('[data-filter-add]').click();
  const editor = page.locator('#filter-editor');
  await editor.locator('[data-field="f.clock"]').click();
  await editor.locator('#filter-value-0').fill('12:34:00.123456');
  await editor.getByRole('button', {name:'Choose time', exact:true}).click();
  const panel = editor.locator('.date-time-panel');
  await panel.getByLabel('Time', {exact:true}).press('Escape');
  await expect(panel).toBeHidden(); await expect(editor).toBeVisible();
  await editor.getByRole('button', {name:'Choose time', exact:true}).click();
  await panel.locator('summary').click();
  await panel.getByLabel('Fractional seconds (optional)', {exact:true}).fill('abc');
  await panel.getByRole('button', {name:'Clear', exact:true}).click();
  await expect(panel).toBeHidden();
  await expect(editor.locator('#filter-value-0')).toHaveValue('');
});
