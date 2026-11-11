import {test as base, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

const test = base.extend({
  errorGuard: [async ({page}, use) => {
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    await use();
    expect(errors).toEqual([]);
  }, {auto:true}],
});
const listing='/admin/models/entries/';
const dialog=page=>page.locator('#filter-editor');
async function login(page, mount='/admin') {
  await page.goto(mount+'/');
  await page.locator('[name=username]').fill('admin');
  await page.locator('[name=password]').fill('browser-test-password');
  await Promise.all([
    page.waitForURL(url=>url.pathname===mount+'/'),
    page.getByRole('button',{name:'Sign in',exact:true}).click(),
  ]);
}
async function open(page, field) {
  await page.locator('[data-filter-add]').click();
  if(field)await dialog(page).locator(`[data-field="${field}"]`).click();
}
async function apply(page) {
  await Promise.all([
    page.waitForURL(url=>url.searchParams.has('page')),
    dialog(page).getByRole('button',{name:'Apply filter',exact:true}).click(),
  ]);
  await expect(dialog(page)).not.toBeVisible();
}
async function count(page, number) {
  await expect(page.locator('.record-count')).toHaveText(`${number} ${number===1?'record':'records'}`);
}

test.beforeEach(async ({page})=>{await login(page);await page.goto(listing);});

test('partial text, independent repeated conditions and removing a chip', async ({page})=>{
  await open(page,'f.name');
  await expect(dialog(page).locator('#filter-operator')).toHaveValue('icontains');
  await dialog(page).locator('#filter-value-0').fill('Alex');await apply(page);await count(page,3);
  await page.locator('[data-filter-edit]').click();
  await dialog(page).getByRole('button',{name:'+ Add another condition',exact:true}).click();
  await dialog(page).locator('#filter-value-0').fill('Smith');
  await Promise.all([page.waitForURL(url=>url.searchParams.get('f.name.icontains~1')==='Smith'),dialog(page).getByRole('button',{name:'Apply filter',exact:true}).click()]);
  await count(page,1);
  await page.locator('[data-filter-edit="1"]').click();
  await expect(dialog(page).locator('#filter-value-0')).toHaveValue('Smith');
  await Promise.all([page.waitForURL(url=>!url.searchParams.has('f.name.icontains~1')),dialog(page).getByRole('button',{name:'Remove',exact:true}).click()]);
  await count(page,3);
});

test('enum sets and CSV/XLSX downloads include only matching rows', async ({page})=>{
  await open(page,'f.status');await dialog(page).locator('#filter-operator').selectOption('in');
  for(const value of ['pending','paid'])await dialog(page).getByRole('checkbox',{name:value,exact:true}).check();
  await apply(page);await count(page,3);
  for(const format of ['csv','xlsx']) {
    await page.locator('.export-panel summary').click();
    await page.locator('.export-form select[name=export]').selectOption(format);
    const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Download',exact:true}).click();
    const download=await pending;expect(download.suggestedFilename()).toBe('entries.'+format);
    const bytes=await readFile(await download.path());
    if(format==='csv') {
      const text=bytes.toString('utf8');expect(text).toContain('Alex Smith');expect(text).toContain('alex Brown');expect(text).not.toContain('Alex%_! Literal');
    } else expect(bytes.subarray(0,2).toString()).toBe('PK');
    await page.locator('.export-panel summary').click();
    await expect(page.locator('.export-form')).not.toBeVisible();
  }
});

test('empty text, whole-day timestamps and retained validation errors', async ({page})=>{
  await open(page,'f.note');await dialog(page).locator('#filter-operator').selectOption('empty');await apply(page);await count(page,1);
  await page.goto(listing);await open(page,'f.moment');
  await expect(dialog(page).locator('#filter-operator')).toHaveValue('on');
  await dialog(page).locator('#filter-value-0').fill('2026-11-01');await apply(page);await count(page,3);
  await page.goto(listing);await open(page,'f.count');await dialog(page).locator('#filter-operator').selectOption('between');
  await dialog(page).locator('#filter-value-0').fill('20');await dialog(page).locator('#filter-value-1').fill('10');
  await Promise.all([page.waitForResponse(r=>r.request().isNavigationRequest()&&r.status()===422),dialog(page).getByRole('button',{name:'Apply filter',exact:true}).click()]);
  await expect(dialog(page)).toBeVisible();await expect(dialog(page).locator('.field-error')).toContainText('upper bound');
  await expect(dialog(page).locator('#filter-value-1')).toHaveValue('10');
});

test('related-record lookup finds visible IDs and explains searchable labels', async ({page})=>{
  await open(page,'r.to_customers_by_customer_id');
  const loaded=page.waitForResponse(r=>r.url().includes('/options?')&&new URL(r.url()).searchParams.get('q')==='51');
  await dialog(page).getByRole('searchbox',{name:'Search related records',exact:true}).fill('51');
  await loaded;
  const results=dialog(page).locator('.filter-related-results');
  await expect(results).toContainText('Alex Johnson');await expect(results).toContainText('ID: 51');
  await expect(dialog(page).locator('.field-help')).toContainText('Caption');
  await expect(results.getByRole('button')).toHaveCount(1);
  await results.getByRole('button').click();await expect(dialog(page).locator('.filter-preview')).toContainText('51');
  await apply(page);await count(page,2);
});

test('debounced main search pauses while the filter dialog is open', async ({page})=>{
  const navigations=[];page.on('request',r=>{if(r.isNavigationRequest()&&r.url().includes('/models/entries/'))navigations.push(r.url());});
  await page.locator('#search').pressSequentially('Alex',{delay:180});
  expect(navigations).toHaveLength(0);await open(page,'f.name');
  await page.waitForTimeout(1100);expect(navigations).toHaveLength(0);
  await dialog(page).locator('#filter-value-0').fill('Smith');await apply(page);await count(page,1);
  expect(new URL(page.url()).searchParams.get('q')).toBe('Alex');
});

test('inline values, toggles and stale edits preserve the latest record', async ({page})=>{
  const name='inline-'+crypto.randomUUID();
  const create=await page.request.get(listing+'new');
  const token=(await create.text()).match(/name="__csrf" value="([^"]+)"/)[1];
  const saved=await page.request.post(listing+'new',{form:{__csrf:token,name,active:'true',note:'seed',day:'2026-11-01'}});
  expect(saved.ok()).toBeTruthy();await page.goto(listing+'?q='+name);
  const toggle=page.locator('[data-list-switch]');await expect(toggle).toHaveAttribute('aria-checked','true');
  const endpoint=await toggle.locator('xpath=ancestor::*[@data-toggle-endpoint]').getAttribute('data-toggle-endpoint');
  const stale=await (await page.request.get(endpoint)).json();
  await toggle.click();await expect(toggle).toHaveAttribute('aria-checked','false');
  const rejected=await page.request.post(endpoint,{form:{__csrf:stale.csrf,__revision:stale.revision,active:'true'}});
  expect(rejected.status()).toBe(409);await expect(toggle).toHaveAttribute('aria-checked','false');
  await page.locator('[data-list-null]').click();await expect(page.locator('[data-list-toggle-control]')).toHaveAttribute('data-value','null');
  await page.locator('[data-inline-endpoint$="/day"]').click();
  await page.getByRole('button',{name:'Choose date',exact:true}).click();await page.getByRole('button',{name:'2026-11-30',exact:true}).click();
  await expect(page.locator('#inline-value')).toHaveValue('2026-11-30');await page.locator('[data-inline-save]').click();
  await expect(page.locator('[data-inline-dialog]')).not.toBeVisible();
  await expect(page.locator('td[data-list-field=day]')).toContainText('2026-11-30');
});

