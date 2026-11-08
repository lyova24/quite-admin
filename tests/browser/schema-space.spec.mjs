import {test, expect} from '@playwright/test';

async function openLargeSchema(page, {width, height, scale = '100%'}) {
  await page.setViewportSize({width, height});
  await page.route('**/assets/admin.css', async route => {
    const response = await route.fetch();
    await route.fulfill({response, body:(await response.text()) + `\n:root { --ui-font-size: ${scale}; }`});
  });
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  const graph = {
    nodes:Array.from({length:1993}, (_, index) => ({
      id:`table_${index}`, name:`table_${index}`, label:`Table ${index}`,
      group:`Group ${index % 50}`, fields:[{name:'id', type:'integer', pk:true}],
    })),
    edges:[], junctions:[],
  };
  await page.route('**/admin/schema', async route => {
    const response = await route.fetch();
    let body = (await response.text())
      .replace(/data-graph='[^']*'/, () => `data-graph='${JSON.stringify(graph)}'`)
      .replace(/data-initial-selection="[^"]*"/, 'data-initial-selection="none"');
    // The small HTTP fixture has two tables; include the large-schema server notice
    // as well so its wrapping contributes to the measured viewport layout.
    if (!body.includes('data-schema-initial-notice')) body = body.replace(
      '<div class="schema-body">',
      '<p class="schema-help" role="status" data-schema-initial-notice>There are too many tables to display automatically. Select tables in the sidebar, or choose Show all.</p><div class="schema-body">',
    );
    await route.fulfill({response, body});
  });
  await page.goto('/admin/schema');
  const root = page.locator('[data-schema-workspace]');
  await expect(root).toHaveAttribute('data-schema-ready', 'true');
  await expect(root).toHaveAttribute('data-initial-selection', 'none');
  await expect(root.locator('[data-schema-count]')).toHaveText('0/1993');
  await expect(root.locator('[data-node]')).toHaveCount(0);
  await expect(root.locator('[data-schema-initial-notice]')).toBeVisible();
  return root;
}

async function geometry(page) {
  return page.evaluate(() => {
    const box = selector => {
      const rect = document.querySelector(selector).getBoundingClientRect();
      return {top:rect.top, bottom:rect.bottom, left:rect.left, right:rect.right, height:rect.height, width:rect.width};
    };
    return {
      viewport:{width:innerWidth, height:innerHeight}, documentWidth:document.documentElement.scrollWidth,
      header:box('.topbar'), workspace:box('[data-schema-workspace]'),
      sidebar:box('.schema-sidebar'), canvas:box('[data-schema-canvas]'), legend:box('.schema-legend'),
      inset:parseFloat(getComputedStyle(document.querySelector('.content')).paddingBottom),
    };
  });
}

for (const viewport of [
  {width:1440, height:1200}, {width:1440, height:900}, {width:1024, height:600},
  {width:390, height:844}, {width:1920, height:1200, scale:'200%'},
]) {
  test(`schema uses the available viewport at ${viewport.width}×${viewport.height} (${viewport.scale || '100%'})`, async ({page}) => {
    const root = await openLargeSchema(page, viewport);
    const bounds = await geometry(page);
    expect(bounds.workspace.top).toBeGreaterThanOrEqual(bounds.header.bottom);
    expect(Math.abs(bounds.workspace.bottom - (viewport.height - bounds.inset))).toBeLessThanOrEqual(2);
    expect(bounds.documentWidth).toBeLessThanOrEqual(viewport.width);
    expect(bounds.canvas.height).toBeGreaterThan(200);
    expect(bounds.sidebar.bottom).toBeLessThanOrEqual(bounds.legend.top + 1);
    expect(bounds.canvas.bottom).toBeLessThanOrEqual(bounds.legend.top + 1);
    expect(await root.locator('.schema-sidebar').evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
    await root.locator('[data-schema-search]').fill('table_42');
    await root.locator('[data-table="table_42"]').check();
    await expect(root.locator('[data-node]')).toHaveCount(1);
    await expect(root.locator('[data-schema-count]')).toHaveText('1/1993');
  });
}

test('schema canvas grows with the window and keeps its sidebar toggle usable', async ({page}) => {
  const root = await openLargeSchema(page, {width:1440, height:900});
  const before = await geometry(page);
  await page.setViewportSize({width:1440, height:1200});
  await expect.poll(async () => (await geometry(page)).canvas.height).toBeGreaterThan(before.canvas.height + 290);
  await root.locator('[data-schema-sidebar-toggle]').click();
  await expect(root.locator('.schema-sidebar')).toBeHidden();
  await expect.poll(async () => (await root.locator('[data-schema-canvas]').boundingBox()).width).toBeGreaterThan(before.canvas.width + 250);
  await root.locator('[data-schema-sidebar-toggle]').click();
  await expect(root.locator('.schema-sidebar')).toBeVisible();
});

test('enlarged mobile controls scroll without clipping the diagram or legend', async ({page}) => {
  const root = await openLargeSchema(page, {width:390, height:844, scale:'200%'});
  const bounds = await geometry(page);
  expect(bounds.documentWidth).toBeLessThanOrEqual(390);
  expect(bounds.canvas.height).toBeGreaterThan(250);
  expect(bounds.workspace.bottom).toBeGreaterThanOrEqual(bounds.legend.bottom);
  expect(bounds.canvas.bottom).toBeLessThanOrEqual(bounds.legend.top + 1);
  await root.locator('.schema-legend').scrollIntoViewIfNeeded();
  await expect(root.locator('.schema-legend')).toBeInViewport();
  await root.locator('[data-schema-expand-view]').click();
  await expect(root).toHaveAttribute('aria-modal', 'true');
  await expect(root.locator('[data-schema-expand-view]')).toBeFocused();
  expect((await geometry(page)).canvas.height).toBeGreaterThan(250);
  await page.keyboard.press('Escape');
  await expect(root).not.toHaveClass(/is-expanded/);
  await expect(root.locator('[data-schema-expand-view]')).toBeFocused();
});
