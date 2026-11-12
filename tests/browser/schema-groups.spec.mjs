import {test, expect} from '@playwright/test';

async function openGroupedSchema(page) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  const table = (id, label, group = null) => ({id, name:id, label, group, fields:[{name:'id', type:'integer', pk:true}]});
  const graph = {
    nodes:[table('alpha', 'Alpha', 'Sales'), table('beta', 'Beta', 'Sales'), table('items', 'Items', 'Catalog'), table('notes', 'Notes')],
    edges:[], junctions:[],
  };
  await page.route('**/admin/schema', async route => {
    const response = await route.fetch();
    const body = (await response.text())
      .replace(/data-graph='[^']*'/, () => `data-graph='${JSON.stringify(graph)}'`)
      .replace(/data-initial-selection="[^"]*"/, 'data-initial-selection="none"');
    await route.fulfill({response, body});
  });
  await page.goto('/admin/schema');
  await expect(page.locator('[data-schema-workspace]')).toHaveAttribute('data-schema-ready', 'true');
  return page.locator('[data-schema-workspace]');
}

test('schema group checkboxes select all members and synchronize checked and mixed states', async ({page}) => {
  const root = await openGroupedSchema(page);
  const group = root.getByRole('checkbox', {name:'Show group: Sales', exact:true});
  await expect(group).not.toBeChecked();
  await group.focus();
  await group.press('Space');
  await expect(group).toBeChecked();
  await expect(root.locator('[data-node]')).toHaveCount(2);
  await expect(root.locator('[data-schema-group="Sales"] small').first()).toHaveText('2/2');
  await root.locator('[data-table="alpha"]').uncheck();
  await expect(group).toHaveAttribute('aria-checked', 'mixed');
  expect(await group.evaluate(input => input.indeterminate)).toBe(true);
  await expect(root.locator('[data-schema-group="Sales"] small').first()).toHaveText('1/2');
  await root.locator('.schema-table-name').filter({hasText:'Alpha'}).click();
  await expect(group).toHaveAttribute('aria-checked', 'true');
  await root.locator('[data-schema-hide-all]').click();
  await expect(group).toHaveAttribute('aria-checked', 'false');
  await root.locator('[data-schema-show-all]').click();
  await expect(group).toHaveAttribute('aria-checked', 'true');
  await expect(root.locator('[data-node]')).toHaveCount(4);
  await group.uncheck();
  await expect(root.locator('[data-node]')).toHaveCount(2);
  await expect(root.locator('[data-node="items"]')).toHaveCount(1);
  await expect(root.locator('[data-node="notes"]')).toHaveCount(1);
});

test('schema group search reveals members and a filtered group control still selects its entire group', async ({page}) => {
  const root = await openGroupedSchema(page);
  const search = root.locator('[data-schema-search]');
  await search.fill('Sales');
  await expect(root.locator('[data-table]')).toHaveCount(2);
  await expect(root.locator('[data-node]')).toHaveCount(0);
  await search.fill('alpha');
  await expect(root.locator('[data-table]')).toHaveCount(1);
  await expect(root.locator('.schema-group-search-help')).toHaveText('Group checkboxes select every table in the group, including tables hidden by search.');
  await root.getByRole('checkbox', {name:'Show group: Sales', exact:true}).check();
  await expect(root.locator('[data-node]')).toHaveCount(2);
  await expect(root.locator('[data-schema-count]')).toHaveText('2/4');
  await search.fill('beta');
  await root.locator('[data-table="beta"]').uncheck();
  await expect(root.getByRole('checkbox', {name:'Show group: Sales', exact:true})).toHaveAttribute('aria-checked', 'mixed');
  await search.fill('not found');
  await expect(root.locator('[data-schema-choices]')).toHaveText('No matching tables.');
  await expect(root.locator('[data-node]')).toHaveCount(1);
  await search.fill('');
  await expect(root.locator('[data-table="alpha"]')).toBeChecked();
  await expect(root.locator('[data-table="beta"]')).not.toBeChecked();
});

test('browser demo uses the same schema groups in both languages', async ({page}) => {
  await page.goto('http://127.0.0.1:8128/#/schema');
  await page.getByLabel('Username', {exact:true}).fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('admin');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  const root = page.locator('[data-schema-workspace]');
  const seed = await (await page.request.get('http://127.0.0.1:8128/seed.json')).json();
  const groups = new Set(Object.values(seed.collections).map(collection => collection.group));
  await expect(root.locator('[data-schema-group]')).toHaveCount(groups.size);
  await root.locator('[data-schema-hide-all]').click();
  await root.getByRole('checkbox', {name:'Show group: Sales', exact:true}).check();
  await expect(root.locator('[data-node]')).toHaveCount(3);
  await page.goto('http://127.0.0.1:8128/?lang=ru#/schema');
  await root.locator('[data-schema-hide-all]').click();
  await root.getByRole('checkbox', {name:'Показать группу: Sales', exact:true}).check();
  await expect(root.locator('[data-node]')).toHaveCount(3);
  await expect(root.getByRole('checkbox', {name:'Показать группу: Sales', exact:true})).toBeChecked();
});
