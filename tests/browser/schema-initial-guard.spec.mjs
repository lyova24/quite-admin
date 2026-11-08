import {test, expect} from '@playwright/test';

async function login(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
}

async function useSchema(page, selection, count) {
  const graph = {
    nodes:Array.from({length:count}, (_, index) => ({
      id:`table_${index}`, name:`table_${index}`, label:`Table ${index}`,
      fields:[{name:'id', type:'integer', pk:true}], url:`/admin/models/table_${index}/`,
    })),
    edges:[], junctions:[],
  };
  await page.route('**/admin/schema', async route => {
    const response = await route.fetch();
    const body = (await response.text())
      .replace(/data-graph='[^']*'/, () => `data-graph='${JSON.stringify(graph)}'`)
      .replace(/data-initial-selection="[^"]*"/, `data-initial-selection="${selection}"`);
    await route.fulfill({response, body});
  });
  await page.goto('/admin/schema');
  await expect(page.locator('[data-schema-workspace]')).toHaveAttribute('data-schema-ready', 'true');
}

test('large schemas start empty and allow search, individual selection and Show all', async ({page}) => {
  await login(page);
  await useSchema(page, 'none', 101);
  const workspace = page.locator('[data-schema-workspace]');
  await expect(workspace.locator('[data-node]')).toHaveCount(0);
  await expect(workspace.locator('.schema-empty')).toHaveText('Select tables to display');
  await expect(workspace.locator('[data-schema-count]')).toHaveText('0/101');
  await expect(workspace.locator('[data-schema-choices] input')).toHaveCount(101);
  await expect(workspace.locator('[data-schema-choices] input:checked')).toHaveCount(0);
  await workspace.locator('[data-schema-search]').fill('table_42');
  await expect(workspace.locator('[data-schema-choices] input')).toHaveCount(1);
  await workspace.locator('[data-schema-choices] input').check();
  await expect(workspace.locator('[data-node="table_42"]')).toHaveCount(1);
  await expect(workspace.locator('[data-schema-count]')).toHaveText('1/101');
  await workspace.locator('[data-schema-search]').fill('');
  await workspace.locator('[data-schema-show-all]').click();
  await expect(workspace.locator('[data-node]')).toHaveCount(101);
  await expect(workspace.locator('[data-schema-count]')).toHaveText('101/101');
  await workspace.locator('[data-schema-hide-all]').click();
  await expect(workspace.locator('[data-node]')).toHaveCount(0);
  await expect(workspace.locator('[data-schema-choices] input:checked')).toHaveCount(0);
});

test('manual selection keeps the table sidebar open on a narrow screen', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await login(page);
  await useSchema(page, 'none', 101);
  await expect(page.locator('[data-schema-sidebar-toggle]')).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.schema-sidebar')).toBeVisible();
  await page.locator('[data-schema-search]').fill('table_5');
  await page.locator('[data-table="table_5"]').check();
  await expect(page.locator('[data-node="table_5"]')).toHaveCount(1);
});

test('the ordinary initial selection still shows every table and collapses the narrow sidebar', async ({page}) => {
  await page.setViewportSize({width:390, height:844});
  await login(page);
  await useSchema(page, 'all', 8);
  await expect(page.locator('[data-node]')).toHaveCount(8);
  await expect(page.locator('[data-schema-count]')).toHaveText('8/8');
  await expect(page.locator('[data-schema-sidebar-toggle]')).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('.schema-sidebar')).toBeHidden();
});
