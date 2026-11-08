import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/');
  await page.getByLabel('Username', {exact:true}).fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/$/);
}

async function fitsViewport(page, locator) {
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds.x).toBeGreaterThanOrEqual(-1);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test.beforeEach(async ({page}) => { await login(page); });

test('laptop dimensions are preserved and the whole interface grows smoothly on wider screens', async ({page}) => {
  await page.goto('/admin/models/entries/');
  let previous = null;
  for (const [width, root] of [[1280,16], [1512,16], [1600,16], [1920,18], [2451,21.31875], [2560,22], [2880,24], [3840,24]]) {
    await page.setViewportSize({width, height:1000});
    const sizes = await page.evaluate(() => {
      const style = selector => getComputedStyle(document.querySelector(selector));
      const box = selector => document.querySelector(selector).getBoundingClientRect();
      return {
        root:parseFloat(style('html').fontSize), text:parseFloat(style('td').fontSize),
        sidebar:box('.sidebar').width, control:box('.list-create').height,
        icon:box('[data-filter-add] svg').width, content:parseFloat(style('.content').maxWidth),
        row:box('tbody tr').height, border:parseFloat(style('.list-table-scroll').borderTopWidth),
      };
    });
    expect(sizes.root).toBeCloseTo(root, 1);
    expect(sizes.text).toBeCloseTo(root * .75, 1);
    expect(Math.abs(sizes.sidebar - root * 11.5)).toBeLessThan(.25);
    expect(sizes.control).toBeCloseTo(root * 1.9375, 1);
    expect(sizes.icon).toBeCloseTo(root * 1.125, 1);
    expect(Math.abs(sizes.content - root * 100)).toBeLessThan(1);
    expect(sizes.border).toBe(1);
    if (previous) expect(sizes.row).toBeGreaterThanOrEqual(previous.row);
    previous = sizes;
    await fitsViewport(page, page.locator('.list-table-scroll'));
  }
});

test('the pencil stays to the right of short, truncated and empty cell values at every scale', async ({page}) => {
  await page.goto('/admin/models/entries/');
  const cell = page.locator('td[data-list-field=day]').first();
  for (const width of [390, 1512, 2560]) {
    await page.setViewportSize({width, height:1000});
    for (const [text, className] of [['2026-11-01', 'cell-value'], ['Long value '.repeat(50), 'cell-value'], ['—', 'null-value']]) {
      const geometry = await cell.evaluate((node, [text, className]) => {
        const value = node.querySelector('[data-cell-value]');
        value.textContent = text; value.className = className;
        const textBox = value.getBoundingClientRect(), pencil = node.querySelector('.cell-edit').getBoundingClientRect();
        return {
          valueRight:textBox.right, pencilLeft:pencil.left,
          valueCenter:textBox.y + textBox.height / 2, pencilCenter:pencil.y + pencil.height / 2,
          truncated:value.scrollWidth > value.clientWidth,
        };
      }, [text, className]);
      expect(geometry.pencilLeft).toBeGreaterThanOrEqual(geometry.valueRight);
      expect(Math.abs(geometry.pencilCenter - geometry.valueCenter)).toBeLessThan(1);
      if (text.length > 90) expect(geometry.truncated).toBe(true);
    }
  }
});

for (const width of [390, 1512, 2560]) {
  test(`filters, calendars and long tables remain usable at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height:1000});
    await page.goto('/admin/models/entries/');
    await fitsViewport(page, page.locator('.list-table-scroll'));
    if (width === 390) {
      expect(await page.locator('.list-table-scroll').evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
    }
    await page.locator('[data-filter-add]').click();
    const dialog = page.locator('#filter-editor');
    await dialog.locator('[data-field="f.moment"]').click();
    await dialog.locator('#filter-value-0').fill('2026-11-01');
    await dialog.getByRole('button', {name:'Choose date', exact:true}).click();
    await fitsViewport(page, dialog);
    await fitsViewport(page, dialog.locator('.date-time-panel'));
    await dialog.getByRole('button', {name:'2026-11-30', exact:true}).click();
    await dialog.locator('.date-time-panel').getByRole('button', {name:'Apply', exact:true}).click();
    await expect(dialog.locator('#filter-value-0')).toHaveValue('2026-11-30');
    await dialog.getByRole('button', {name:'Apply filter', exact:true}).click();
    await expect(dialog).toBeHidden();
    await expect(page.locator('.active-filters')).toContainText('2026-11-30');

    await page.goto('/admin/models/entries/new');
    const date = page.locator('.form-date-control').filter({has:page.locator('[name=day]')});
    await date.getByRole('button', {name:'Choose date', exact:true}).click();
    const panel = page.locator('.form-date-panel:not([hidden])');
    await fitsViewport(page, panel);
    await panel.getByRole('button', {name:'2026-11-30', exact:true}).click();
    await expect(page.locator('[name=day]')).toHaveValue('2026-11-30');
    await fitsViewport(page, page.locator('.form-footer'));
  });
}

test('an application can retain compact sizing or enlarge the rem base without clipping the page', async ({page}) => {
  let scale = '100%';
  await page.route('**/assets/admin.css', async route => {
    const response = await route.fetch();
    await route.fulfill({response, body:(await response.text()) + `\n:root { --ui-font-size: ${scale}; }`});
  });
  await page.setViewportSize({width:2560, height:1440});
  await page.goto('/admin/models/entries/');
  await expect(page.locator('td').first()).toHaveCSS('font-size', '12px');
  scale = '200%';
  await page.reload();
  await expect(page.locator('td').first()).toHaveCSS('font-size', '24px');
  await expect(page.locator('.sidebar')).toHaveCSS('width', '368px');
  await fitsViewport(page, page.locator('.list-table-scroll'));
  await page.setViewportSize({width:390, height:844});
  await fitsViewport(page, page.locator('.list-table-scroll'));
  await page.locator('[data-bulk-panel] > summary').click();
  await fitsViewport(page, page.locator('[data-bulk-form]'));
  await page.keyboard.press('Escape');
  await page.goto('/admin/models/entries/new');
  await fitsViewport(page, page.locator('.record-form'));
  const picker = page.locator('[data-relation-picker]').filter({has:page.locator('[name="__relation__to_customers_by_customer_id"]')});
  const trigger = picker.locator('.picker-trigger');
  await trigger.evaluate(node => { node.firstChild.textContent = 'Choose records with a longer label'; });
  await fitsViewport(page, trigger);
  await trigger.click();
  await expect(picker.getByRole('searchbox')).toBeVisible();
});
