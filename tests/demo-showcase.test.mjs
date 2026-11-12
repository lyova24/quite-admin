import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Store} from '../demo/store.mjs';
import {filterActivity, activityPage} from '../demo/activity.mjs';
import {csv, matchingRows, listWindow, exportColumns, listCell} from '../demo/listing.mjs';
import {recordKey} from '../demo/store.mjs';
import {valueModel, renderValue, escapeHTML} from '../demo/values.mjs';
const seed = JSON.parse(await readFile(new URL('../build/docs/demo/seed.json',import.meta.url)));

test('history dates include both complete UTC endpoints and preserve other conditions',()=>{
  const store = new Store(seed);
  const events = ['2026-01-01T23:59:59.999999Z','2026-01-02T00:00:00.000000Z','2026-01-03T23:59:59.999999Z','2026-01-04T00:00:00.000000Z'].map((occurred_at,id)=>({id,occurred_at,subject:'admin',collection:'products',action:'edit',outcome:'success'}));
  const query = new URLSearchParams({date_mode:'range',date_from:'2026-01-02',date_to:'2026-01-03',subject:'admin',collection:'products'});
  assert.deepEqual(filterActivity(events,query).map(event=>event.id),[2,1]);
  query.set('date_mode','day');query.set('date','2026-01-02');
  assert.deepEqual(filterActivity(events,query).map(event=>event.id),[1]);
  query.set('date_mode','all');
  assert.equal(filterActivity(events,query).length,4);
  assert.ok(filterActivity(store.activity,new URLSearchParams()).every(event=>['edit','inline_edit','create','delete'].includes(event.action)));
  assert.ok(filterActivity(store.activity,new URLSearchParams({action:'',collection:'__auth__'})).every(event=>event.collection===''));
});

test('CSV exports all filtered sorted matches and protects formula-like cells',()=>{
  const store = new Store(seed), c = store.collection('products');
  c.records[0].values.name = '=HYPERLINK("example")\nsecond line';
  const rows=matchingRows(store,'products',new URLSearchParams({sort:'price',direction:'desc'}));
  assert.equal(rows.length,8);
  const result=csv(c,rows,['name','price']);
  assert.ok(result.startsWith('\uFEFF"Name","Price"\r\n'));
  assert.ok(result.includes('"\'=HYPERLINK(""example"")\nsecond line"'));
  assert.ok(result.indexOf('42.00') < result.indexOf('12.00'));
  assert.equal(matchingRows(store,'products',new URLSearchParams({'f.active.eq':'false'})).length,1);
});

test('cursor windows traverse both ways and are independent of offset page input',()=>{
  const store = new Store(seed), all=matchingRows(store,'orders',new URLSearchParams());
  const first=listWindow(all,new URLSearchParams({page:'500'}),true);
  assert.equal(first.rows.length,5);assert.equal(first.hasPrevious,false);assert.equal(first.hasNext,true);
  const second=listWindow(all,new URLSearchParams({after:first.rows.at(-1).key}),true);
  assert.equal(second.rows.length,3);assert.equal(second.hasPrevious,true);assert.equal(second.hasNext,false);
  assert.deepEqual(listWindow(all,new URLSearchParams({before:second.rows[0].key}),true).rows,first.rows);
  const filtered=matchingRows(store,'orders',new URLSearchParams({'f.status.eq':'pending'}));
  assert.equal(listWindow(filtered,new URLSearchParams(),true).hasNext,false);
});

test('history renders both languages/views, escapes values, and retains filters in links',()=>{
  const store=new Store(seed),row=store.collection('products').records[0];
  store.save('products',row.key,{name:'<img src=x onerror=alert(1)>'},{},store.revision('products',row.key));
  const e=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  for(const language of ['en','ru'])for(const view of ['journal','table']){
    const t=(text,values={})=>Object.entries(values).reduce((text,[name,value])=>text.replaceAll('{'+name+'}',value),language==='ru'?seed.translations[text]||text:text);
    const html=activityPage({store,seed,language,t,e,href:(slug,key)=>'#/models/'+slug+'/'+key,query:new URLSearchParams({view,subject:'admin',date_mode:'range',date_from:'2026-01-01'})});
    assert.ok(html.includes('subject=admin'));
    assert.ok(html.includes('date_from=2026-01-01'));
    assert.ok(!html.includes('<img src=x'));
    assert.ok(html.includes('&lt;img src=x'));
    assert.ok(html.includes('data-history-period'));
    assert.ok(html.includes('data-history-changes'));
    assert.ok(html.includes(view==='table'?'class="history-table"':'class="activity-journal"'));
  }
});


