import {test, expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test.beforeEach(async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(navigator, 'clipboard', {
    value:{writeText:async value => {window.copiedValue=value;}}, configurable:true,
  }));
  await page.goto('/values/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await page.goto('/values/models/previews/');
});

test('safe links, copy, expanded JSON and multiline values', async ({page}) => {
  const row = page.locator('tbody tr').filter({has:page.locator('a[href="https://example.test/page?q=hello&next=world"]')});
  const url = row.locator('[data-field-display=url]').first();
  await expect(url.locator('a')).toHaveAttribute('rel', 'noopener noreferrer');
  await url.getByRole('button', {name:'Copy value: Url', exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.copiedValue)).toBe('https://example.test/page?q=hello&next=world');
  await expect(url.getByRole('status')).toHaveText('Value copied');
  const short = row.locator('a[href="https://short.example/abc%2F123"]');
  await expect(short).toBeVisible();
  const json = row.locator('[data-field-display=json]');
  await json.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(json.locator('pre')).toBeVisible();
  await expect(json.locator('pre')).toContainText('  "hello": "Привет"');
  await json.getByRole('button', {name:'Copy value: Payload', exact:true}).click();
  expect(JSON.parse(await page.evaluate(()=>window.copiedValue))).toEqual({hello:'Привет', nested:[1,2]});
  const body = row.locator('[data-field-display=multiline]');
  await body.locator('summary').click();
  await expect(body.locator('pre')).toContainText('First line\nSecond line');
  await page.evaluate(() => {navigator.clipboard.writeText = async () => {throw new Error('denied');};});
  await body.getByRole('button', {name:'Copy value: Body', exact:true}).click();
  await expect(body.getByRole('status')).toHaveText('Copy the selected value with Ctrl+C or ⌘C.');
  expect(await page.evaluate(()=>getSelection().toString())).toContain('First line\nSecond line');
  await row.getByRole('link', {name:'Open record', exact:true}).click();
  await expect(page.locator('[data-field-display=json] pre')).toBeVisible();
  await expect(page.locator('input[name=url]')).toHaveCount(0);
});

test('unsafe URL and HTML payloads remain escaped text', async ({page}) => {
  const row = page.locator('tbody tr').filter({hasText:'javascript:alert(1)'});
  await expect(row.locator('[data-field-display=url] a')).toHaveCount(0);
  await expect(row.locator('img')).toHaveCount(0);
  await expect(row.locator('[data-field-display=json] pre')).toContainText('<img src=x onerror=alert(1)>');
  await expect(row.locator('[data-field-display=multiline]')).toContainText('<script>alert(1)</script>');
  await expect(row.locator('script')).toHaveCount(0);
});

test('readable values and expanding remain usable without JavaScript', async ({page}) => {
  // Only authentication is needed; restoring localStorage executes JS in Firefox.
  const {cookies} = await page.context().storageState();
  const context = await page.context().browser().newContext({javaScriptEnabled:false, storageState:{cookies, origins:[]}});
  const plain = await context.newPage();
  await plain.goto(new URL('/values/models/previews/', page.url()).href);
  await expect(plain.locator('[data-copy-value]:visible')).toHaveCount(0);
  const details = plain.locator('[data-field-display=json] details').first();
  await details.locator('summary').click();
  await expect(details.locator('pre')).toBeVisible();
  await expect(plain.locator('a[href="https://short.example/abc%2F123"]')).toBeVisible();
  await context.close();
});

test('service changes refresh URL, JSON and long text after another field is edited', async ({page}) => {
  await page.goto('/editing/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await page.goto('/editing/models/previews/new');
  const title = 'Refresh ' + randomUUID();
  const token = await page.locator('input[name=__csrf]').first().inputValue();
  const response = await page.request.post('/editing/models/previews/new', {form:{__csrf:token,title}});
  expect(response.ok()).toBeTruthy();
  await page.goto('/editing/models/previews/?q='+encodeURIComponent(title));
  await page.getByRole('button', {name:'Edit field: Title', exact:true}).click();
  await page.locator('[data-inline-control] input').fill(title+' updated');
  await page.locator('[data-inline-dialog]').getByRole('button', {name:'Save changes', exact:true}).click();
  await expect(page.locator('a[href="https://example.test/renamed"]')).toBeVisible();
  const json = page.locator('[data-field-display=json]');
  await json.locator('summary').click();
  await expect(json.locator('pre')).toContainText('"renamed": true');
  await json.getByRole('button', {name:'Copy value: Payload',exact:true}).click();
  expect(JSON.parse(await page.evaluate(()=>window.copiedValue))).toEqual({renamed:true});
  const body = page.locator('[data-field-display=multiline]');
  await body.locator('summary').click();
  await expect(body.locator('pre')).toContainText('Updated text\nLong value');
  await page.locator('[data-bulk-all]').check();
  await page.locator('[data-bulk-panel] > summary').click();
  await page.getByRole('button', {name:'Continue',exact:true}).click();
  await page.getByRole('button', {name:'Confirm action',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Succeeded: 1');
});
