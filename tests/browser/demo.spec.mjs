import {readFile} from 'node:fs/promises';
import {test,expect} from '@playwright/test';
test.use({baseURL:'http://127.0.0.1:8128'});

test.beforeEach(async ({page})=>{
  await page.goto('/');
  await page.getByLabel('Username',{exact:true}).fill('admin');
  await page.getByLabel('Password',{exact:true}).fill('admin');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
});

test('demo shares inline controls and records persisted before/after values',async ({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.getByRole('link',{name:'Edit a list cell',exact:true}).click();
  const row=page.getByRole('row').filter({hasText:'Everyday notebook'});
  await row.getByRole('button',{name:'Edit field: Price',exact:true}).click();
  await page.locator('#inline-value').fill('19.50');
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(row).toContainText('19.50');
  await row.getByRole('switch',{name:'Active',exact:true}).click();
  await expect(row.getByRole('switch')).not.toBeChecked();
  await page.getByRole('link',{name:'Activity history',exact:true}).click();
  await page.getByRole('button',{name:'Expand all changes',exact:true}).click();
  await expect(page.locator('.activity-journal')).toContainText('19.50');
  await expect(page.locator('.activity-journal')).toContainText('18.00');
  await page.reload();
  await page.getByRole('button',{name:'Expand all changes',exact:true}).click();
  await expect(page.locator('.activity-journal')).toContainText('19.50');
  await page.getByRole('link',{name:'Table',exact:true}).click();
  await expect(page.getByRole('table',{name:'Activity history',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('demo forms preserve microseconds and show JSON, TEXT and nullable boolean',async ({page})=>{
  await page.getByRole('link',{name:'Dates, time and JSON',exact:true}).click();
  await expect(page.locator('#field-starts_at')).toHaveValue(/\.123456$/);
  await expect(page.locator('#field-reminder_at')).toHaveValue('09:15:00.654321');
  await expect(page.locator('#field-description')).toHaveJSProperty('tagName','TEXTAREA');
  const approved=page.locator('.form-field').filter({has:page.locator('#field-approved')});
  await expect(approved.getByRole('switch')).toBeDisabled();
  await approved.getByRole('button',{name:'None',exact:true}).click();
  await expect(approved.getByRole('switch')).not.toBeChecked();
  await approved.getByRole('switch').click();
  await expect(page.locator('#field-approved')).toHaveValue('true');
  await page.getByRole('button',{name:'Choose date',exact:true}).first().click();
  const picker=page.locator('.form-date-panel:not([hidden])');
  await expect(picker.getByRole('button',{name:'Apply',exact:true})).toHaveCount(0);
  await picker.getByRole('button',{name:'Today',exact:true}).click();
  await expect(picker).toBeHidden();
  await page.getByRole('textbox',{name:'Settings',exact:true}).fill('{"capacity":18}');
  await page.getByRole('button',{name:'Format JSON',exact:true}).click();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('#field-starts_at')).toHaveValue(/\.123456$/);
  await expect(page.locator('#field-settings')).toHaveValue(/"capacity": 18/);
  await expect(page.locator('#field-approved')).toHaveValue('true');
  await expect(approved.getByRole('switch')).toBeChecked();
});

test('demo history reuses user filters and inclusive period controls in both views',async ({page})=>{
  await page.getByRole('link',{name:'Activity history',exact:true}).click();
  await page.getByRole('button',{name:'+ Add filter',exact:true}).click();
  await page.getByRole('button',{name:'Demo Admin ID: admin',exact:true}).click();
  await page.getByRole('button',{name:'Apply filter',exact:true}).click();
  await expect(page).toHaveURL(/subject=admin/);
  await page.locator('[data-history-period] summary').click();
  await page.getByRole('tab',{name:'Date range',exact:true}).click();
  const today=await page.locator('[data-history-period]').getAttribute('data-today');
  await page.locator('#history-date-from').fill(today);
  await page.locator('#history-date-to').fill(today);
  await page.getByRole('button',{name:'Apply period',exact:true}).click();
  await page.getByRole('link',{name:'Table',exact:true}).click();
  await expect(page).toHaveURL(/view=table/);
  await expect(page).toHaveURL(/subject=admin/);
  await expect(page).toHaveURL(/date_mode=range/);
  await expect(page.getByRole('table',{name:'Activity history',exact:true})).toContainText('Demo Admin');
  await expect(page.getByRole('table',{name:'Activity history',exact:true})).not.toContainText('Olivia Chen');
});

test('demo exports more than the visible page and restores initial data on reset',async ({page})=>{
  await page.getByRole('link',{name:'Products',exact:true}).click();
  await page.locator('.export-panel > summary').click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV download',exact:true}).click();
  const file=await download;
  expect(file.suggestedFilename()).toBe('products.csv');
  const content=await readFile(await file.path(),'utf8');
  expect(content).toContain('Weekly planner');
  expect(content.trim().split('\r\n')).toHaveLength(9);
  await page.getByRole('button',{name:'Reset demo',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Quite Admin',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Dates, time and JSON',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Catalog launch',exact:true})).toBeVisible();
});
