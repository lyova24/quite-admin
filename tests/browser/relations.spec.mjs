import {test, expect} from '@playwright/test';

async function login(page, demo = false) {
  await page.goto(demo ? 'http://127.0.0.1:8128/' : '/admin/');
  await page.getByLabel('Username', {exact: true}).fill('admin');
  await page.getByLabel('Password', {exact: true}).fill(demo ? 'admin' : 'browser-test-password');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Sign in', exact: true})).toHaveCount(0);
  if (demo) await page.locator('[data-tour-consent]').getByRole('button', {name: 'Not now', exact: true}).click();
}

const selectedValues = picker => picker.locator('select').evaluate(select =>
  [...select.selectedOptions].map(option => option.value).filter(Boolean));

test('single relation supports ID search, keyboard choice and clearing without submitting', async ({page}) => {
  await login(page);
  await page.goto('/admin/models/entries/new');
  const picker = page.locator('[data-relation-picker]').filter({
    has: page.locator('[name="__relation__to_customers_by_customer_id"]'),
  });
  const trigger = picker.locator('.picker-trigger');
  await trigger.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  const search = picker.getByRole('searchbox');
  await expect(search).toBeFocused();
  await search.fill('52');
  const option = picker.getByRole('radio');
  await expect(option).toHaveCount(1);
  await expect(picker.locator('.picker-results')).toContainText('Maria Jones');
  await expect(picker.locator('.picker-option-description')).toContainText('52');
  await search.press('ArrowDown');
  await expect(option).toBeFocused();
  await option.press('Enter');
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(picker.locator('.picker-selection')).toContainText('Maria Jones');
  await expect(picker.locator('select')).toHaveValue('WyI1MiJd');
  await expect(page).toHaveURL(/\/entries\/new$/);
  await picker.getByRole('button', {name: 'Clear selection', exact: true}).click();
  await expect(picker.locator('select')).toHaveValue('');
  await expect(picker.locator('.picker-selection')).toBeHidden();
  await expect(trigger).toBeFocused();
});

for (const kind of ['one_to_one', 'one_to_many', 'many_to_many']) {
  test(`${kind} picker preserves selection through searches and submits native values`, async ({page}) => {
    await login(page, true);
    const seed = await (await page.request.get('http://127.0.0.1:8128/seed.json')).json();
    const [slug, collection] = Object.entries(seed.collections).find(([, collection]) =>
      collection.relations.some(relation => relation.kind === kind) && collection.records.length);
    const relation = collection.relations.find(relation => relation.kind === kind);
    const source = collection.records.find(row => row.links[relation.name]?.length) || collection.records[0];
    await page.goto(`http://127.0.0.1:8128/#/models/${slug}/${encodeURIComponent(source.key)}`);
    const picker = page.locator('[data-relation-picker]').filter({
      has: page.locator(`select[name="__relation__${relation.name}"]`),
    });
    const trigger = picker.locator('.picker-trigger');
    await trigger.click();
    const multiple = kind !== 'one_to_one';
    const options = picker.getByRole(multiple ? 'checkbox' : 'radio');
    await expect(options.first()).toBeVisible();
    const unselected = picker.locator(`input[type=${multiple ? 'checkbox' : 'radio'}]:not(:checked)`);
    const candidate = await unselected.count() ? unselected.first() : options.first();
    const key = await candidate.getAttribute('data-key');
    await candidate.check();
    await expect(picker.locator('.picker-selection')).toBeVisible();
    expect(await selectedValues(picker)).toContain(key);
    if (!(await picker.locator('details').evaluate(node => node.open))) await trigger.click();
    await expect(picker.locator('details')).toHaveAttribute('open', '');
    const selected = await selectedValues(picker);
    await picker.getByRole('searchbox').fill('no record can match this search');
    await expect(picker.locator('.picker-status')).toHaveText('No matching records.');
    expect(await selectedValues(picker)).toEqual(selected);
    await picker.getByRole('searchbox').press('Escape');
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(await picker.locator('select').evaluate(select =>
      new FormData(select.form).getAll(select.name))).toEqual(selected);
    const revision = await page.locator('[name=__revision]').inputValue();
    await page.getByRole('button', {name:'Save changes', exact:true}).click();
    await expect(page.locator('[name=__revision]')).not.toHaveValue(revision);
    await expect(page.locator('#form-error')).toBeHidden();
    await page.reload();
    await expect(picker.locator('.picker-trigger')).toBeVisible();
    expect(await selectedValues(picker)).toEqual(selected);
    await picker.getByRole('button', {name: 'Clear selection', exact: true}).click();
    expect(await selectedValues(picker)).toEqual([]);
  });
}

test('multiple relation keeps choices across pages, errors and retries', async ({page}) => {
  await login(page);
  await page.goto('/admin/models/customers/WyI1MSJd');
  const picker = page.locator('[data-relation-picker]').filter({has: page.locator('select[multiple]')}).first();
  await picker.evaluate(root => {
    root.loadOptions = async ({search, page}) => {
      if (search === 'failure') {
        return new Promise((resolve, reject) => {
          root.failLookup = () => reject(new Error('Fictional lookup failure'));
        });
      }
      await new Promise(resolve => setTimeout(resolve, 50));
      return {items: [{key: 'test-' + page, label: 'Candidate ' + page}], total: 2, has_next: page === 1};
    };
  });
  const trigger = picker.locator('.picker-trigger');
  await trigger.click();
  await picker.getByRole('checkbox', {name: 'Candidate 1', exact: true}).check();
  await expect(picker.locator('details')).toHaveAttribute('open', '');
  await picker.getByRole('button', {name: 'Next', exact: true}).click();
  await picker.getByRole('checkbox', {name: 'Candidate 2', exact: true}).check();
  const selected = await selectedValues(picker);
  expect(selected).toEqual(expect.arrayContaining(['test-1', 'test-2']));
  await picker.getByRole('searchbox').fill('failure');
  await expect(picker.getByRole('checkbox')).toBeDisabled();
  await expect.poll(() => picker.evaluate(root => typeof root.failLookup)).toBe('function');
  await picker.evaluate(root => root.failLookup());
  await expect(picker.locator('.picker-status')).toHaveText('Could not load records. Try again.');
  expect(await selectedValues(picker)).toEqual(selected);
  await picker.evaluate(root => { root.loadOptions = async () => ({items: [], total: 0, has_next: false}); });
  await picker.getByRole('button', {name: 'Retry', exact: true}).click();
  await expect(picker.locator('.picker-status')).toHaveText('No matching records.');
  expect(await selectedValues(picker)).toEqual(selected);
  await picker.getByRole('button', {name: 'Remove: Candidate 1', exact: true}).click();
  expect(await selectedValues(picker)).not.toContain('test-1');
  expect(await selectedValues(picker)).toContain('test-2');
});
