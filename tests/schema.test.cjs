const { test } = require('node:test');
const assert = require('node:assert/strict');
const { layoutSchema, projectGraph, routeEdge, compactFields } = require('../src/quite_admin/static/schema.js');
const node = (id, extra = 3) => ({id, name:id, label:id, fields:[{name:'id',type:'integer',pk:true},{name:'owner_id',type:'integer',fk:true,linked:true},...Array.from({length:extra},(_,i)=>({name:'value_'+i,type:'string'}))]});
const edge = (id, source, target, kind='o2m') => ({id,source,target,kind,sourceFields:['id'],targetFields:['owner_id']});

test('automatic layout handles cycles, parallel/self edges, isolated tables and expanded cards without overlap', () => {
  const nodes = Array.from({length:25},(_,i)=>node('table_'+i,i%6));
  const edges = nodes.slice(1,21).map((item,i)=>edge('e'+i, nodes[Math.floor(i/3)].id,item.id));
  edges.push(edge('cycle','table_10','table_0'),edge('self','table_1','table_1'),edge('parallel','table_0','table_1','m2m'));
  const expanded = new Set(['table_2','table_8','table_15']);
  const layout = layoutSchema(nodes, edges, expanded);
  assert.equal(layout.length,nodes.length);
  for(const a of layout) for(const b of layout) if(a.id!==b.id) {
    assert.ok(a.x+a.width<=b.x || b.x+b.width<=a.x || a.y+a.height<=b.y || b.y+b.height<=a.y,`${a.id} overlaps ${b.id}`);
  }
  assert.deepEqual(layoutSchema(nodes,edges,expanded),layout);
  assert.equal(layout.find(n=>n.id==='table_2').shownFields.length,nodes[2].fields.length);
  assert.equal(compactFields(nodes[0]).length,2);
  assert.deepEqual(layoutSchema([],[]),[]);
});

test('m2m expansion inserts its junction and two correctly oriented one-to-many edges', () => {
  const a=node('a'),b=node('b'),junction={...node('j'),junction:true};
  const relation={...edge('m','a','b','m2m'),targetFields:['id'],junction:'j',junctionSourceFields:['a_id'],junctionTargetFields:['b_id']};
  const graph={nodes:[a,b],junctions:[junction],edges:[relation]};
  assert.equal(projectGraph(graph,new Set(['a','b']),new Set()).edges[0].kind,'m2m');
  const expanded=projectGraph(graph,new Set(['a','b','j']),new Set(['m']));
  assert.equal(expanded.nodes.length,3);
  assert.deepEqual(expanded.edges.map(e=>[e.source,e.target,e.targetFields,e.kind]),[['a','j',['a_id'],'o2m'],['b','j',['b_id'],'o2m']]);
  assert.equal(projectGraph(graph,new Set(['a','j']),new Set(['m'])).edges.length,1);
  assert.equal(projectGraph(graph,new Set(),new Set()).nodes.length,0);
});

test('an already registered junction reuses its table and physical edges', () => {
  const relation={...edge('m','a','b','m2m'),targetFields:['id'],junction:'j',junctionSourceFields:['a_id'],junctionTargetFields:['b_id']};
  const graph={nodes:[node('a'),node('b'),node('j')],edges:[relation,{...edge('left','a','j'),targetFields:['a_id']},{...edge('right','b','j'),targetFields:['b_id']} ]};
  const output=projectGraph(graph,new Set(['a','b','j']),new Set(['m']));
  assert.equal(output.nodes.length,3);assert.equal(output.edges.length,2);
  assert.ok(output.edges.every(e=>e.originals.includes('m')));
});

test('orthogonal routing avoids an intervening table and preserves field endpoints', () => {
  const base=node('a'),fields=compactFields(base);
  const a={...base,x:0,y:0,width:260,height:138,shownFields:fields};
  const b={...node('b'),x:800,y:0,width:260,height:138,shownFields:fields};
  const obstacle={...node('middle'),x:380,y:-30,width:260,height:230,shownFields:fields};
  const route=routeEdge(a,b,edge('e','a','b'),[a,b,obstacle]);
  assert.equal(route.points[0].x,260);assert.equal(route.points.at(-1).x,800);
  for(let i=1;i<route.points.length;i++) {
    const p=route.points[i-1],q=route.points[i];
    assert.ok(p.x===q.x || p.y===q.y);
    const intersects = p.x===q.x ? p.x>obstacle.x && p.x<obstacle.x+obstacle.width && Math.max(p.y,q.y)>obstacle.y && Math.min(p.y,q.y)<obstacle.y+obstacle.height : p.y>obstacle.y && p.y<obstacle.y+obstacle.height && Math.max(p.x,q.x)>obstacle.x && Math.min(p.x,q.x)<obstacle.x+obstacle.width;
    assert.equal(intersects,false);
  }
  const self=routeEdge(a,a,edge('self','a','a'),[a]);
  assert.equal(self.points.at(-1).y,a.y+56+26+13);
});