test('cell values open the record while only the pencil opens inline editing', async ({page})=>{
  const cell=page.locator('td[data-list-field=day]').first();
  const text=await cell.locator('[data-cell-value]').textContent();
  await cell.locator('.cell-edit').click();
  await expect(page.locator('[data-inline-dialog]')).toBeVisible();
  await page.locator('[data-inline-cancel]').click();
  const bounds=await cell.locator('[data-cell-value]').boundingBox();
  await page.mouse.click(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
  await expect(page).toHaveURL(/\/admin\/models\/entries\/[^/]+$/);
  await expect(page.locator('input[name=day]')).toHaveValue(text);
});

test('calendar uses the theme and remains usable on a narrow screen', async ({page})=>{
  await login(page,'/dark');await page.goto('/dark/models/entries/');await page.setViewportSize({width:390,height:844});
  await open(page,'f.moment');await dialog(page).locator('#filter-value-0').fill('2026-11-01');
  await dialog(page).getByRole('button',{name:'Choose date',exact:true}).click();
  await expect(dialog(page)).toHaveCSS('background-color','rgb(23, 32, 51)');
  await dialog(page).getByRole('button',{name:'2026-11-30',exact:true}).click();
  await dialog(page).locator('.date-time-panel').getByRole('button',{name:'Apply',exact:true}).click();
  await expect(dialog(page).locator('#filter-value-0')).toHaveValue('2026-11-30');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  expect(await dialog(page).evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(false);
});

test('search and filtering still work without JavaScript', async ({browser})=>{
  const context=await browser.newContext({javaScriptEnabled:false});const page=await context.newPage();
  await login(page);await page.goto(listing);await page.locator('.filter-disclosure > summary').click();
  await page.locator('.filter-field').filter({has:page.locator('summary',{hasText:'Name'})}).locator('summary').click();
  await page.locator('[name="f.name.icontains"]').fill('Alex');await page.getByRole('button',{name:'Apply filters',exact:true}).click();
  await count(page,3);await context.close();
});


test('foreign-key labels link to the related record above the row target', async ({page})=>{
  const link=page.locator('td[data-list-field=customer_id] .relation-value').first();
  await expect(link).toHaveText('Alex Johnson');
  const row=link.locator('xpath=ancestor::tr');
  const primary=row.locator('.cell-primary [data-cell-value]');
  const colors=await page.evaluate(()=>{
    const root=getComputedStyle(document.documentElement);
    return {text:root.getPropertyValue('--text').trim(),accent:root.getPropertyValue('--accent').trim(),hover:root.getPropertyValue('--hover').trim()};
  });
  const rgb=hex=>`rgb(${hex.slice(1).match(/../g).map(value=>parseInt(value,16)).join(', ')})`;
  await expect(link).toHaveCSS('color',rgb(colors.text));
  await primary.hover({force:true});
  await expect(row).toHaveCSS('background-color',rgb(colors.hover));
  await expect(primary).toHaveCSS('color',rgb(colors.text));
  await expect(link).toHaveCSS('color',rgb(colors.text));
  await link.hover();
  await expect(link).toHaveCSS('color',rgb(colors.accent));
  await expect(primary).toHaveCSS('color',rgb(colors.text));
  await page.getByRole('heading',{name:'Entries',exact:true}).hover();
  await expect(link).toHaveCSS('color',rgb(colors.text));
  await link.click();
  await expect(page).toHaveURL(/\/admin\/models\/customers\/[^/]+$/);
  await expect(page.locator('input[name=caption]')).toHaveValue('Alex Johnson');
});

test('related-record return links preserve the source listing after inline refresh', async ({page})=>{
  const prefix='return-'+crypto.randomUUID();
  const created=[];
  try {
    const createCustomer=await page.request.get('/admin/models/customers/new');
    const customerToken=(await createCustomer.text()).match(/name="__csrf" value="([^"]+)"/)[1];
    const customer=await page.request.post('/admin/models/customers/new',{
      form:{__csrf:customerToken,caption:prefix},
    });
    expect(customer.ok()).toBeTruthy();
    const customerPath=new URL(customer.url()).pathname;
    created.push(customerPath);
    const customerKey=customerPath.split('/').at(-1);
    const create=await page.request.get(listing+'new');
    const token=(await create.text()).match(/name="__csrf" value="([^"]+)"/)[1];
    for(const suffix of ['a','b','c']){
      const response=await page.request.post(listing+'new',{form:{
        __csrf:token,name:prefix+'-'+suffix,active:'true',day:'2026-11-01',
        __relation__to_customers_by_customer_id:customerKey,
        __relation_present__to_customers_by_customer_id:'true',
      }});
      expect(response.ok()).toBeTruthy();
      created.push(new URL(response.url()).pathname);
    }
    const source=listing+'?'+new URLSearchParams({q:prefix,'f.name.icontains':prefix,
      sort:'name',direction:'desc',page:'2',limit:'1'});
    const absolute=new URL(source,page.url()).href;
    await page.goto(source);
    const related=page.locator('tbody .relation-value');
    const expectOrigin=async()=>{
      const target=new URL(await related.getAttribute('href'),page.url());
      expect(target.pathname).toBe(customerPath);
      expect(target.searchParams.get('return_to')).toBe(source);
    };
    await expectOrigin();
    await related.click();
    await expect(page.locator('.back-link')).toHaveAttribute('href',source);
    await page.locator('.back-link').click();
    await expect(page).toHaveURL(absolute);
    await related.click();
    await page.locator('.form-footer a').click();
    await expect(page).toHaveURL(absolute);
    await related.click();
    await page.locator('.breadcrumbs a').filter({hasText:'Entries'}).click();
    await expect(page).toHaveURL(absolute);

    const toggle=page.locator('[data-list-switch]');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked','false');
    await expectOrigin();
    await page.locator('[data-inline-endpoint$="/day"]').click();
    await page.locator('#inline-value').fill('2026-11-02');
    await page.locator('[data-inline-save]').click();
    await expect(page.locator('[data-inline-dialog]')).not.toBeVisible();
    await expectOrigin();
    await related.click();
    await page.locator('.back-link').click();
    await expect(page).toHaveURL(absolute);
    await expect(page.locator('td[data-list-field=day]')).toContainText('2026-11-02');
  } finally {
    for(const path of created.reverse()){
      const confirmation=await page.request.get(path+'/delete');
      const token=(await confirmation.text()).match(/name="__csrf" value="([^"]+)"/)[1];
      const deleted=await page.request.post(path+'/delete',{form:{__csrf:token}});
      expect(deleted.ok()).toBeTruthy();
    }
  }
});


