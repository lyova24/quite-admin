const {test} = require('node:test');
const assert = require('node:assert/strict');
const {operators, entries, updateQuery} = require('../src/quite_admin/static/filters.js');
const price = {id:'f.price', kind:'number', nullable:true};
test('exact numbers and large identifiers are transmitted as strings', () => {
  const raw = '123456789012345678.123456789';
  assert.deepEqual(entries(price, 'eq', [raw]), [['f.price.eq', raw]]);
  assert.deepEqual(entries(price, 'between', [raw, '2e30']), [['f.price.gte', raw], ['f.price.lte', '2e30']]);
  assert.equal(operators(price)[0], 'eq');
});
test('changing range to equality replaces both bounds and keeps search, sort, other filters', () => {
  const params = new URLSearchParams('q=pen&sort=name&direction=desc&limit=50&page=4&f.price.gte=10&f.price.lte=20&f.active.eq=false');
  const next = updateQuery(params, {parameters:['f.price.gte','f.price.lte']}, entries(price,'eq',['15']));
  assert.equal(next.toString(), 'q=pen&sort=name&direction=desc&limit=50&page=1&f.active.eq=false&f.price.eq=15');
  assert.equal(params.get('f.price.gte'), '10');
});
test('repeated field conditions get separate slots, preserve values and reject duplicates', () => {
  const first = new URLSearchParams('q=Alex&f.price.ne=10');
  const next = updateQuery(first, null, entries(price,'ne',['20']));
  assert.equal(next.get('f.price.ne'), '10');
  assert.equal(next.get('f.price.ne~1'), '20');
  const edited = updateQuery(next, {parameters:['f.price.ne~1']}, entries(price,'ne',['30']));
  assert.equal(edited.get('f.price.ne~1'), '30');
  assert.equal(edited.get('q'), 'Alex');
  const removed = updateQuery(edited, {parameters:['f.price.ne~1']}, []);
  assert.equal(removed.get('f.price.ne'), '10');
  assert.equal(removed.has('f.price.ne~1'), false);
  assert.throws(() => updateQuery(next, null, entries(price,'ne',['10'])), /conflict/);
});
test('type-specific operators and NULL do not need an extra field', () => {
  assert.deepEqual(operators({kind:'boolean'}), ['eq']);
  assert.deepEqual(operators({kind:'json',nullable:true}), ['null','not_null']);
  assert.deepEqual(entries(price,'not_null',[]), [['f.price.is_null','false']]);
  assert.deepEqual(entries({id:'r.tags',kind:'relation'},'eq',['WyIxIl0']), [['r.tags','WyIxIl0']]);
  assert.throws(() => entries({id:'f.name',kind:'string'},'between',['a','b']), /Invalid/);
});

test('text defaults to partial matching and multi-values preserve precision', () => {
  const name = {id:'f.name',kind:'string',nullable:true};
  assert.equal(operators(name)[0], 'icontains');
  assert.ok(operators(name).includes('not_icontains'));
  assert.deepEqual(entries(name,'icontains',['Alex%_!']), [['f.name.icontains','Alex%_!']]);
  assert.deepEqual(entries(name,'empty',[]), [['f.name.is_empty','true']]);
  assert.deepEqual(entries(price,'in',['9007199254740993','123456789012345678.123456789']), [['f.price.in','["9007199254740993","123456789012345678.123456789"]']]);
  const date = {id:'f.created',kind:'datetime',operators:['on','eq','gte','lt']};
  assert.deepEqual(entries(date,'on',['2026-11-01','+03:00']), [['f.created.on','2026-11-01T00:00:00+03:00']]);
  assert.deepEqual(operators({kind:'string',operators:['eq','is_null']}), ['eq','null','not_null']);
});

test('separate ranges are edited and removed as pairs without losing other ranges', () => {
  const first = new URLSearchParams('f.price.gte=10&f.price.lte=20');
  const next = updateQuery(first, null, entries(price,'between',['12','18']));
  assert.equal(next.get('f.price.gte~1'), '12');
  assert.equal(next.get('f.price.lte~1'), '18');
  const edited = updateQuery(next, {parameters:['f.price.gte~1','f.price.lte~1']}, entries(price,'eq',['15']));
  assert.equal(edited.get('f.price.eq~1'), '15');
  assert.equal(edited.get('f.price.gte'), '10');
  assert.equal(edited.has('f.price.lte~1'), false);
  const separate = updateQuery(next, null, entries(price,'between',['10','18']));
  assert.equal(separate.get('f.price.gte~2'), '10');
  assert.equal(separate.get('f.price.lte~2'), '18');
});
