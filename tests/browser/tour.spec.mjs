import {test, expect} from '@playwright/test';

test.use({baseURL: 'http://127.0.0.1:8128'});

async function login(page, language = 'en') {
  await page.goto(language === 'ru' ? '/?lang=ru' : '/');
  await page.locator('[name=username]').fill('admin');
  await page.locator('[name=password]').fill('admin');
  await page.locator('#demo-login button').click();
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  const consent = page.locator('[data-tour-consent]');
  await expect(consent).toBeVisible();
  await expect(consent).toHaveJSProperty('open', true);
  return consent;
}

async function records(page) {
  return page.evaluate(() => {
    for (const value of Object.values(localStorage)) {
      let state;
      try { state = JSON.parse(value); } catch { continue; }
      if (state?.collections) return Object.fromEntries(Object.entries(state.collections)
        .map(([slug, collection]) => [slug, collection.records]));
    }
    throw new Error('The fictional record store was not persisted.');
  });
}

async function progress(page) {
  return page.evaluate(() => Object.fromEntries(Object.entries(sessionStorage)
    .filter(([key]) => key.endsWith(':progress'))));
}

async function choices(page) {
  return page.evaluate(() => Object.fromEntries(Object.entries(localStorage)
    .filter(([key]) => key.endsWith(':choice'))));
}

async function startFromProfile(page, language = 'en') {
  await page.locator('[data-profile-toggle]').click();
  const start = page.locator('[data-tour-start]');
  await expect(start).toHaveAccessibleName(language === 'ru' ? 'Начать тур' : 'Start tour');
  await start.click();
  const consent = page.locator('[data-tour-consent]');
  await expect(consent).toBeVisible();
  return consent;
}

async function expectStep(page, step) {
  const card = page.locator('[data-tour-card]');
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute('data-tour-step', step);
  await expect(page.locator('[data-tour-highlight]')).toHaveCount(1);
  return card;
}

async function next(page, step) {
  await page.locator('[data-tour-next]').click();
  return expectStep(page, step);
}

async function formValues(page) {
  return page.locator('.record-form').evaluate(form => [...new FormData(form).entries()]);
}

async function fitsViewport(page, locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(-1);
  expect(box.y).toBeGreaterThanOrEqual(-1);
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize().height + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('the invitation waits for consent and declining keeps ordinary Home unchanged across reloads', async ({page}) => {
  const writes = [];
  page.on('request', request => { if (request.method() === 'POST') writes.push(request.url()); });
  const consent = await login(page);
  const url = page.url();
  const initial = await records(page);
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  await expect(page.locator('[data-tour-highlight],.qa-tour-target')).toHaveCount(0);
  expect(await progress(page)).toEqual({});
  expect(await choices(page)).toEqual({});
  await expect(page).toHaveURL(url);
  expect(await records(page)).toEqual(initial);
  await consent.getByRole('button', {name: 'Not now', exact: true}).click();
  await expect(consent).toBeHidden();
  expect(Object.keys(await choices(page))).toHaveLength(1);
  expect(await progress(page)).toEqual({});
  await page.reload();
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page.locator('[data-tour-consent]')).toBeHidden();
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  await expect(page.locator('[data-tour-highlight]')).toHaveCount(0);
  await expect(page).toHaveURL(url);
  expect(await records(page)).toEqual(initial);
  expect(writes).toEqual([]);
});

test('the profile can invite again after declining without starting the tour automatically', async ({page}) => {
  const consent = await login(page);
  await consent.getByRole('button', {name: 'Not now', exact: true}).click();
  const url = page.url();
  const initial = await records(page);
  const invitation = await startFromProfile(page);
  await expect(page).toHaveURL(url);
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  await expect(page.locator('[data-tour-highlight]')).toHaveCount(0);
  expect(await records(page)).toEqual(initial);
  expect(await progress(page)).toEqual({});
  await invitation.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  expect(Object.keys(await progress(page))).toHaveLength(1);
  await page.locator('[data-tour-close]').click();
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  await expect(page.locator('[data-tour-highlight]')).toHaveCount(0);
  expect(await progress(page)).toEqual({});
  await page.reload();
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page.locator('[data-tour-consent]')).toBeHidden();
  await expect(page.locator('[data-tour-card]')).toBeHidden();
});