test('cursor collections sort non-key columns before paginating',()=>{
  const store=new Store(seed);
  const query=new URLSearchParams({sort:'total',direction:'desc'});
  const rows=matchingRows(store,'orders',query);
  const values=rows.map(row=>Number(row.values.total));
  assert.deepEqual(values,[...values].sort((a,b)=>b-a));
  const first=listWindow(rows,query,true);
  query.set('after',first.rows.at(-1).key);
  const second=listWindow(rows,query,true);
  assert.deepEqual([...first.rows,...second.rows],rows);
});

test('showcase metadata exports permitted policies, rich displays and allowlisted actions without secrets',()=>{
  const samples=seed.collections.field_samples, accounts=seed.collections.demo_accounts;
  assert.equal(samples.recordLabel,'title');
  assert.equal(samples.fields.find(field=>field.name==='website').display,'url');
  assert.equal(samples.fields.find(field=>field.name==='ticket').urlTemplate,'https://example.com/issues/{value}');
  assert.equal(samples.fields.find(field=>field.name==='quantity').minimum,0);
  assert.deepEqual(samples.actions.map(action=>action.effect),[{status:'archived'},{status:'published'}]);
  assert.deepEqual(seed.collections.products.bulkActions.map(action=>action.effect),[{active:'false'}]);
  for(const collection of Object.values(seed.collections)) {
    assert.ok(!collection.fields.some(field=>['api_key','password_hash'].includes(field.name)));
    assert.ok(collection.records.every(row=>!('api_key' in row.values)&&!('password_hash' in row.values)));
    assert.ok(!collection.actions.some(action=>'handler' in action));
  }
  assert.equal(accounts.serverOnlyWrites,true);
  assert.equal(accounts.canCreate,false);
  assert.equal(accounts.canEdit,false);
  assert.deepEqual(accounts.inline,[]);
  assert.deepEqual(seed.collections.reference_rates.inline,[]);
  const password=accounts.inputFields.find(field=>field.kind==='password');
  assert.ok(password);
  assert.equal(password.default,null);
  assert.ok(!('value' in password));
});

test('manual composite identities are computed after inputs, preserve UTF-8 and reject duplicates atomically',()=>{
  const store=new Store(seed), collection=store.collection('regional_prices');
  const values={region:'Ев🌍',sku:'SKU/42',price:'12.50',currency:'EUR'};
  const key=store.save('regional_prices',null,values,{});
  const encoded=key.replaceAll('-','+').replaceAll('_','/');
  const decoded=new TextDecoder().decode(Uint8Array.from(atob(encoded),char=>char.charCodeAt(0)));
  assert.deepEqual(JSON.parse(decoded),['Ев🌍','SKU/42']);
  assert.equal(key,recordKey(collection,values));
  assert.equal(store.label('regional_prices',store.record('regional_prices',key)),'Ев🌍 · SKU/42');
  store.collection('regional_prices').recordLabel='sku';
  assert.equal(store.label('regional_prices',store.record('regional_prices',key)),'SKU/42');
  const before=structuredClone(store.snapshot());
  assert.throws(()=>store.save('regional_prices',null,values,{}),/constraint/);
  assert.deepEqual(store.snapshot(),before);
  assert.throws(()=>store.save('regional_prices',null,{sku:'missing region',price:'1',currency:'USD'},{}),/primary key/);
  assert.deepEqual(store.snapshot(),before);
});

