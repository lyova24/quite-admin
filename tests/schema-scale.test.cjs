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

function scaleGraph() {
  const nodes = Array.from({length:2000}, (_, i) => table('table_' + i));
  const edges = nodes.slice(1).map((node, i) => relation('edge_' + i, nodes[Math.floor(i / 3)].id, node.id));
  for (let i = 0; i < 422; i++) edges.push(relation('extra_' + i, nodes[(i * 17) % 2000].id, nodes[(i * 31 + 1) % 2000].id));
  return {nodes, edges};
}

test('layout handles a six-thousand-table FK chain without recursive stack growth', () => {
  const nodes = Array.from({length:6000}, (_, i) => table('chain_' + String(i).padStart(5, '0')));
  const edges = nodes.slice(1).map((node, i) => relation('edge_' + i, nodes[i].id, node.id));
  const layout = layoutSchema(nodes, edges);
  assert.equal(layout.length, nodes.length);
  assert.ok(layout.every(node => Number.isFinite(node.x) && Number.isFinite(node.y)));
  assert.ok(layout.find(node => node.id === nodes[0].id).x < layout.find(node => node.id === nodes.at(-1).id).x);
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
