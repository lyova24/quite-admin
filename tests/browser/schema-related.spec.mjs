import {test, expect} from '@playwright/test';

const table = id => ({
  id, name:id, label:'Table ' + id,
  fields:[{name:'id', type:'integer', pk:true}, {name:'parent_id', type:'integer', fk:true}, {name:'caption', type:'string'}],
});
const relation = (id, source, target) => ({id, source, target, sourceFields:['id'], targetFields:['parent_id'], kind:'o2m'});
const related = (root, id) => root.locator(`[data-schema-related="${id}"]`);
const card = (root, id) => root.locator(`[data-node="${id}"]`);

function graph() {
  return {
    nodes:Array.from({length:10}, (_, index) => table('table_' + index)), junctions:[],
    edges:[
      relation('outgoing_one', 'table_0', 'table_1'), relation('incoming_one', 'table_2', 'table_0'),
      relation('outgoing_two', 'table_0', 'table_3'), relation('incoming_two', 'table_4', 'table_0'),
      relation('self', 'table_0', 'table_0'), relation('second_degree', 'table_1', 'table_5'),
      relation('unrelated_one', 'table_6', 'table_7'), relation('unrelated_two', 'table_8', 'table_9'),
    ],
  };
}

async function openSchema(page, data = graph()) {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await page.route('**/admin/schema', async route => {
    const response = await route.fetch();
    const body = (await response.text())
      .replace(/data-graph='[^']*'/, () => `data-graph='${JSON.stringify(data)}'`)
      .replace(/data-initial-selection="[^"]*"/, 'data-initial-selection="all"');
    await route.fulfill({response, body});
  });
  await page.goto('/admin/schema');
  const root = page.locator('[data-schema-workspace]');
  await expect(root).toHaveAttribute('data-schema-ready', 'true');
  await expect(root.locator('[data-node]')).toHaveCount(data.nodes.length);
  return root;
}

async function expectSelection(root, ids, count = 10) {
  const expected = [...ids].sort();
  expect(await root.locator('[data-node]').evaluateAll(nodes => nodes.map(node => node.dataset.node).sort())).toEqual(expected);
  expect(await root.locator('[data-table]:checked').evaluateAll(nodes => nodes.map(node => node.dataset.table).sort())).toEqual(expected);
  await expect(root.locator('[data-schema-count]')).toHaveText(`${ids.length}/${count}`);
}

async function viewState(root) {
  return {
    viewBox:await root.locator('[data-schema-canvas]').getAttribute('viewBox'),
    positions:await root.locator('[data-node]').evaluateAll(nodes => nodes.map(node => [node.dataset.node, node.getAttribute('transform')]).sort((a, b) => a[0].localeCompare(b[0]))),
  };
}

test('hover control isolates direct neighbours and restores the prior tables, positions and view', async ({page}) => {
  const root = await openSchema(page);
  const all = graph().nodes.map(node => node.id), subset = all.slice(0, 5);
  await card(root, 'table_8').focus();
  await page.keyboard.press('ArrowRight');
  await root.locator('[data-schema-zoom="in"]').click();
  const before = await viewState(root);
  await card(root, 'table_0').hover();
  const toggle = related(root, 'table_0');
  await expect(toggle).toBeVisible();
  await expect.poll(() => toggle.evaluate(node => getComputedStyle(node.closest('.schema-related-control')).opacity)).toBe('1');
  await expect(toggle).toHaveAccessibleName('Show only related tables: Table table_0');
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(card(root, 'table_0')).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expectSelection(root, subset);
  await expect(root.locator('[data-edge]')).toHaveCount(5);
  await expect(related(root, 'table_0')).toHaveAttribute('aria-pressed', 'true');
  await expect(related(root, 'table_0')).toHaveAccessibleName('Restore previous tables: Table table_0');
  await expect(card(root, 'table_0')).toHaveAttribute('aria-expanded', 'false');
  await expect(root.locator('[data-schema-canvas]')).not.toHaveClass(/is-dragging/);
  await related(root, 'table_0').click();
  await expectSelection(root, all);
  expect(await viewState(root)).toEqual(before);
  await expect(card(root, 'table_0')).toHaveAttribute('aria-expanded', 'false');
});

test('keyboard controls can change the focus table without replacing the original selection snapshot', async ({page}) => {
  const root = await openSchema(page);
  const all = graph().nodes.map(node => node.id);
  await related(root, 'table_0').focus();
  await expect(related(root, 'table_0')).toBeFocused();
  await related(root, 'table_0').press('Enter');
  await expectSelection(root, all.slice(0, 5));
  await expect(related(root, 'table_0')).toBeFocused();
  await related(root, 'table_1').focus();
  await related(root, 'table_1').press('Space');
  // Table 5 was selected before focusing Table 0, so retargeting can show it
  // again without treating tables hidden by temporary focus as user exclusions.
  await expectSelection(root, ['table_0', 'table_1', 'table_5']);
  await expect(related(root, 'table_1')).toBeFocused();
  await expect(related(root, 'table_1')).toHaveAttribute('aria-pressed', 'true');
  await expect(related(root, 'table_0')).toHaveAttribute('aria-pressed', 'false');
  await related(root, 'table_1').press('Space');
  await expectSelection(root, all);
  await expect(related(root, 'table_1')).toBeFocused();
});

