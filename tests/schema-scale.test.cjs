const {test} = require('node:test');
const assert = require('node:assert/strict');
const {performance} = require('node:perf_hooks');
const {layoutSchema, routeEdge, createRoutingContext} = require(process.env.QUITE_ADMIN_SCHEMA_SCRIPT || '../src/quite_admin/static/schema.js');

const table = (id) => ({id, name:id, label:id, fields:[
  {name:'id', type:'integer', pk:true}, {name:'parent_id', type:'integer', fk:true},
  {name:'caption', type:'string'},
]});
const relation = (id, source, target) => ({id, source, target, sourceFields:['id'], targetFields:['parent_id'], kind:'o2m'});
const intersects = (a, b, r) => a.x === b.x
  ? a.x > r.x && a.x < r.x + r.width && Math.max(a.y, b.y) > r.y && Math.min(a.y, b.y) < r.y + r.height
  : a.y > r.y && a.y < r.y + r.height && Math.max(a.x, b.x) > r.x && Math.min(a.x, b.x) < r.x + r.width;

// Measure occupied table area after fitting the whole diagram into its viewport.
// Bounding-box density alone misses a tall star or a single-row chain: either can
// be dense internally while using almost none of the screen at "Fit schema".
function assertCompactLayout(nodes, edges, expanded = new Set(), aspect = 1.8, minimumFill = 0.2) {
  const layout = layoutSchema(nodes, edges, expanded, aspect);
  assert.deepEqual(layout.map(node => node.id).sort(), nodes.map(node => node.id).sort());
  assert.equal(new Set(layout.map(node => node.id)).size, nodes.length);
  for (const node of layout) {
    assert.ok([node.x, node.y, node.width, node.height].every(Number.isFinite), 'every table has finite bounds');
    assert.ok(node.width > 0 && node.height > 0, 'every table has a positive size');
    assert.equal(node.shownFields.length, expanded.has(node.id) ? node.fields.length : node.fields.filter(field => field.pk || field.fk || field.linked).length);
  }
  // Sweep only horizontally overlapping rectangles, keeping the 6k-chain check
  // practical without using the layout's own spatial index to validate itself.
  const active = [];
  for (const node of [...layout].sort((a, b) => a.x - b.x)) {
    for (let index = active.length - 1; index >= 0; index--) {
      const other = active[index];
      if (other.x + other.width <= node.x) active.splice(index, 1);
      else assert.ok(node.y + node.height <= other.y || other.y + other.height <= node.y, `${node.id} overlaps ${other.id}`);
    }
    active.push(node);
  }
  const width = Math.max(...layout.map(node => node.x + node.width)) - Math.min(...layout.map(node => node.x));
  const height = Math.max(...layout.map(node => node.y + node.height)) - Math.min(...layout.map(node => node.y));
  const fittedArea = Math.max(width / aspect, height) ** 2 * aspect;
  const fill = layout.reduce((sum, node) => sum + node.width * node.height, 0) / fittedArea;
  assert.ok(fill >= minimumFill, `tables fill only ${(fill * 100).toFixed(2)}% of a ${aspect}:1 viewport`);
  assert.deepEqual(layoutSchema(nodes, edges, expanded, aspect), layout, 'automatic layout is deterministic');
  return layout;
}

function scaleGraph() {
  const nodes = Array.from({length:2000}, (_, i) => table('table_' + i));
  const edges = nodes.slice(1).map((node, i) => relation('edge_' + i, nodes[Math.floor(i / 3)].id, node.id));
  for (let i = 0; i < 422; i++) edges.push(relation('extra_' + i, nodes[(i * 17) % 2000].id, nodes[(i * 31 + 1) % 2000].id));
  return {nodes, edges};
}

test('layout handles a six-thousand-table FK chain without recursive stack growth', () => {
  const nodes = Array.from({length:6000}, (_, i) => table('chain_' + String(i).padStart(5, '0')));
  const edges = nodes.slice(1).map((node, i) => relation('edge_' + i, nodes[i].id, node.id));
  const layout = assertCompactLayout(nodes, edges);
  assert.ok(layout.find(node => node.id === nodes[0].id).x < layout.find(node => node.id === nodes.at(-1).id).x);
});

test('wide hubs and giant cycles fit both landscape and portrait workspaces', () => {
  const nodes = Array.from({length:2000}, (_, index) => table('table_' + index));
  const star = nodes.slice(1).map((node, index) => relation('star_' + index, nodes[0].id, node.id));
  const cycle = nodes.map((node, index) => relation('cycle_' + index, node.id, nodes[(index + 1) % nodes.length].id));
  for (const aspect of [0.6, 2.2]) {
    assertCompactLayout(nodes, star, new Set(), aspect);
    assertCompactLayout(nodes, cycle, new Set(), aspect);
  }
});

test('uneven layers and disconnected components do not form an L-shaped diagram with a huge void', () => {
  const nodes = Array.from({length:2000}, (_, index) => table('table_' + index));
  const edges = [];
  // One tall branching component, one long chain, many small components and
  // isolated tables reproduce the extreme width/height mixture of real schemas.
  for (let index = 1; index < 650; index++) edges.push(relation('branch_' + index, nodes[Math.floor((index - 1) / 32)].id, nodes[index].id));
  for (let index = 651; index < 1300; index++) edges.push(relation('chain_' + index, nodes[index - 1].id, nodes[index].id));
  for (let index = 1300; index < 1800; index += 5) {
    for (let offset = 1; offset < 5; offset++) edges.push(relation('small_' + (index + offset), nodes[index].id, nodes[index + offset].id));
  }
  for (const aspect of [0.7, 1.8]) assertCompactLayout(nodes, edges, new Set(), aspect);
});

