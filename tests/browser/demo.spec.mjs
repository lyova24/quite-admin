import {readFile} from 'node:fs/promises';
import {test,expect} from '@playwright/test';
test.use({baseURL:'http://127.0.0.1:8128'});

test.beforeEach(async ({page})=>{
  await page.goto('/');
  await page.getByLabel('Username',{exact:true}).fill('admin');
  await page.getByLabel('Password',{exact:true}).fill('admin');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.locator('[data-tour-consent]').getByRole('button',{name:'Not now',exact:true}).click();
});

test('demo shares inline controls and records persisted before/after values',async ({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/#/models/products/');
  const row=page.getByRole('row').filter({hasText:'Everyday notebook'});
  await row.getByRole('button',{name:'Edit field: Price',exact:true}).click();
  await page.locator('#inline-value').fill('19.50');
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(row).toContainText('19.50');
  await row.getByRole('switch',{name:'Active',exact:true}).click();
  await expect(row.getByRole('switch')).not.toBeChecked();
  await page.locator('.sidebar').getByRole('link',{name:'Activity history',exact:true}).click();
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
  await page.goto('/#/models/schedules/');
  await page.locator('.record-row-link').first().click();
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

test('the standard table catalog leads to editable date fields and the shared calendar saves a chosen day',async ({page})=>{
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page.locator('.demo-notice,.demo-tour,[data-demo-calendar]')).toHaveCount(0);
  await page.locator('[data-home-view-option="list"]').click();
  await page.locator('[data-home-catalog] [data-table-link="schedules"]').click();
  await page.locator('a.list-create[href="#/models/schedules/new"]').click();
  await expect(page).toHaveURL(/\/schedules\/new$/);
  await expect(page.locator('#field-day')).toBeEditable();
  await expect(page.locator('#field-starts_at-date')).toBeEditable();
  await expect(page.locator('#field-starts_at-time')).toBeEditable();
  await expect(page.locator('#field-reminder_at-time')).toBeEditable();
  await page.locator('#field-day').fill('2026-11-01');
  const date=page.locator('.form-date-control').filter({has:page.locator('#field-day')});
  await date.getByRole('button',{name:'Choose date',exact:true}).click();
  const calendar=page.locator('.form-date-panel:not([hidden])');
  await expect(calendar).toBeVisible();
  await expect(calendar.locator('.date-calendar-grid')).toBeVisible();
  await calendar.getByRole('button',{name:'2026-11-14',exact:true}).click();
  await expect(page.locator('#field-day')).toHaveValue('2026-11-14');
  await page.locator('#field-title').fill('Calendar walkthrough');
  await page.locator('#field-starts_at-date').fill('2026-11-14');
  await page.locator('#field-starts_at-time').fill('15:30:00');
  await page.locator('#field-reminder_at-time').fill('09:45:00');
  await page.getByRole('button',{name:'Create record',exact:true}).click();
  await expect(page).not.toHaveURL(/\/new$/);
  await page.reload();
  await expect(page.locator('#field-day')).toHaveValue('2026-11-14');
  await expect(page.locator('#field-starts_at')).toHaveValue('2026-11-14T15:30:00');
  await expect(page.locator('#field-reminder_at')).toHaveValue('09:45:00');
});

test('Russian schedule fields expose the same editable calendar without demo notices',async ({page})=>{
  await page.goto('/?lang=ru#/models/schedules/new');
  await expect(page.locator('label[for=field-day]')).toContainText('Дата');
  await expect(page.locator('label[id=label-starts_at]')).toContainText('Дата и время');
  await expect(page.locator('label[id=label-reminder_at]')).toContainText('Время');
  await expect(page.locator('#field-day')).toBeEditable();
  await expect(page.locator('#field-starts_at-date')).toBeEditable();
  await expect(page.locator('#field-starts_at-time')).toBeEditable();
  await expect(page.locator('#field-reminder_at-time')).toBeEditable();
  const date=page.locator('.form-date-control').filter({has:page.locator('#field-day')});
  await date.getByRole('button',{name:'Выбрать дату',exact:true}).click();
  await expect(page.locator('.form-date-panel:not([hidden])')).toBeVisible();
  await expect(page.locator('.demo-notice,.demo-tour,[data-demo-calendar]')).toHaveCount(0);
});

test('demo history reuses user filters and inclusive period controls in both views',async ({page})=>{
  await page.locator('.sidebar').getByRole('link',{name:'Activity history',exact:true}).click();
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

test('demo exports more than the visible page through the standard table catalog',async ({page})=>{
  await page.locator('[data-home-view-option="list"]').click();
  await expect(page.locator('[data-group="Catalog"]')).toHaveAttribute('open','');
  await page.locator('[data-home-catalog] [data-table-link="products"]').click();
  await page.locator('.export-panel > summary').click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV download',exact:true}).click();
  const file=await download;
  expect(file.suggestedFilename()).toBe('products.csv');
  const content=await readFile(await file.path(),'utf8');
  expect(content).toContain('Weekly planner');
  expect(content.trim().split('\r\n')).toHaveLength(9);
  await page.reload();
  await expect(page.locator('.record-row-link').first()).toBeVisible();
});

test('demo uses the fixed icon rail across routes, reloads and language changes', async ({page}) => {
  const sidebar = page.locator('#admin-sidebar');
  await expect(sidebar).toHaveCSS('width', '56px');
  await expect(page.locator('[data-sidebar-toggle], [data-sidebar-resizer], .rail-search')).toHaveCount(0);
  await page.goto('/#/models/products/');
  await page.reload();
  await page.goto('/?lang=ru#/models/products/');
  await expect(sidebar).toHaveCSS('width', '56px');
  await expect(sidebar.getByRole('link', {name:'Главная',exact:true})).toBeVisible();
});
