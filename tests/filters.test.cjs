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
test('existing unrelated conditions cannot be silently overwritten', () => {
  assert.throws(() => updateQuery(new URLSearchParams('f.price.eq=10'), null, entries(price,'eq',['20'])), /conflict/);
});
test('type-specific operators and NULL do not need an extra field', () => {
  assert.deepEqual(operators({kind:'boolean'}), ['eq']);
  assert.deepEqual(operators({kind:'json',nullable:true}), ['null','not_null']);
  assert.deepEqual(entries(price,'not_null',[]), [['f.price.is_null','false']]);
  assert.deepEqual(entries({id:'r.tags',kind:'relation'},'eq',['WyIxIl0']), [['r.tags','WyIxIl0']]);
  assert.throws(() => entries({id:'f.name',kind:'string'},'between',['a','b']), /Invalid/);
});