test('cursor column headers sort timestamps, traverse pages and reset boundaries', async ({page})=>{
  await login(page,'/cursor');
  const prefix='cursor-'+crypto.randomUUID();
  const records=[
    {suffix:'earliest',moment:'2031-04-10T08:00:00',count:'40'},
    {suffix:'latest',moment:'2031-04-12T08:00:00',count:'30'},
    {suffix:'tie-first',moment:'2031-04-11T08:00:00',count:'20'},
    {suffix:'tie-second',moment:'2031-04-11T08:00:00',count:'10'},
  ];
  const create=await page.request.get('/cursor/models/entries/new');
  const token=(await create.text()).match(/name="__csrf" value="([^"]+)"/)[1];
  for(const {suffix,moment,count} of records) {
    const saved=await page.request.post('/cursor/models/entries/new',{
      form:{__csrf:token,name:prefix+'-'+suffix,moment,count,note:'cursor fixture'},
    });
    expect(saved.ok()).toBeTruthy();
  }
  await page.goto('/cursor/models/entries/?limit=1&q='+prefix);
  const name=page.locator('td[data-list-field=name] [data-cell-value]');
  const header=page.getByRole('columnheader').filter({hasText:'Moment'});
  await header.getByRole('link').click();
  await expect(header).toHaveAttribute('aria-sort','ascending');
  await expect(name).toHaveText(prefix+'-earliest');
  await header.getByRole('link').click();
  await expect(header).toHaveAttribute('aria-sort','descending');
  await expect(name).toHaveText(prefix+'-latest');
  for(const suffix of ['tie-first','tie-second','earliest']) {
    await page.getByRole('link',{name:'Next →',exact:true}).click();
    await expect(page).toHaveURL(/after=/);
    await expect(name).toHaveText(prefix+'-'+suffix);
  }
  await expect(page.getByRole('link',{name:'Next →',exact:true})).toHaveCount(0);
  for(const suffix of ['tie-second','tie-first']) {
    await page.getByRole('link',{name:'← Previous',exact:true}).click();
    await expect(page).toHaveURL(/before=/);
    await expect(name).toHaveText(prefix+'-'+suffix);
  }
  await page.getByRole('columnheader').filter({hasText:'Count'}).getByRole('link').click();
  expect(new URL(page.url()).searchParams.has('before')).toBe(false);
  expect(new URL(page.url()).searchParams.has('after')).toBe(false);
  expect(new URL(page.url()).searchParams.get('q')).toBe(prefix);
  await expect(page.getByRole('columnheader').filter({hasText:'Count'})).toHaveAttribute('aria-sort','ascending');
  await expect(name).toHaveText(prefix+'-tie-second');
  await page.getByRole('link',{name:'Next →',exact:true}).click();
  await expect(page).toHaveURL(/after=/);
  await expect(name).toHaveText(prefix+'-tie-first');
  await header.getByRole('link').click();
  expect(new URL(page.url()).searchParams.has('after')).toBe(false);
  expect(new URL(page.url()).searchParams.has('before')).toBe(false);
  await expect(header).toHaveAttribute('aria-sort','ascending');
  await expect(name).toHaveText(prefix+'-earliest');
});


test('form relation picker displays relation_label and searches label or exact ID', async ({page})=>{
  await page.goto(listing+'new');
  const picker=page.locator('[data-relation-picker]').filter({has:page.locator('[name="__relation__to_customers_by_customer_id"]')});
  const search=picker.getByRole('searchbox');
  await picker.locator('summary').click();
  await search.fill('Johnson');
  await expect(picker.locator('.picker-results .picker-option')).toHaveCount(1);
  await expect(picker.locator('.picker-results')).toContainText('Alex Johnson');
  await search.fill('52');
  await expect(picker.locator('.picker-results')).toContainText('Maria Jones');
  await expect(picker.locator('.picker-results .picker-option')).toHaveCount(1);
  await picker.locator('.picker-results input').check();
  await expect(picker.locator('.picker-selection')).toContainText('Maria Jones');
  await expect(picker.locator('select')).toHaveValue('WyI1MiJd');
});
