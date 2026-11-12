import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Store} from '../demo/store.mjs';
import {bulkCommands, runBulk, runRecordAction} from '../demo/actions.mjs';
import {filterActivity} from '../demo/activity.mjs';
const seed = JSON.parse(await readFile(new URL('../build/docs/demo/seed.json',import.meta.url)));

test('showcase actions persist allowed effects and reject stale or unknown commands', () => {
  const store = new Store(seed), row = store.collection('field_samples').records[0];
  const revision = store.revision('field_samples',row.key);
  runRecordAction(store,'field_samples',row.key,'archive',revision);
  assert.equal(store.record('field_samples',row.key).values.status,'archived');
  assert.equal(filterActivity(store.activity,new URLSearchParams())[0].action,'action:archive');
  assert.throws(() => runRecordAction(store,'field_samples',row.key,'publish',revision), /changed/);
  assert.throws(() => runRecordAction(store,'field_samples',row.key,'forged'), /Unknown action/);
  assert.deepEqual(bulkCommands(store.collection('reference_rates')),[]);
  assert.deepEqual(bulkCommands(store.collection('demo_accounts')),[]);
});

test('bulk commands process only selected keys and preserve successful results on partial failure', () => {
  const store = new Store(seed), rows = store.collection('products').records;
  const pending = {slug:'products',action:'action:deactivate',keys:[rows[0].key,rows[1].key],
    labels:Object.fromEntries(rows.map(row=>[row.key,row.values.name])),
    revisions:Object.fromEntries(rows.map(row=>[row.key,store.revision('products',row.key)]))};
  store.save('products',rows[1].key,{name:'Changed elsewhere'},{});
  const results = runBulk(store,pending);
  assert.deepEqual(results.map(result=>result.success),[true,false]);
  assert.equal(store.record('products',rows[0].key).values.active,'false');
  assert.equal(store.record('products',rows[1].key).values.active,'true');
  assert.equal(store.record('products',rows[2].key).values.active,'true');
  assert.throws(() => runBulk(store,{...pending,action:'action:forged'}),/Unknown action/);
  assert.throws(() => runBulk(store,{...pending,keys:[]}),/Select between/);
  const deletion = runBulk(store,{...pending,action:'delete'});
  assert.deepEqual(deletion.map(result=>result.success),[false,false]);
  assert.ok(store.record('products',rows[0].key));
});
