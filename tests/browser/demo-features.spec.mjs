import {readFile} from 'node:fs/promises';
import {test,expect} from '@playwright/test';
test.use({baseURL:'http://127.0.0.1:8128'});

test.beforeEach(async ({page}) => {
  await page.goto('/');
  await page.getByLabel('Username',{exact:true}).fill('admin');
  await page.getByLabel('Password',{exact:true}).fill('admin');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('[data-tour-consent]').getByRole('button',{name:'Not now',exact:true}).click();
});

async function openFirst(page,slug) {
  await page.goto('/#/models/' + slug + '/');
  await page.locator('.record-row-link').first().click();
}

test('standard Home exposes model tables and read-only policies match the server example',async ({page}) => {
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page.locator('.demo-notice,.demo-tour,[data-demo-calendar],[data-tour-card]')).toHaveCount(0);
  await expect(page.locator('a[href="#/showcase"],a[href="#/pages/report"]')).toHaveCount(0);
  await page.locator('[data-home-view-option="list"]').click();
  await expect(page.locator('[data-home-catalog] [data-table-link="regional_prices"]')).toBeVisible();
  await page.goto('/#/models/reference_rates/');
  await expect(page.locator('.list-create,[data-bulk-form],.delete-action,[data-inline-endpoint]')).toHaveCount(0);
  await page.locator('.record-row-link').first().click();
  await expect(page.locator('.record-form input:not([type=hidden]),.record-form select,.record-form button[type=submit]')).toHaveCount(0);
  await openFirst(page,'demo_accounts');
  await expect(page.locator('.record-editor')).not.toContainText('This table uses Python application services.');
  await expect(page.locator('.record-form input:not([type=hidden]),.record-form select,.record-form button[type=submit]')).toHaveCount(0);
  await expect(page.locator('[name=new_password],[name=password_hash]')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('rich displays and record actions work with real exported enum and UUID fields',async ({page}) => {
  await page.goto('/#/models/field_samples/');
  await expect(page.locator('[data-list-field=website] .value-url')).toHaveAttribute('rel','noopener noreferrer');
  await expect(page.locator('[data-list-field=payload] [data-field-display=json]')).toBeVisible();
  await expect(page.locator('[data-list-field=description] .value-details')).toBeVisible();
  await page.locator('.record-row-link').first().click();
  await expect(page.locator('#field-status')).toHaveJSProperty('tagName','SELECT');
  await expect(page.locator('#field-public_id')).toHaveValue(/^[0-9a-f-]{36}$/);
  await expect(page.locator('[name=api_key]')).toHaveCount(0);
  await expect(page.locator('.field-url-preview a[href="https://example.com/issues/DEMO-42"]')).toBeVisible();
  await page.getByRole('button',{name:'Archive sample',exact:true}).click();
  await expect(page.locator('#field-status')).toHaveValue('archived');
  await page.reload();
  await expect(page.locator('#field-status')).toHaveValue('archived');
  await page.getByRole('button',{name:'Publish sample',exact:true}).click();
  await expect(page.locator('#field-status')).toHaveValue('published');
  await page.goto('/#/history?collection=field_samples');
  await expect(page.locator('.activity-journal')).toContainText('Publish sample');
  await expect(page.locator('.activity-journal')).toContainText('Archive sample');
});

test('relationship choices span multiple pages and read-only inverse relations stay visible',async ({page}) => {
  await openFirst(page,'field_samples');
  const picker=page.locator('[data-relation-picker]').filter({has:page.locator('[name="__relation__folder"]')});
  await picker.locator('summary').click();
  await expect(picker.getByRole('radio')).toHaveCount(25);
  await picker.getByRole('button',{name:'Next',exact:true}).click();
  await expect(picker.getByRole('radio')).toHaveCount(11);
  const choice=picker.getByRole('radio').last();
  await choice.check();
  const selected=await picker.locator('select').inputValue();
  const revision=await page.locator('[name=__revision]').inputValue();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('[name=__revision]')).not.toHaveValue(revision);
  await page.reload();
  await expect(picker.locator('select')).toHaveValue(selected);
  await openFirst(page,'folders');
  await expect(page.locator('[name="__relation__samples"]')).toHaveCount(0);
  await expect(page.locator('.is-readonly').filter({hasText:'Samples'})).toBeVisible();
});

test('composite keys use the entered Unicode values and survive a reload',async ({page}) => {
  await page.goto('/#/models/regional_prices/new');
  await page.locator('#field-region').fill('EU');
  await page.locator('#field-sku').fill('Товар/42');
  await page.locator('#field-price').fill('19.75');
  await page.getByRole('button',{name:'Create record',exact:true}).click();
  await expect(page).not.toHaveURL(/\/new$/);
  await page.reload();
  await expect(page.locator('#field-region')).toHaveText('EU');
  await expect(page.locator('#field-sku')).toHaveText('Товар/42');
  await expect(page.locator('#field-price')).toHaveValue('19.75');
});

test('bulk commands confirm selected records and persist a local result',async ({page}) => {
  await page.goto('/#/models/products/');
  const first=page.locator('[data-bulk-key]').first();
  const key=await first.inputValue();
  await first.check();
  await page.locator('[data-bulk-panel] > summary').click();
  await page.locator('#bulk-action').selectOption('action:deactivate');
  await page.getByRole('button',{name:'Continue',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Confirm bulk action',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Confirm action',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Bulk action results',exact:true})).toBeVisible();
  await expect(page.getByRole('status')).toHaveText('Succeeded: 1 · Failed: 0');
  await page.getByRole('link',{name:'Back to records',exact:true}).click();
  const row=page.locator('tr').filter({has:page.locator(`[data-bulk-key][value="${key}"]`)});
  await expect(row.getByRole('switch')).not.toBeChecked();
  await page.reload();
  await expect(row.getByRole('switch')).not.toBeChecked();
});

test('CSV export includes selected related-table fields',async ({page}) => {
  await page.goto('/#/models/products/');
  await page.locator('.export-panel > summary').click();
  for (const box of await page.locator('[name=columns]').all()) await box.uncheck();
  await page.locator('[name=columns][value="name"]').check();
  await page.locator('[name=columns][value="tags.name"]').check();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV download',exact:true}).click();
  const content=await readFile(await (await download).path(),'utf8');
  expect(content).toContain('Popular');
  expect(content).toContain('Weekly planner');
  expect(content).toContain('"Name","Tags · Name"');
  await page.goto('/#/models/products/?q=Everyday');
  await page.locator('.export-panel > summary').click();
  const filteredDownload=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV download',exact:true}).click();
  const filtered=await readFile(await (await filteredDownload).path(),'utf8');
  expect(filtered).toContain('Everyday notebook');
  expect(filtered).not.toContain('Weekly planner');
});

test('bulk deletion supports cancellation before committing selected rows',async ({page}) => {
  await page.goto('/#/models/notes/');
  for (const confirm of [false,true]) {
    await page.locator('[data-bulk-key]').first().check();
    await page.locator('[data-bulk-panel] > summary').click();
    await page.locator('#bulk-action').selectOption('delete');
    await page.getByRole('button',{name:'Continue',exact:true}).click();
    if (!confirm) {
      await page.getByRole('link',{name:'Cancel',exact:true}).click();
      await expect(page.locator('[data-bulk-key]')).toHaveCount(1);
    } else {
      await page.getByRole('button',{name:'Confirm action',exact:true}).click();
      await expect(page.getByRole('status')).toHaveText('Succeeded: 1 · Failed: 0');
      await page.getByRole('link',{name:'Back to records',exact:true}).click();
      await expect(page.getByRole('heading',{name:'No records',exact:true})).toBeVisible();
    }
  }
});

test('export in an older tab reads fresh records and preserves another tab’s edits',async ({page,context}) => {
  await page.goto('/#/models/products/');
  const other=await context.newPage();
  await other.goto('/');
  await other.getByLabel('Username',{exact:true}).fill('admin');
  await other.getByLabel('Password',{exact:true}).fill('admin');
  await other.getByRole('button',{name:'Sign in',exact:true}).click();
  const consent=other.locator('[data-tour-consent]');
  if (await consent.isVisible()) await consent.getByRole('button',{name:'Not now',exact:true}).click();
  await openFirst(other,'products');
  const revision=await other.locator('[name=__revision]').inputValue();
  await other.locator('#field-name').fill('Concurrent notebook');
  await other.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(other.locator('[name=__revision]')).not.toHaveValue(revision);
  await page.locator('.export-panel > summary').click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV download',exact:true}).click();
  const content=await readFile(await (await download).path(),'utf8');
  expect(content).toContain('Concurrent notebook');
  await other.reload();
  await expect(other.locator('#field-name')).toHaveValue('Concurrent notebook');
});

test('a composite relationship searches both raw keys and saves them together',async ({page}) => {
  const seed=await (await page.request.get('/seed.json')).json();
  const source=seed.collections.price_alerts.records[0];
  const relation=seed.collections.price_alerts.relations.find(relation=>relation.name==='regional_price');
  const target=seed.collections[relation.target];
  const choice=target.records.find(row=>!source.links[relation.name].includes(row.key));
  const raw=Object.fromEntries(target.fields.filter(field=>field.primaryKey).map(field=>[field.name,choice.values[field.name]]));
  await page.goto(`/#/models/price_alerts/${source.key}`);
  await expect(page.locator('#field-region,#field-sku')).toHaveCount(0);
  const picker=page.locator('[data-relation-picker]').filter({has:page.locator('[name="__relation__regional_price"]')});
  await picker.locator('summary').click();
  await picker.getByRole('searchbox').fill(JSON.stringify(raw));
  await expect(picker.getByRole('radio')).toHaveCount(1);
  await expect(picker.locator('.picker-results')).toContainText(raw.region);
  await expect(picker.locator('.picker-results')).toContainText(raw.sku);
  await picker.getByRole('radio').check();
  const revision=await page.locator('[name=__revision]').inputValue();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('[name=__revision]')).not.toHaveValue(revision);
  await page.reload();
  await expect(picker.locator('select')).toHaveValue(choice.key);
  await picker.getByRole('button',{name:'Clear selection',exact:true}).click();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('#form-error')).toContainText('A related record is required.');
  await page.reload();
  await expect(picker.locator('select')).toHaveValue(choice.key);
});
