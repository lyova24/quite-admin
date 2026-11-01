const {test} = require('node:test');
const assert = require('node:assert/strict');
const {utcDate, isoDay, shiftDay, monthCells, presetBounds} = require('../src/quite_admin/static/history.js');

test('calendar dates retain UTC boundaries, leap days and years below 100', () => {
  for (const day of ['0001-01-01', '0099-12-31', '2024-02-29', '9999-12-31']) {
    assert.equal(isoDay(utcDate(day)), day);
    assert.equal(utcDate(day).getUTCHours(), 0);
  }
  for (const day of ['0000-01-01', '2023-02-29', '2024-02-30', '20240229']) assert.equal(utcDate(day), null);
  assert.equal(shiftDay('2024-03-01', -1), '2024-02-29');
  assert.equal(shiftDay('2026-01-01', -1), '2025-12-31');
  assert.equal(shiftDay('0001-01-01', -1), '');
  assert.equal(shiftDay('9999-12-31', 1), '');
});

test('Monday-first calendar covers the selected month without generating invalid dates', () => {
  const cells = monthCells(2024, 1);
  assert.equal(cells.length, 42);
  assert.equal(cells[0], '2024-01-29');
  assert.equal(cells.filter(day => day.startsWith('2024-02')).length, 29);
  assert.equal(new Set(cells).size, 42);
  for (const [year, month] of [[1, 0], [9999, 11]]) {
    assert.ok(monthCells(year, month).every(day => !day || utcDate(day)));
  }
});

test('quick periods select full inclusive days and remain stable at month/year boundaries', () => {
  assert.deepEqual(presetBounds('today', '2026-01-01'), {mode:'day', start:'2026-01-01', end:'2026-01-01'});
  assert.deepEqual(presetBounds('yesterday', '2026-01-01'), {mode:'day', start:'2025-12-31', end:'2025-12-31'});
  assert.deepEqual(presetBounds('week', '2024-03-01'), {mode:'range', start:'2024-02-24', end:'2024-03-01'});
  assert.deepEqual(presetBounds('month', '2024-03-01'), {mode:'range', start:'2024-02-01', end:'2024-03-01'});
  assert.deepEqual(presetBounds('this_month', '2024-02-29'), {mode:'range', start:'2024-02-01', end:'2024-02-29'});
  assert.deepEqual(presetBounds('all', '2026-01-01'), {mode:'all', start:'', end:''});
  assert.equal(presetBounds('unknown', '2026-01-01'), null);
  assert.equal(presetBounds('today', 'invalid'), null);
});
