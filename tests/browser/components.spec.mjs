import {test, expect} from '@playwright/test';

test.beforeEach(async ({page}) => {
  await page.goto('/admin/');
  await page.locator('[name=username]').fill('admin');
  await page.locator('[name=password]').fill('browser-test-password');
  await page.getByRole('button', {name:'Sign in', exact:true}).click();
  await page.goto('/admin/models/entries/new');
});

test('repeated enhancement keeps one switch and JSON editor and preserves submitted strings', async ({page}) => {
  const raw = '{"id":9007199254740993,"id":2,"amount":1e-400,"text":"</textarea><script>bad</script>"}';
  await page.evaluate(raw => {
    const host = document.createElement('section'); host.id = 'shared-fields';
    const label = document.createElement('label'); label.id = 'shared-label';
    label.htmlFor = 'shared-boolean'; label.textContent = 'Shared boolean';
    const create = window.QuiteAdmin.createFieldControl;
    host.append(label,
      create({name:'shared_boolean', kind:'boolean', nullable:true}, {id:'shared-boolean', value:'false'}),
      create({name:'shared_json', kind:'json'}, {id:'shared-json', value:raw}));
    document.querySelector('.record-form').append(host);
    for (let i = 0; i < 3; i++) window.quiteAdminEnhanceFields(host);
    host.addEventListener('change', () => { host.dataset.changes = String(Number(host.dataset.changes || 0) + 1); });
  }, raw);
  const host = page.locator('#shared-fields');
  await expect(host.getByRole('switch')).toHaveCount(1);
  await expect(host.locator('.json-editor')).toHaveCount(1);
  await expect(host.getByRole('button', {name:'Format JSON'})).toHaveCount(1);
  await expect(host.locator('script')).toHaveCount(0);
  await host.getByRole('switch').click();
  await expect(host.locator('select')).toHaveValue('true');
  await expect(host).toHaveAttribute('data-changes', '1');
  await host.getByRole('button', {name:'None', exact:true}).click();
  await expect(host.locator('select')).toHaveValue('');
  await expect(host.getByRole('switch')).toBeDisabled();
  await host.getByRole('button', {name:'None', exact:true}).click();
  await expect(host.locator('select')).toHaveValue('true');
  await host.getByRole('button', {name:'Format JSON'}).click();
  const formatted = await host.locator('textarea').inputValue();
  expect(formatted).toContain('9007199254740993');
  expect(formatted).toContain('1e-400');
  expect(formatted.match(/"id"/g)).toHaveLength(2);
  expect(await page.evaluate(() => {
    const data = new FormData(document.querySelector('.record-form'));
    return [data.get('shared_boolean'), data.get('shared_json')];
  })).toEqual(['true', formatted]);
});

test('detached date editors release global listeners and hidden drafts cannot block form submission', async ({page}) => {
  const result = await page.evaluate(() => {
    const counts = {pointerdown:0, resize:0};
    const original = [];
    for (const [target, type] of [[document, 'pointerdown'], [window, 'resize']]) {
      const add = target.addEventListener, remove = target.removeEventListener;
      target.addEventListener = function(name, ...args) { if (name === type) counts[type]++; return add.call(this, name, ...args); };
      target.removeEventListener = function(name, ...args) { if (name === type) counts[type]--; return remove.call(this, name, ...args); };
      original.push(() => { target.addEventListener = add; target.removeEventListener = remove; });
    }
    try {
      for (const kind of ['date', 'datetime', 'time']) {
        const host = document.createElement('div');
        const input = window.QuiteAdmin.createFieldControl({name:kind, kind}, {id:'temporary-' + kind});
        host.append(input); document.body.append(host);
        const cleanup = window.quiteAdminEnhanceFields(host);
        host.querySelector('.date-time-trigger').click();
        const panel = host.querySelector('.date-time-panel');
        const invalid = panel.querySelector('input[type=number]') || panel.querySelector('input[type=time]');
        invalid.value = ''; invalid.required = true;
        host.querySelector('.date-time-trigger').click();
        if ([...panel.querySelectorAll('input,select')].some(node => !node.disabled)) throw new Error('Hidden draft can block submission');
        cleanup(); host.remove();
      }
      return counts;
    } finally { original.forEach(restore => restore()); }
  });
  expect(result).toEqual({pointerdown:0, resize:0});
});

test('shared controls retain exact values and escape markup when serialized by the demo', async ({page}) => {
  const values = ['9007199254740993', '</textarea><script>bad</script>\n"quoted"', '" onfocus="bad()'];
  const result = await page.evaluate(values => {
    const fields = [
      {kind:'integer', name:'identifier'},
      {kind:'json', name:'payload'},
      {kind:'string', name:'choice', choices:[values[2], 'other']},
    ];
    const form = document.createElement('form');
    form.innerHTML = fields.map((field, index) => window.QuiteAdmin.createFieldControl(field,
      {id:'serialized-' + index, value:values[index], enhance:false}).outerHTML).join('');
    return {values:[...new FormData(form).values()], scripts:form.querySelectorAll('script').length,
      handlers:form.querySelectorAll('[onfocus]').length};
  }, values);
  expect(result).toEqual({values, scripts:0, handlers:0});
});