test('UUID defaults and enum defaults stay canonical, with validation rollback for UUIDs and hook bounds',()=>{
  const store=new Store(seed);
  const key=store.save('field_samples',null,{title:'New sample'},{});
  const row=store.record('field_samples',key);
  assert.match(row.values.public_id,/^[a-f0-9-]{36}$/);
  assert.equal(row.values.status,'draft');
  assert.equal(row.values.quantity,'1');
  assert.equal(row.values.ratio,'1.0');
  store.save('field_samples',key,{public_id:'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'},{});
  assert.equal(store.record('field_samples',key).values.public_id,'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
  const before=structuredClone(store.snapshot());
  for(const values of [{public_id:'invalid'},{quantity:'-1'},{ratio:'-0.1'},{status:'other'}]) {
    assert.throws(()=>store.save('field_samples',key,values,{}));
    assert.deepEqual(store.snapshot(),before);
  }
});

test('read-only model and relationship policies protect direct local writes',()=>{
  const store=new Store(seed), rate=store.collection('reference_rates').records[0];
  const folder=store.collection('folders').records.find(row=>row.links.samples?.length);
  const before=structuredClone(store.snapshot());
  assert.throws(()=>store.save('reference_rates',rate.key,{value:'999'},{}),/not permitted/);
  assert.throws(()=>store.delete('reference_rates',rate.key),/not permitted/);
  assert.throws(()=>store.save('reference_rates',null,{code:'OTHER',value:'1'},{}),/not permitted/);
  assert.throws(()=>store.save('folders',folder.key,{name:'unsaved'},{samples:[]}),/read-only/);
  assert.deepEqual(store.snapshot(),before);
});

test('required composite relationships replace both foreign keys and roll back invalid changes',()=>{
  const store=new Store(seed), row=store.collection('price_alerts').records[0];
  const relation=store.collection('price_alerts').relations.find(relation=>relation.name==='regional_price');
  assert.deepEqual(relation.sourceReferences,{region:'region',sku:'sku'});
  relation.sourceFields.reverse(); // Mapping follows column names, not incidental metadata order.
  const target=store.collection('regional_prices').records.find(candidate=>!row.links.regional_price.includes(candidate.key));
  store.save('price_alerts',row.key,{threshold:'16.00'},{regional_price:[target.key]});
  const saved=store.record('price_alerts',row.key);
  assert.equal(saved.values.region,target.values.region);
  assert.equal(saved.values.sku,target.values.sku);
  const before=structuredClone(store.snapshot());
  assert.throws(()=>store.save('price_alerts',row.key,{threshold:'20.00'},{regional_price:[]}),/required/);
  assert.throws(()=>store.save('price_alerts',row.key,{threshold:'-1'},{}));
  assert.deepEqual(store.snapshot(),before);
});

test('rich displays escape markup, restrict URL schemes and preserve large JSON integers',()=>{
  assert.equal(valueModel({display:'url'},'javascript:alert(1)').href,null);
  assert.equal(valueModel({display:'url'},'https:example.com').href,null);
  assert.equal(valueModel({display:'url'},'https:////example.com').href,null);
  assert.equal(valueModel({display:'url'},'https://example.com/\\evil').href,null);
  assert.equal(valueModel({display:'url'},' https://example.com/').href,null);
  const url=valueModel({urlTemplate:'https://example.com/issues/{value}'},"abc/42!'");
  assert.equal(url.href,'https://example.com/issues/abc%2F42%21%27');
  const json=valueModel({display:'json'},'{"n":9007199254740993,"text":"</pre><script>bad</script>"}');
  assert.ok(json.text.includes('9007199254740993'));
  assert.ok(!json.text.includes('9007199254740992'));
  const html=renderValue({label:'Data',display:'json'},json.text,{compact:true});
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('value-details'));
  assert.ok(html.includes('data-copy-value'));
  const cell=listCell({slug:'test',row:{key:'1',values:{url:'https://example.com/'}},
    field:{name:'url',label:'URL',display:'url'},editable:true,t:text=>text,e:escapeHTML});
  assert.ok(cell.includes('rel="noopener noreferrer"'));
  assert.ok(!cell.includes('data-inline-endpoint'));
});

test('related CSV uses stable aligned one-hop values and preserves one row per source',()=>{
  const store=new Store(seed), collection=store.collection('products');
  const row=collection.records.find(row=>row.links.tags.length>1);
  const expected=[...row.links.tags].sort().map(key=>store.record('tags',key).values.name).join('\n');
  assert.ok(exportColumns(collection,store).some(column=>column.name==='tags.name'));
  const result=csv(collection,[row],['name','tags.name','tags.id'],store);
  assert.ok(result.startsWith('\uFEFF"Name","Tags · Name","Tags · Id"\r\n'));
  assert.ok(result.includes('"'+expected+'"'));
  assert.throws(()=>csv(collection,[row],['api_key'],store),/valid export columns/);
  assert.throws(()=>csv(collection,[row],['tags.api_key'],store),/valid export columns/);
});