test('Next, Back and Skip navigate only after consent and preserve the active form draft', async ({page}) => {
  const consent = await login(page);
  const initial = await records(page);
  await consent.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  await next(page, 'list');
  await expect(page).toHaveURL(/#\/models\/products\/$/);
  await next(page, 'form');
  await expect(page).toHaveURL(/#\/models\/products\/new$/);
  const original = await formValues(page);
  await next(page, 'relationships');
  await page.locator('[data-tour-back]').click();
  await expectStep(page, 'form');
  expect(await formValues(page)).toEqual(original);
  await page.locator('[data-tour-skip]').click();
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  await expect(page.locator('[data-tour-highlight]')).toHaveCount(0);
  expect(await formValues(page)).toEqual(original);
  expect(await records(page)).toEqual(initial);
  expect(await progress(page)).toEqual({});
  expect(Object.keys(await choices(page))).toHaveLength(1);
  await page.reload();
  await expect(page.locator('.record-form')).toBeVisible();
  await expect(page.locator('[data-tour-consent]')).toBeHidden();
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  await startFromProfile(page);
  await expect(page.locator('[data-tour-card]')).toBeHidden();
});

test('the accepted walkthrough opens real controls without POSTs, record submissions or data changes', async ({page}) => {
  const writes = [];
  page.on('request', request => { if (request.method() === 'POST') writes.push(request.url()); });
  await page.addInitScript(() => {
    window.tourRecordSubmits = [];
    document.addEventListener('submit', event => {
      if (event.target.matches('.record-form')) window.tourRecordSubmits.push(location.href);
    }, true);
  });
  const consent = await login(page);
  const initial = await records(page);
  await consent.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  await next(page, 'list');
  await next(page, 'form');
  const productForm = await formValues(page);
  await next(page, 'relationships');
  await expect(page.locator('[data-relation-picker]').first()).toBeVisible();
  await next(page, 'calendar');
  await expect(page.locator('.form-date-panel:not([hidden])')).toBeVisible();
  await expect(page.locator('.form-date-panel:not([hidden]) .date-calendar-grid')).toBeVisible();
  const scheduleForm = await formValues(page);
  await next(page, 'export');
  await expect(page.locator('.export-panel')).toHaveAttribute('open', '');
  await page.locator('[data-tour-back]').click();
  await expectStep(page, 'calendar');
  expect(await formValues(page)).toEqual(scheduleForm);
  await next(page, 'export');
  await next(page, 'schema');
  await expect(page).toHaveURL(/#\/schema$/);
  const diagram = page.getByRole('group', {name: 'Tables and relationships', exact: true});
  await expect(diagram).toBeVisible();
  await expect(diagram).toHaveAttribute('data-tour-highlight', '');
  expect(await diagram.evaluate(node => node instanceof SVGSVGElement)).toBe(true);
  await expect(diagram.locator('[data-node]').first()).toBeVisible();
  await expect(diagram.locator('[data-edge] .edge-line').first()).toHaveAttribute('d', /^M.+/);
  await expect(page.locator('.schema-toolbar[data-tour-highlight]')).toHaveCount(0);
  await expectSpotlightFitsTarget(page);
  const schemaPaint = await page.evaluate(() => {
    const shade = document.querySelector('[data-tour-shade]');
    const filledCenter = selector => {
      const rect = document.querySelector(selector).getBoundingClientRect();
      const point = new DOMPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
        .matrixTransform(shade.getScreenCTM().inverse());
      return shade.isPointInFill(point);
    };
    return {diagramDimmed: filledCenter('[data-schema-canvas]'), toolbarDimmed: filledCenter('.schema-toolbar')};
  });
  expect(schemaPaint).toEqual({diagramDimmed: false, toolbarDimmed: true});
  await next(page, 'history');
  await expect(page).toHaveURL(/#\/history$/);
  await page.locator('[data-tour-back]').click();
  await expectStep(page, 'schema');
  await next(page, 'history');
  await page.getByRole('button', {name: 'Finish', exact: true}).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page.locator('[data-tour-card],[data-tour-highlight],[data-tour-spotlight]')).toHaveCount(0);
  await expect(page.locator('[data-tour-consent]')).toBeHidden();
  expect(await progress(page)).toEqual({});
  expect(Object.values(await choices(page))).toEqual(['completed']);
  expect(await records(page)).toEqual(initial);
  expect(writes).toEqual([]);
  expect(await page.evaluate(() => window.tourRecordSubmits)).toEqual([]);
  await page.reload();
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.locator('[data-tour-consent]')).toBeHidden();
  await expect(page.locator('[data-tour-card],[data-tour-highlight],[data-tour-spotlight]')).toHaveCount(0);
  expect(await progress(page)).toEqual({});
  expect(Object.values(await choices(page))).toEqual(['completed']);
  expect(await records(page)).toEqual(initial);
  expect(writes).toEqual([]);
  await page.goto('/#/models/products/new');
  expect(await formValues(page)).toEqual(productForm);
});

for (const language of ['en', 'ru']) {
  test(`the invitation and guided calendar fit a mobile viewport in ${language}`, async ({page}) => {
    await page.setViewportSize({width: 390, height: 844});
    const consent = await login(page, language);
    await fitsViewport(page, consent);
    await consent.getByRole('button', {name: language === 'ru' ? 'Начать тур' : 'Start tour', exact: true}).click();
    await expectStep(page, 'home');
    await fitsViewport(page, page.locator('[data-tour-card]'));
    for (const step of ['list', 'form', 'relationships', 'calendar']) {
      await next(page, step);
      await fitsViewport(page, page.locator('[data-tour-card]'));
    }
    await expect(page.locator('.form-date-panel:not([hidden])')).toBeVisible();
    await fitsViewport(page, page.locator('.form-date-panel:not([hidden])'));
    await page.locator('[data-tour-skip]').click();
    await expect(page.locator('[data-tour-card]')).toBeHidden();
    await startFromProfile(page, language);
    await fitsViewport(page, page.locator('[data-tour-consent]'));
  });
}

test('Escape declines the initial invitation and persists that choice without navigating', async ({page}) => {
  const consent = await login(page);
  const url = page.url();
  const initial = await records(page);
  await consent.press('Escape');
  await expect(consent).toBeHidden();
  await expect(page.locator('[data-tour-card],[data-tour-highlight]')).toHaveCount(0);
  expect(await progress(page)).toEqual({});
  expect(Object.keys(await choices(page))).toHaveLength(1);
  await page.reload();
  await expect(page.locator('[data-dashboard]')).toBeVisible();
  await expect(page.locator('[data-tour-consent]')).toBeHidden();
  await expect(page).toHaveURL(url);
  expect(await records(page)).toEqual(initial);
});

test('an edited form blocks tour navigation and skipping keeps the unsaved values', async ({page}) => {
  const consent = await login(page);
  const initial = await records(page);
  await consent.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  await next(page, 'list');
  await next(page, 'form');
  await page.locator('#field-name').fill('Unsaved tour draft');
  const draft = await formValues(page);
  const url = page.url();
  const savedProgress = await progress(page);
  await page.locator('[data-tour-next]').click();
  await expect(page.locator('[data-tour-card]')).toHaveAttribute('data-tour-step', 'form');
  await expect(page.locator('[data-tour-message]')).toHaveText('This form has changes. Save or cancel them before continuing.');
  await expect(page).toHaveURL(url);
  expect(await formValues(page)).toEqual(draft);
  expect(await progress(page)).toEqual(savedProgress);
  await page.locator('[data-tour-skip]').click();
  await expect(page.locator('[data-tour-card]')).toBeHidden();
  expect(await formValues(page)).toEqual(draft);
  expect(await records(page)).toEqual(initial);
  const invitation = await startFromProfile(page);
  await invitation.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expect(invitation.locator('[data-tour-message]')).toHaveText('This form has changes. Save or cancel them before continuing.');
  await expect(invitation).toBeVisible();
  await expect(page).toHaveURL(url);
  expect(await formValues(page)).toEqual(draft);
});

test('reload resumes an accepted active step while another tab requires a fresh invitation', async ({page, context}) => {
  const consent = await login(page);
  await consent.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  await next(page, 'list');
  const state = await progress(page);
  await page.reload();
  await expectStep(page, 'list');
  expect(await progress(page)).toEqual(state);
  const other = await context.newPage();
  await other.goto('/');
  await other.locator('[name=username]').fill('admin');
  await other.locator('[name=password]').fill('admin');
  await other.locator('#demo-login button').click();
  await expect(other.locator('[data-dashboard]')).toBeVisible();
  await expect(other.locator('[data-tour-consent]')).toBeHidden();
  await expect(other.locator('[data-tour-card],[data-tour-highlight]')).toHaveCount(0);
  expect(await progress(other)).toEqual({});
  await startFromProfile(other);
  await expect(other.locator('[data-tour-card]')).toBeHidden();
  await expectStep(page, 'list');
});

async function trackCsp(page) {
  await page.addInitScript(() => {
    window.tourCspViolations = [];
    window.tourCspDetails = [];
    window.tourNativeSelectCsp = [];
    const authoredStyleTargets = new WeakSet();
    new MutationObserver(records => {
      for (const record of records) authoredStyleTargets.add(record.target);
    }).observe(document, {attributes: true, attributeFilter: ['style'], attributeOldValue: true, subtree: true});
    document.addEventListener('securitypolicyviolation', event => {
      const details = {
        effectiveDirective: event.effectiveDirective,
        blockedURI: event.blockedURI,
        sourceFile: event.sourceFile,
        lineNumber: event.lineNumber,
        columnNumber: event.columnNumber,
        sample: event.sample,
        targetTag: event.target?.tagName || null,
        targetId: event.target?.id || null,
        targetStyle: event.target instanceof Element ? event.target.getAttribute('style') : null,
      };
      // Reproduced without application code: WebKit's native SELECT shadow control
      // reports its own text-overflow rule. Authored attributes, including the same
      // rule on SELECT, remain violations; never exempt Document or empty samples.
      if (event.effectiveDirective === 'style-src-attr' && event.blockedURI === 'inline'
        && event.target instanceof HTMLSelectElement && !event.target.hasAttribute('style')
        && !authoredStyleTargets.has(event.target)
        && event.sample === 'text-overflow:inherit') {
        window.tourNativeSelectCsp.push(details);
        return;
      }
      window.tourCspViolations.push(event.effectiveDirective);
      window.tourCspDetails.push(details);
    });
  });
}

async function documentBox(locator) {
  return locator.evaluate(node => {
    const rect = node.getBoundingClientRect();
    return {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height};
  });
}

async function expectSpotlightFitsTarget(page) {
  await expect(page.locator('[data-tour-spotlight]')).toHaveCount(1);
  await expect(page.locator('[data-tour-shade]')).toHaveAttribute('fill-rule', 'evenodd');
  await expect.poll(() => page.evaluate(() => {
    const target = document.querySelector('[data-tour-highlight]').getBoundingClientRect();
    const frame = document.querySelector('[data-tour-frame]');
    if (!frame) return Infinity;
    const left = Math.max(4, target.left - 6), top = Math.max(4, target.top - 6);
    const right = Math.min(innerWidth - 4, target.right + 6);
    const bottom = Math.min(innerHeight - 4, target.bottom + 6);
    const expected = {x: left, y: top, width: right - left, height: bottom - top};
    return Math.max(...Object.entries(expected).map(([name, value]) =>
      Math.abs(Number(frame.getAttribute(name)) - value)));
  })).toBeLessThanOrEqual(1.1);
  const paint = await page.evaluate(() => {
    const frame = document.querySelector('[data-tour-frame]');
    const rect = Object.fromEntries(['x', 'y', 'width', 'height', 'rx'].map(name => [name, Number(frame.getAttribute(name))]));
    const shade = document.querySelector('[data-tour-shade]');
    const filled = (x, y) => shade.isPointInFill(new DOMPoint(x, y).matrixTransform(shade.getScreenCTM().inverse()));
    const outside = [[1, 1], [innerWidth - 1, 1], [1, innerHeight - 1], [innerWidth - 1, innerHeight - 1]]
      .find(([x, y]) => x < rect.x || x > rect.x + rect.width || y < rect.y || y > rect.y + rect.height);
    return {
      rounded: rect.rx > 0,
      targetIsDimmed: filled(rect.x + rect.width / 2, rect.y + rect.height / 2),
      backgroundIsDimmed: outside && filled(...outside),
      shadeOpacity: Number(getComputedStyle(shade).opacity) * Number(getComputedStyle(shade).fillOpacity),
      cardAboveShade: Number(getComputedStyle(document.querySelector('[data-tour-card]')).zIndex)
        > Number(getComputedStyle(document.querySelector('[data-tour-spotlight]')).zIndex),
    };
  });
  expect(paint.rounded).toBe(true);
  expect(paint.targetIsDimmed).toBe(false);
  expect(paint.backgroundIsDimmed).toBe(true);
  expect(paint.shadeOpacity).toBeGreaterThan(0);
  expect(paint.cardAboveShade).toBe(true);
}

test('the rounded spotlight is consent-only, leaves Home layout intact and never intercepts its target', async ({page}) => {
  await trackCsp(page);
  await page.setViewportSize({width: 1512, height: 900});
  const consent = await login(page);
  const initial = await records(page);
  await expect(page.locator('[data-tour-spotlight]')).toHaveCount(0);
  await consent.getByRole('button', {name: 'Not now', exact: true}).click();
  await expect(page.locator('[data-tour-spotlight]')).toHaveCount(0);
  const invitation = await startFromProfile(page);
  const homeSearch = page.locator('[data-dashboard] .home-search');
  const baseline = await documentBox(homeSearch);
  await invitation.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  await expectSpotlightFitsTarget(page);
  expect(await documentBox(homeSearch)).toEqual(baseline);
  await page.locator('[data-tour-highlight]').click();
  const search = page.locator('[data-table-search-dialog]');
  await expect(search).toBeVisible();
  await search.press('Escape');
  await expect(search).toBeHidden();
  await expectStep(page, 'home');
  await page.locator('[data-tour-close]').click();
  await expect(page.locator('[data-tour-spotlight],[data-tour-highlight]')).toHaveCount(0);
  expect(await documentBox(homeSearch)).toEqual(baseline);
  const again = await startFromProfile(page);
  await again.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectSpotlightFitsTarget(page);
  await page.locator('[data-tour-skip]').click();
  await expect(page.locator('[data-tour-spotlight],[data-tour-highlight]')).toHaveCount(0);
  expect(await records(page)).toEqual(initial);
  expect(await page.evaluate(() => window.tourCspViolations)).toEqual([]);
});

test('the spotlight follows real scrolling, responsive resizing and an opened relationship dropdown', async ({page}) => {
  await trackCsp(page);
  await page.setViewportSize({width: 1512, height: 700});
  const consent = await login(page);
  const initial = await records(page);
  await consent.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  await next(page, 'list');
  await next(page, 'form');
  const form = await formValues(page);
  await expectSpotlightFitsTarget(page);
  const documentPosition = await documentBox(page.locator('[data-tour-highlight]'));
  const before = await page.locator('[data-tour-highlight]').boundingBox();
  await page.evaluate(() => scrollBy(0, 60));
  await expect.poll(async () => Math.abs((await page.locator('[data-tour-highlight]').boundingBox()).y - before.y)).toBeGreaterThan(1);
  await expectSpotlightFitsTarget(page);
  expect(await documentBox(page.locator('[data-tour-highlight]'))).toEqual(documentPosition);
  await page.setViewportSize({width: 390, height: 844});
  await expectSpotlightFitsTarget(page);
  await next(page, 'relationships');
  await expectSpotlightFitsTarget(page);
  const picker = page.locator('[data-tour-highlight]');
  await picker.locator('.picker-trigger').click();
  const panel = picker.locator('.picker-panel');
  await expect(panel).toBeVisible();
  await expect(picker.locator('.picker-results input').first()).toBeEnabled();
  await expect.poll(() => panel.evaluate(panel => {
    const rect = panel.getBoundingClientRect();
    const shade = document.querySelector('[data-tour-shade]');
    const point = new DOMPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
      .matrixTransform(shade.getScreenCTM().inverse());
    return shade.isPointInFill(point);
  })).toBe(false);
  await picker.getByRole('searchbox').press('Escape');
  await expectStep(page, 'relationships');
  await expectSpotlightFitsTarget(page);
  expect(await formValues(page)).toEqual(form);
  await page.locator('[data-tour-skip]').click();
  await expect(page.locator('[data-tour-spotlight]')).toHaveCount(0);
  expect(await records(page)).toEqual(initial);
  expect(await page.evaluate(() => window.tourCspViolations)).toEqual([]);
});

test('calendar and export spotlights follow the opened controls while calendar clicks keep values unchanged', async ({page}) => {
  await trackCsp(page);
  await page.setViewportSize({width: 1512, height: 900});
  const writes = [];
  page.on('request', request => { if (request.method() === 'POST') writes.push(request.url()); });
  const consent = await login(page);
  const initial = await records(page);
  await consent.getByRole('button', {name: 'Start tour', exact: true}).click();
  await expectStep(page, 'home');
  for (const step of ['list', 'form', 'relationships', 'calendar']) await next(page, step);
  const calendar = page.locator('.form-date-panel:not([hidden])');
  await expect(calendar).toBeVisible();
  await expectSpotlightFitsTarget(page);
  const values = await formValues(page);
  await calendar.getByRole('button', {name: 'Next month', exact: true}).click();
  await expect(calendar).toBeVisible();
  await expectSpotlightFitsTarget(page);
  expect(await formValues(page)).toEqual(values);
  await page.setViewportSize({width: 390, height: 844});
  await expectSpotlightFitsTarget(page);
  await next(page, 'export');
  await expect(page.locator('.export-panel')).toHaveAttribute('open', '');
  await expect(page.locator('.export-form')).toBeVisible();
  await expectSpotlightFitsTarget(page);
  const mobileExport = await page.evaluate(() => {
    const target = document.querySelector('.export-form').getBoundingClientRect();
    const sidebar = document.querySelector('.sidebar').getBoundingClientRect();
    return {left: target.left, right: target.right, sidebarRight: sidebar.right, viewportWidth: innerWidth};
  });
  expect(mobileExport.left).toBeGreaterThanOrEqual(mobileExport.sidebarRight);
  expect(mobileExport.right).toBeLessThanOrEqual(mobileExport.viewportWidth);
  await expect.poll(() => page.evaluate(() => {
    const target = document.querySelector('[data-tour-highlight]').getBoundingClientRect();
    const card = document.querySelector('[data-tour-card]').getBoundingClientRect();
    return Math.max(0, Math.min(target.right, card.right) - Math.max(target.left, card.left))
      * Math.max(0, Math.min(target.bottom, card.bottom) - Math.max(target.top, card.top));
  })).toBe(0);
  await page.setViewportSize({width: 1512, height: 900});
  await expectSpotlightFitsTarget(page);
  await page.locator('[data-tour-skip]').click();
  await expect(page.locator('[data-tour-spotlight]')).toHaveCount(0);
  expect(await records(page)).toEqual(initial);
  expect(writes).toEqual([]);
  expect(await page.evaluate(() => window.tourCspViolations)).toEqual([]);
});

test('CSP catches attached and detached author styles, including the native SELECT rule text', async ({page}) => {
  await trackCsp(page);
  const consent = await login(page);
  await consent.getByRole('button', {name: 'Not now', exact: true}).click();
  expect(await page.evaluate(() => window.tourCspViolations)).toEqual([]);
  await page.evaluate(() => {
    // Construct in an inert document so WebKit has no pending native-control CSP
    // event when we deliberately author a style attribute on this same SELECT.
    const inert = document.implementation.createHTMLDocument('');
    const select = inert.createElement('select');
    select.id = 'authored-select-style';
    document.body.append(document.adoptNode(select));
    select.setAttribute('style', 'text-overflow:inherit');
    const div = document.createElement('div');
    div.id = 'authored-div-style';
    div.textContent = 'This authored inline style must be blocked.';
    document.body.append(div);
    div.setAttribute('style', 'color:red');
    document.createElement('div').setAttribute('style', 'background:blue');
    const removed = inert.createElement('select');
    removed.id = 'removed-select-style';
    document.body.append(document.adoptNode(removed));
    removed.setAttribute('style', 'text-overflow:inherit');
    removed.removeAttribute('style');
  });
  await expect.poll(() => page.evaluate(() => ({
    count: window.tourCspViolations.length,
    attached: window.tourCspDetails.filter(details => details.targetId).map(details => details.targetId).sort(),
    detached: window.tourCspDetails.filter(details => details.targetTag === null).length,
  }))).toEqual({count: 4, attached: ['authored-div-style', 'authored-select-style', 'removed-select-style'], detached: 1});
  expect(await page.evaluate(() => window.tourCspViolations)).toEqual(['style-src-attr', 'style-src-attr', 'style-src-attr', 'style-src-attr']);
  await expect(page.locator('#authored-div-style')).not.toHaveCSS('color', 'rgb(255, 0, 0)');
});
