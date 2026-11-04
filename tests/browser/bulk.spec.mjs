import {test, expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test('page selection, confirmation, custom action and deletion', async ({page}) => {
  await page.goto('/admin/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  const name = 'Bulk ' + randomUUID();
  await page.goto('/admin/models/entries/new');
  const token = await page.locator('input[name=__csrf]').first().inputValue();
  for (let index=0; index<2; index++) {
    const response = await page.request.post('/admin/models/entries/new', {
      form:{__csrf:token, name:name+' '+index, count:'7'},
    });
    expect(response.ok()).toBeTruthy();
  }
  const listing = '/admin/models/entries/?q=' + encodeURIComponent(name);
  await page.goto(listing);
  const toolbar = page.locator('[data-bulk-form]');
  await expect(toolbar.getByRole('button', {name:'Continue', exact:true})).toBeDisabled();
  const boxes = page.locator('[data-bulk-key]');
  await expect(boxes).toHaveCount(2);
  await boxes.first().check();
  await expect(page.locator('[data-bulk-all]')).toHaveJSProperty('indeterminate', true);
  await page.locator('[data-bulk-all]').check();
  await expect(page.locator('[data-bulk-count]')).toHaveText('Selected records: 2');
  await toolbar.locator('select').selectOption('action:reset');
  await page.route(/\/models\/entries\/actions\/bulk(?:\?|$)/, async route => {
    const response = await route.fetch();
    await new Promise(resolve=>setTimeout(resolve,1100));
    await route.fulfill({response});
  }, {times:1});
  await page.getByRole('textbox', {name:'Search records', exact:true}).fill('Pending search must not interrupt selection');
  await toolbar.getByRole('button', {name:'Continue', exact:true}).click();
  await expect(page.getByRole('heading', {name:'Confirm bulk action', exact:true})).toBeVisible();
  await expect(page.locator('.bulk-confirmation li')).toHaveCount(2);
  await page.getByRole('link', {name:'Cancel', exact:true}).click();
  await expect(page).toHaveURL(url=>url.searchParams.get('q')===name);
  await page.goto(listing);
  await expect(page.locator('[data-list-field=count]')).toHaveText(['7','7']);
  await page.locator('[data-bulk-all]').check();
  await page.locator('[data-bulk-form] select').selectOption('action:reset');
  await page.getByRole('button', {name:'Continue', exact:true}).click();
  await page.getByRole('button', {name:'Confirm action', exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Succeeded: 2');
  await page.goto(listing);
  await expect(page.locator('[data-list-field=count]')).toHaveText(['0','0']);
  await page.locator('[data-bulk-all]').check();
  await page.getByRole('button', {name:'Continue', exact:true}).click();
  await page.getByRole('button', {name:'Confirm action', exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Succeeded: 2');
  await page.goto(listing);
  await expect(page.locator('[data-bulk-form]')).toHaveCount(0);
});