test('explicit checkbox changes reset temporary focus and become the next restoration selection', async ({page}) => {
  const root = await openSchema(page);
  await card(root, 'table_0').hover();
  await related(root, 'table_0').click();
  await root.locator('[data-table="table_4"]').uncheck();
  await expectSelection(root, ['table_0', 'table_1', 'table_2', 'table_3']);
  await expect(root.locator('[data-schema-related][aria-pressed="true"]')).toHaveCount(0);
  await root.locator('[data-table="table_8"]').check();
  const edited = ['table_0', 'table_1', 'table_2', 'table_3', 'table_8'];
  await expectSelection(root, edited);
  await card(root, 'table_0').hover();
  await related(root, 'table_0').click();
  await expectSelection(root, edited.slice(0, 4));
  await related(root, 'table_0').click();
  await expectSelection(root, edited);
});

test('group, Show all and Hide all choices end temporary focus before applying the requested selection', async ({page}) => {
  const data = graph();
  data.nodes.forEach((node, index) => { node.group = index < 5 ? 'Connected' : 'Other'; });
  const root = await openSchema(page, data), all = data.nodes.map(node => node.id);
  const isolate = async () => {
    await card(root, 'table_0').hover();
    await related(root, 'table_0').click();
    await expectSelection(root, all.slice(0, 5));
  };
  await isolate();
  await root.locator('[data-schema-group-toggle="Other"]').check();
  await expectSelection(root, all);
  await expect(root.locator('[data-schema-related][aria-pressed="true"]')).toHaveCount(0);
  await isolate();
  await root.locator('[data-schema-show-all]').click();
  await expectSelection(root, all);
  await expect(root.locator('[data-schema-related][aria-pressed="true"]')).toHaveCount(0);
  await isolate();
  await root.locator('[data-schema-hide-all]').click();
  await expectSelection(root, []);
  await root.locator('[data-schema-show-all]').click();
  await isolate();
  await related(root, 'table_0').click();
  await expectSelection(root, all);
});

test('related focus never adds hidden tables or neighbours absent from the authorized catalog', async ({page}) => {
  const data = graph();
  data.nodes.push(table('hidden'));
  data.edges.push(relation('hidden_edge', 'table_0', 'hidden'), relation('unavailable_edge', 'table_0', 'unavailable'));
  const root = await openSchema(page, data);
  await root.locator('[data-table="hidden"]').uncheck();
  await card(root, 'table_0').hover();
  await related(root, 'table_0').click();
  await expectSelection(root, graph().nodes.slice(0, 5).map(node => node.id), 11);
  await expect(root.locator('[data-table="hidden"]')).not.toBeChecked();
  await expect(root.locator('[data-node="hidden"], [data-node="unavailable"], [data-table="unavailable"]')).toHaveCount(0);
  await related(root, 'table_0').click();
  await expectSelection(root, graph().nodes.map(node => node.id), 11);
  await expect(root.locator('[data-table="hidden"]')).not.toBeChecked();
});

test('related focus uses projected many-to-many junction edges and restores the expanded junction', async ({page}) => {
  const junction = {...table('junction'), junction:true, fields:[
    {name:'id', type:'integer', pk:true}, {name:'left_id', type:'integer', fk:true}, {name:'right_id', type:'integer', fk:true},
  ]};
  const root = await openSchema(page, {
    nodes:[table('left'), table('right'), table('unrelated')], junctions:[junction],
    edges:[{...relation('many', 'left', 'right'), kind:'m2m', targetFields:['id'], junction:'junction', junctionSourceFields:['left_id'], junctionTargetFields:['right_id']}],
  });
  await card(root, 'left').hover();
  await related(root, 'left').click();
  await expectSelection(root, ['left', 'right'], 3);
  await related(root, 'left').click();
  await expectSelection(root, ['left', 'right', 'unrelated'], 3);
  await root.locator('[data-edge="many"] .edge-label-bg').click();
  await expectSelection(root, ['left', 'right', 'unrelated', 'junction'], 4);
  await expect(root.locator('[data-edge]')).toHaveCount(2);
  await card(root, 'left').hover();
  await related(root, 'left').click();
  await expectSelection(root, ['left', 'junction'], 4);
  await expect(root.locator('[data-edge]')).toHaveCount(1);
  await related(root, 'left').click();
  await expectSelection(root, ['left', 'right', 'unrelated', 'junction'], 4);
  await expect(root.locator('[data-edge]')).toHaveCount(2);
});

test.describe('touch related-table control', () => {
  test.use({hasTouch:true, viewport:{width:390, height:844}});

  test('the control is available without hovering', async ({page}) => {
    const root = await openSchema(page);
    const toggle = related(root, 'table_0');
    await expect.poll(() => toggle.evaluate(node => getComputedStyle(node.closest('.schema-related-control')).opacity)).toBe('1');
    await toggle.tap();
    await expectSelection(root, graph().nodes.slice(0, 5).map(node => node.id));
    await expect(card(root, 'table_0')).toHaveAttribute('aria-expanded', 'false');
    await related(root, 'table_0').tap();
    await expectSelection(root, graph().nodes.map(node => node.id));
  });
});
