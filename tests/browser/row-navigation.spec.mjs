import {test, expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

async function login(page, mount) {
  await page.goto(mount+'/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
}

async function clickCenter(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  const bounds=await locator.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.click(bounds.x+bounds.width/2, bounds.y+bounds.height/2);
}

async function clickPadding(page, cell) {
  await cell.scrollIntoViewIfNeeded();
  const bounds=await cell.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.click(bounds.x+3, bounds.y+3);
}

const variants=[
  {kind:'editable', mount:'/rows-name', collection:'entries', first:'name', text:'Alex Smith'},
  {kind:'boolean', mount:'/rows-active', collection:'entries', first:'active', text:'Alex Smith'},
  {kind:'foreign key', mount:'/rows-customer_id', collection:'entries', first:'customer_id', text:'Alex Smith'},
  {kind:'formatted', mount:'/values', collection:'previews', first:'url', text:'javascript:alert(1)'},
];

for (const javaScriptEnabled of [true, false]) {
  test.describe(javaScriptEnabled ? 'with JavaScript' : 'without JavaScript', () => {
    test.use({javaScriptEnabled});
    for (const {kind, mount, collection, first, text} of variants) {
      test(`a ${kind} first cell stretches its record link across text and padding`, async ({page}) => {
        await login(page, mount);
        const listing=mount+'/models/'+collection+'/';
        const openList=()=>page.goto(listing);
        await openList();
        const row=page.locator('tbody .record-row').filter({hasText:text});
        const firstCell=row.locator(`td[data-list-field=${first}]`);
        const recordLink=firstCell.locator('.cell-open');
        await expect(recordLink).toHaveCount(1);
        const target=new URL(await recordLink.getAttribute('href'), page.url());
        const ordinaryText=kind==='formatted'
          ? firstCell.locator('span.value-url')
          : row.locator('td[data-list-field=name] [data-cell-value]');
        await clickCenter(page, ordinaryText);
        await expect(page).toHaveURL(url=>url.pathname===target.pathname);
        await openList();
        await clickPadding(page, firstCell);
        await expect(page).toHaveURL(url=>url.pathname===target.pathname);
        await openList();
        const otherCell=row.locator(`td[data-list-field=${kind==='formatted' ? 'code' : 'count'}]`);
        await clickPadding(page, otherCell);
        await expect(page).toHaveURL(url=>url.pathname===target.pathname);
      });
    }
  });
}

test('row controls keep their own actions above the stretched link', async ({page}) => {
  const mount='/rows-name';
  const listing=mount+'/models/entries/';
  await login(page, mount);
  const create=await page.request.get(listing+'new');
  const token=(await create.text()).match(/name="__csrf" value="([^"]+)"/)[1];
  const name='row-controls-'+randomUUID();
  const customer=await page.request.post(mount+'/models/customers/new', {form:{
    __csrf:token, caption:name,
  }});
  expect(customer.ok()).toBeTruthy();
  const customerPath=new URL(customer.url()).pathname;
  const customerKey=customerPath.split('/').at(-1);
  const saved=await page.request.post(listing+'new', {form:{
    __csrf:token, name, active:'true', count:'10', __relation__to_customers_by_customer_id:customerKey,
    __relation_present__to_customers_by_customer_id:'true',
  }});
  expect(saved.ok()).toBeTruthy();
  const recordPath=new URL(saved.url()).pathname;
  try {
    await page.goto(listing+'?q='+name);
    const row=page.locator('tbody .record-row');

    await clickCenter(page, row.locator('.cell-edit'));
    await expect(page.locator('[data-inline-dialog]')).toBeVisible();
    expect(new URL(page.url()).pathname).toBe(listing);
    await page.locator('[data-inline-cancel]').click();

    const toggle=row.locator('[data-list-switch]');
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await clickCenter(page, toggle);
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(new URL(page.url()).pathname).toBe(listing);

    const selection=row.locator('[data-bulk-key]');
    await clickCenter(page, selection);
    await expect(selection).toBeChecked();
    expect(new URL(page.url()).pathname).toBe(listing);

    const related=row.locator('.relation-value');
    await expect(related).toHaveText(name);
    await clickCenter(page, related);
    await expect(page).toHaveURL(url=>url.pathname===customerPath);
    await expect(page.locator('input[name=caption]')).toHaveValue(name);

    await page.goto(listing+'?q='+name);
    await clickCenter(page, row.locator('.delete-action'));
    await expect(page).toHaveURL(url=>url.pathname===recordPath+'/delete');
    await expect(page.getByRole('heading', {name:'Delete this record?', exact:true})).toBeVisible();
  } finally {
    for (const path of [recordPath, customerPath]) {
      const removed=await page.request.post(path+'/delete', {form:{__csrf:token}});
      expect(removed.ok()).toBeTruthy();
    }
  }
});
