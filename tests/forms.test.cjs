const {test} = require('node:test');
const assert = require('node:assert/strict');
const {tokens, splitTemporal, formatJSON} = require('../src/quite_admin/static/forms.js');
test('JSON formatting preserves number lexemes, duplicate keys, escaped strings and XSS text', () => {
  const raw = '{"id":9007199254740993,"price":1234567890.123456789,"tiny":1e-400,"id":2,"s":"</script>\\\" : ,","empty": [ ],"nested":[true,{"x":null}]}';
  const formatted = formatJSON(raw);
  assert.match(formatted, /9007199254740993/);
  assert.match(formatted, /1234567890\.123456789/);
  assert.match(formatted, /1e-400/);
  assert.equal((formatted.match(/"id"/g) || []).length, 2);
  assert.deepEqual(JSON.parse(formatted), JSON.parse(raw));
  assert.equal(tokens(raw).map(t => t[1]).join(''), raw);
  assert.ok(tokens(raw).some(([kind]) => kind === 'key'));
  assert.throws(() => formatJSON('{bad}'));
  assert.throws(() => formatJSON('['.repeat(42) + '1' + ']'.repeat(42)), /depth/);
});
test('date/time controls retain explicit timezone and subsecond precision without conversion', () => {
  assert.deepEqual(splitTemporal('2026-11-01T12:34:56.123456+03:00', 'datetime'), ['2026-11-01T12:34:56.123456', '+03:00']);
  assert.deepEqual(splitTemporal('2026-11-01T12:34:56Z', 'datetime'), ['2026-11-01T12:34:56', 'Z']);
  assert.deepEqual(splitTemporal('12:34:56.123456-05:30', 'time'), ['12:34:56.123456', '-05:30']);
  assert.deepEqual(splitTemporal('12:34:00', 'time'), ['12:34:00', '']);
  assert.deepEqual(splitTemporal('', 'datetime'), ['', '']);
  assert.equal(splitTemporal('bad submitted value', 'datetime'), null);
  assert.equal(splitTemporal('12:34:56+00:00:30', 'time'), null);
});
