import {test, expect} from '@playwright/test';

const graph = () => {
  const nodes = Array.from({length:2000}, (_, index) => ({
    id:'table_' + index, name:'table_' + index, label:'Table ' + index,
    fields:[{name:'id', type:'integer', pk:true}, {name:'parent_id', type:'integer', fk:true}, {name:'caption', type:'string'}],
  }));
  const edge = (index, source, target) => ({id:'edge_' + index, source, target, sourceFields:['id'], targetFields:['parent_id'], kind:'o2m', label:'Parent'});
  const edges = nodes.slice(1).map((node, index) => edge(index, nodes[Math.floor(index / 3)].id, node.id));
  const pairs = new Set(edges.map(item => item.source + '|' + item.target));
  for (let index = 0; edges.length < 2421; index++) {
    const source = nodes[(index * 17) % 2000].id, target = nodes[(index * 31 + 1) % 2000].id;
    const pair = source + '|' + target;
    if (pairs.has(pair)) continue;
    pairs.add(pair);
    edges.push(edge(edges.length, source, target));
  }
  return {nodes, edges, junctions:[]};
};

test('all two thousand tables render and remain movable when initial selection is unrestricted', async ({page}) => {
  // Budget the complete interaction sequence separately from the 5s initial-render check.
  test.setTimeout(60000);
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await page.goto('/admin/schema');
  const renderMs = await page.evaluate(graph => {
    const previous = document.querySelector('[data-schema-workspace]');
    previous.schemaCleanup();
    const root = previous.cloneNode(true);
    previous.replaceWith(root);
    root.removeAttribute('data-schema-ready');
    root.dataset.graph = JSON.stringify(graph);
    root.dataset.initialSelection = 'all';
    const start = performance.now();
    window.QuiteAdmin.initSchemas();
    return performance.now() - start;
  }, graph());
  const root = page.locator('[data-schema-workspace]');
  await expect(root.locator('[data-node]')).toHaveCount(2000);
  await expect(root.locator('[data-edge]')).toHaveCount(2421);
  await expect(root.locator('[data-schema-count]')).toHaveText('2000/2000');
  expect(renderMs).toBeLessThan(5000);
  const initialViewBox = await root.locator('[data-schema-canvas]').getAttribute('viewBox');
  const initialPositions = await root.locator('[data-node]').evaluateAll(nodes => nodes.map(node => [node.dataset.node, node.getAttribute('transform')]));
  const fill = await root.locator('[data-schema-canvas]').evaluate(canvas => {
    const nodes = [...canvas.querySelectorAll('[data-node]')].map(node => {
      const position = node.transform.baseVal.consolidate().matrix;
      const surface = node.querySelector('.node-surface');
      return {x:position.e, y:position.f, width:surface.width.baseVal.value, height:surface.height.baseVal.value};
    });
    const width = Math.max(...nodes.map(node => node.x + node.width)) - Math.min(...nodes.map(node => node.x));
    const height = Math.max(...nodes.map(node => node.y + node.height)) - Math.min(...nodes.map(node => node.y));
    const box = canvas.getBoundingClientRect(), aspect = box.width / box.height;
    return nodes.reduce((sum, node) => sum + node.width * node.height, 0) / (Math.max(width / aspect, height) ** 2 * aspect);
  });
  expect(fill, 'tables should occupy the workspace after fitting the whole graph').toBeGreaterThan(0.2);

  await root.locator('[data-schema-search]').fill('Table 0');
  await root.locator('.schema-table-name').filter({hasText:'Table 0'}).first().click();
  const card = root.locator('[data-node="table_0"]');
  const initial = await card.evaluate(node => {
    node.dataset.scaleIdentity = 'preserved';
    return node.getAttribute('transform');
  });
  await card.focus();
  await page.keyboard.press('ArrowRight');
  await expect(card).toHaveAttribute('data-scale-identity', 'preserved');
  expect(await card.getAttribute('transform')).not.toBe(initial);
  await expect(card).toBeFocused();

  const box = await card.boundingBox();
  const before = await card.getAttribute('transform');
  await page.mouse.move(box.x + box.width / 2, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 20, box.y + 20, {steps:3});
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + 20, {steps:3});
  await page.mouse.up();
  await expect(card).toHaveAttribute('data-scale-identity', 'preserved');
  const after = await card.getAttribute('transform');
  const x = transform => Number(transform.match(/translate\(([^,]+)/)[1]);
  expect(x(after) - x(before)).toBeCloseTo(40, 0);
  await expect(root.locator('[data-node]')).toHaveCount(2000);

  const beforeZoom = await root.locator('[data-schema-canvas]').getAttribute('viewBox');
  await root.locator('[data-schema-zoom="in"]').click();
  expect(await root.locator('[data-schema-canvas]').getAttribute('viewBox')).not.toBe(beforeZoom);
  await expect(root.locator('[data-node="table_0"]')).toHaveAttribute('data-scale-identity', 'preserved');

  // Auto layout discards manual positions and zoom, but keeps every table/edge.
  await root.locator('[data-schema-layout]').click();
  await expect(root.locator('[data-schema-canvas]')).toHaveAttribute('viewBox', initialViewBox);
  expect(await root.locator('[data-node]').evaluateAll(nodes => nodes.map(node => [node.dataset.node, node.getAttribute('transform')]))).toEqual(initialPositions);
  await expect(root.locator('[data-node]')).toHaveCount(2000);
  await expect(root.locator('[data-edge]')).toHaveCount(2421);
  await expect(root.locator('[data-schema-count]')).toHaveText('2000/2000');
});