test('mixed expanded card heights remain compact and never overlap', () => {
  const nodes = Array.from({length:240}, (_, index) => ({
    ...table('table_' + index),
    fields:[...table('table_' + index).fields, ...Array.from({length:index % 7 * 5}, (_, field) => ({name:'value_' + field, type:'string'}))],
  }));
  const edges = nodes.slice(1).map((node, index) => relation('edge_' + index, nodes[Math.floor(index / 5)].id, node.id));
  // A table with many foreign keys is tall even when it is not expanded.
  nodes.at(-1).fields.push(...Array.from({length:102}, (_, index) => ({name:'related_' + index, type:'integer', fk:true})));
  const expanded = new Set(nodes.filter((_, index) => index % 3 === 0).map(node => node.id));
  for (const aspect of [0.65, 2.1]) assertCompactLayout(nodes, edges, expanded, aspect, 0.13);
});

test('the shared spatial index agrees with obstacle intersection for long and negative-coordinate segments', () => {
  const nodes = Array.from({length:2000}, (_, i) => ({...table('n' + i), x:(i % 40) * 310 - 400, y:Math.floor(i / 40) * 190 - 300, width:240, height:138}));
  const context = createRoutingContext(nodes);
  assert.equal(context.large, true);
  for (let i = 0; i < 400; i++) {
    const a = {x:((i * 17) % 13000) - 1000, y:((i * 137) % 11000) - 1000};
    const b = i % 2 ? {x:a.x + 8300, y:a.y} : {x:a.x, y:a.y + 9300};
    assert.equal(context.blocked(a, b), context.obstacles.some(r => intersects(a, b, r)));
  }
});

test('large routing detours around local obstacles without searching distant tables', () => {
  const nodes = layoutSchema([table('source'), table('target')], []);
  const source = {...nodes[0], id:'source', x:0, y:0}, target = {...nodes[1], id:'target', x:800, y:0};
  const middle = {...source, id:'middle', x:380, y:-30, width:260, height:230};
  const distant = Array.from({length:2000}, (_, i) => ({...source, id:'distant_' + i, x:2000 + i * 300, y:2000}));
  const all = [source, target, middle, ...distant], context = createRoutingContext(all);
  const route = routeEdge(source, target, relation('edge', source.id, target.id), all, 0, context);
  for (let i = 1; i < route.points.length; i++) assert.equal(intersects(route.points[i - 1], route.points[i], middle), false);
});

test('bounded routing uses free corridors between dense columns with uneven card sizes', () => {
  const base = layoutSchema([table('base')], [])[0], nodes = [];
  for (let column = 0; column < 12; column++) {
    let y = column * 17;
    for (let row = 0; row < 40; row++) {
      const node = {
        ...base, id:`column_${column}_row_${row}`, x:column * 500, y,
        width:(row + column) % 3 === 0 ? 240 : 360,
        height:138 + ((row * 7 + column) % 9) * 26,
      };
      nodes.push(node); y += node.height + 48;
    }
  }
  // Each column has a clear vertical corridor on either side and the space
  // above all cards is free. Uneven rows rule out a single horizontal shortcut;
  // narrow endpoint cards must not send their route through wider neighbours.
  const context = createRoutingContext(nodes), blocked = context.blocked;
  let probes = 0;
  context.blocked = (a, b) => { probes++; return blocked(a, b); };
  for (const [from, to] of [[3, 438], [6, 455], [9, 457], [438, 3], [3, 36]]) {
    const source = nodes[from], target = nodes[to];
    probes = 0;
    const route = routeEdge(source, target, relation('edge', source.id, target.id), nodes, 0, context);
    assert.ok(probes < 4200, `an edge exceeded the bounded routing work: ${probes} obstacle probes`);
    assert.equal(route.points[0].y, source.y + 69);
    assert.equal(route.points.at(-1).y, target.y + 95);
    assert.ok(route.points.every(point => Number.isFinite(point.x) && Number.isFinite(point.y)));
    for (let index = 1; index < route.points.length; index++) {
      const before = route.points[index - 1], after = route.points[index];
      assert.ok(before.x === after.x || before.y === after.y);
      for (const obstacle of nodes) if (obstacle !== source && obstacle !== target) {
        assert.equal(intersects(before, after, obstacle), false, `route ${from} → ${to} crosses ${obstacle.id}`);
      }
    }
  }
});

test('routing search stays bounded on a dense two-thousand-table diagram', () => {
  const {nodes, edges} = scaleGraph(), start = performance.now();
  const layout = layoutSchema(nodes, edges), byId = new Map(layout.map(node => [node.id, node]));
  const context = createRoutingContext(layout);
  let probes = 0, maxProbes = 0;
  const blocked = context.blocked;
  context.blocked = (a, b) => { probes++; return blocked(a, b); };
  for (const edge of edges) {
    probes = 0;
    const source = byId.get(edge.source), target = byId.get(edge.target);
    const route = routeEdge(source, target, edge, layout, 0, context);
    assert.equal(route.points[0].y, source.y + 69);
    assert.equal(route.points.at(-1).y, target.y + 95);
    for (let i = 1; i < route.points.length; i++) assert.ok(route.points[i - 1].x === route.points[i].x || route.points[i - 1].y === route.points[i].y);
    maxProbes = Math.max(maxProbes, probes);
  }
  assert.ok(maxProbes < 4200, `an edge exceeded the bounded routing work: ${maxProbes} obstacle probes`);
  assert.ok(performance.now() - start < 5000, 'a two-thousand-table layout and routing exceeded the generous five-second regression budget');
});
