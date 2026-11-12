import {test, expect} from '@playwright/test';

async function openForm(page) {
  await page.goto('/admin/');
  await page.getByLabel('Username', {exact:true}).fill('admin');
  await page.getByLabel('Password', {exact:true}).fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await page.goto('/admin/models/entries/new');
}

test('form heading, fields and footer stay aligned at phone, laptop and wide desktop widths', async ({page}) => {
  await openForm(page);
  for (const width of [390, 1512, 2560]) {
    await page.setViewportSize({width, height:1000});
    const geometry = await page.evaluate(() => {
      const box = selector => {
        const {x, width, right} = document.querySelector(selector).getBoundingClientRect();
        return {x, width, right};
      };
      return {editor:box('.record-editor'), heading:box('.record-heading'),
        form:box('.record-form'), footer:box('.form-footer'), content:box('.content'),
        overflow:document.documentElement.scrollWidth > innerWidth};
    });
    expect(geometry.overflow).toBe(false);
    expect(Math.abs(geometry.heading.x - geometry.form.x)).toBeLessThan(1);
    expect(Math.abs(geometry.heading.right - geometry.form.right)).toBeLessThan(1);
    expect(Math.abs(geometry.footer.x - geometry.form.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.footer.right - geometry.form.right)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.editor.x + geometry.editor.width / 2
      - geometry.content.x - geometry.content.width / 2)).toBeLessThan(1);
    await expect(page.locator('#field-count')).toHaveAttribute('placeholder', 'e.g. 42');
    await expect(page.locator('#field-count')).toHaveValue('');
  }
  await page.locator('label[for="field-name"]').evaluate(node => {
    node.firstChild.textContent = 'A very long field label '.repeat(20);
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('record forms retain native relationship selection without JavaScript', async ({browser, baseURL}) => {
  const context = await browser.newContext({javaScriptEnabled:false, baseURL});
  try {
    const page = await context.newPage();
    await openForm(page);
    const select = page.locator('[name="__relation__to_customers_by_customer_id"]');
    await expect(select).toBeVisible();
    await select.selectOption({label:'Maria Jones'});
    await expect(select).toHaveValue('WyI1MiJd');
    const describedBy = await select.getAttribute('aria-describedby');
    await expect(page.locator('#' + describedBy.trim())).toHaveText('Select one related record.');
  } finally {
    await context.close();
  }
});
