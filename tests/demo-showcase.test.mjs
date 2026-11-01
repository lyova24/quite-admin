import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Store} from '../demo/store.mjs';
import {filterActivity, activityPage} from '../demo/activity.mjs';
import {csv, matchingRows, listWindow} from '../demo/listing.mjs';
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
