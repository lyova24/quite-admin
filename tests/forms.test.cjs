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

const {parseValue, composeValue, rangeReversed} = require('../src/quite_admin/static/datetime.js');
test('shared picker preserves wall time, trailing microseconds and offsets when only the date changes', () => {
  for (const value of ['2026-11-01T12:34:56.120000+03:00', '0001-01-01T00:00:00.000001Z', '2024-02-29T23:59:00']) {
    const parts = parseValue(value, 'datetime');
    assert.equal(composeValue(parts, 'datetime'), value);
    parts.day = '2026-12-31';
    assert.equal(composeValue(parts, 'datetime'), '2026-12-31' + value.slice(10));
  }
  assert.equal(composeValue({...parseValue('12:34:00.123456-05:30', 'time'), time:'12:35'}, 'time'), '12:35:00.123456-05:30');
  for (const value of ['bad', '2023-02-29T12:00', '2024-02-29T24:00', '2024-02-29T12:00+24:00', '2024-02-29T12:00+03:00:30']) assert.equal(parseValue(value, 'datetime'), null);
  assert.equal(composeValue({day:'', time:'12:00', fraction:'', offset:''}, 'datetime'), null);
  assert.equal(composeValue({...parseValue('12:34', 'time'), fraction:'1234567'}, 'time'), null);
  for (const kind of ['date', 'datetime', 'time']) assert.equal(composeValue(parseValue('', kind), kind), '');
});
test('range ordering compares exact microseconds and explicit offsets without rewriting values', () => {
  assert.equal(rangeReversed('2024-02-29', '2024-03-01', 'date'), false);
  assert.equal(rangeReversed('2024-03-01', '2024-02-29', 'date'), true);
  assert.equal(rangeReversed('2026-11-01T12:00:00.000002Z', '2026-11-01T12:00:00.000001Z', 'datetime'), true);
  assert.equal(rangeReversed('2026-11-01T15:00:00.000001+03:00', '2026-11-01T12:00:00.000002Z', 'datetime'), false);
  assert.equal(rangeReversed('12:00:00.000002', '12:00:00.000001', 'time'), true);
  assert.equal(rangeReversed('12:00+03:00', '10:00Z', 'time'), false);
  assert.equal(rangeReversed('2026-11-01T12:00', '2026-11-01T13:00Z', 'datetime'), null);
  assert.equal(rangeReversed('', '2024-03-01', 'date'), false);
});
