import {test, expect} from '@playwright/test';

async function login(page, mount = '/admin') {
  await page.goto(mount + '/login');
  await page.getByLabel('Username').fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await expect(page).toHaveURL(new RegExp(mount + '/$'));
}
const width = page => page.locator('.sidebar').evaluate(element => element.getBoundingClientRect().width);

test('sidebar drag and keyboard resizing persist per mount, and double-click restores the default', async ({page}) => {
  await login(page);
  const initial = await width(page);
  const handle = page.getByRole('separator', {name:'Resize sidebar'});
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 70);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 100, box.y + 70);
  await page.mouse.up();
  const resized = await width(page);
  expect(resized).toBeCloseTo(initial + 100, 0);
  await page.reload();
  expect(await width(page)).toBeCloseTo(resized, 0);
  await page.goto('/admin/models/entries/');
  expect(await width(page)).toBeCloseTo(resized, 0);
  await handle.press('Home');
  expect(await width(page)).toBeCloseTo(160, 0);
  await handle.press('ArrowRight');
  expect(await width(page)).toBeCloseTo(176, 0);
  await handle.press('End');
  expect(await width(page)).toBeCloseTo(512, 0);
  await handle.dblclick();
  expect(await width(page)).toBeCloseTo(initial, 0);
  await handle.press('Shift+ArrowRight');
  await login(page, '/dark');
  expect(await width(page)).toBeCloseTo(initial, 0);
});

test('long navigation labels wrap without horizontal scroll at desktop and mobile widths', async ({page}) => {
  await login(page);
  await page.evaluate(() => {
    document.querySelectorAll('.sidebar .nav-link').forEach(link => { link.textContent = 'long_table_name_'.repeat(15); });
    const group = document.querySelector('.nav-group');
    group.open = true;
    group.querySelector('summary').firstChild.textContent = 'LongGroupName'.repeat(20);
  });
  for (const size of [1280, 800, 390]) {
    await page.setViewportSize({width:size, height:900});
    const fits = await page.locator('.sidebar').evaluate(sidebar => ({
      sidebar: sidebar.scrollWidth <= sidebar.clientWidth,
      page: document.documentElement.scrollWidth <= innerWidth,
      links: [...sidebar.querySelectorAll('a, summary')].every(element => {
        const bounds = element.getBoundingClientRect(), parent = sidebar.getBoundingClientRect();
        return bounds.right <= parent.right + 1 && element.scrollWidth <= element.clientWidth + 1;
      }),
    }));
    expect(fits).toEqual({sidebar:true, page:true, links:true});
  }
  await expect(page.getByRole('separator', {name:'Resize sidebar'})).toBeHidden();
});

test('disabled storage still allows resizing and Escape cancels a drag', async ({page}) => {
  await page.addInitScript(() => Object.defineProperty(window, 'localStorage', {
    get() { throw new Error('Storage disabled'); },
  }));
  await login(page);
  const handle = page.getByRole('separator', {name:'Resize sidebar'});
  const initial = await width(page);
  await handle.press('ArrowRight');
  expect(await width(page)).toBeCloseTo(initial + 16, 0);
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 70);
  await page.mouse.down();
  await page.mouse.move(box.x + 100, box.y + 70);
  await handle.press('Escape');
  await page.mouse.up();
  expect(await width(page)).toBeCloseTo(initial + 16, 0);
  await page.reload();
  expect(await width(page)).toBeCloseTo(initial, 0);
});

test('the resize handle stays reachable after scrolling a long navigation', async ({page}) => {
  await login(page);
  await page.evaluate(() => {
    const nav = document.querySelector('.sidebar nav');
    for (let index = 0; index < 60; index++) {
      const link = document.createElement('a'); link.className = 'nav-link';
      link.href = '#'; link.textContent = 'Table ' + index; nav.append(link);
    }
    const sidebar = document.querySelector('.sidebar'); sidebar.scrollTop = sidebar.scrollHeight;
  });
  const handle = page.getByRole('separator', {name:'Resize sidebar'});
  await expect(handle).toBeInViewport();
  const before = await width(page);
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, 100);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 50, 100);
  await page.mouse.up();
  expect(await width(page)).toBeCloseTo(before + 50, 0);
});
