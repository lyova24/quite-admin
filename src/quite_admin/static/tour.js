(function () {
  'use strict';
  // Example-only walkthrough. No record values or identifiers enter storage.
  const memory = new Map();
  let current;
  const storage = (kind, key, value) => {
    const cacheKey = kind + ':' + key;
    if (value !== undefined) {
      memory.set(cacheKey, value);
      try {
        if (value === null) window[kind].removeItem(key);
        else window[kind].setItem(key, value);
      } catch (_) { /* Consent still works when browser storage is unavailable. */ }
      return value;
    }
    if (memory.has(cacheKey)) return memory.get(cacheKey);
    try { return window[kind].getItem(key); } catch (_) { return null; }
  };
  const node = (tag, className, text) => {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text) result.textContent = text;
    return result;
  };
  function spotlight(target, card) {
    const svgNode = (tag, attributes) => {
      const result = document.createElementNS('http://www.w3.org/2000/svg', tag);
      for (const [name, value] of Object.entries(attributes)) result.setAttribute(name, value);
      return result;
    };
    const overlay = svgNode('svg', {class: 'qa-tour-spotlight', 'data-tour-spotlight': '',
      'aria-hidden': 'true', focusable: 'false'});
    const shade = svgNode('path', {class: 'qa-tour-shade', 'data-tour-shade': '', 'fill-rule': 'evenodd'});
    const frame = svgNode('rect', {class: 'qa-tour-frame', 'data-tour-frame': ''});
    overlay.append(shade, frame); document.body.append(overlay);
    const abort = new AbortController();
    const listen = (element, event, callback, capture = false) =>
      element.addEventListener(event, callback, {capture, passive: true, signal: abort.signal});
    let animation;
    const round = value => Math.round(value * 2) / 2;
    function update() {
      animation = null;
      const viewport = overlay.getBoundingClientRect();
      const bounds = target.getBoundingClientRect();
      let {left, top, right, bottom} = bounds;
      // An open picker may extend beyond the selector's normal flow box.
      for (const popup of target.querySelectorAll('.picker-menu[open] .picker-panel')) {
        const box = popup.getBoundingClientRect();
        if (box.width && box.height) {
          left = Math.min(left, box.left); top = Math.min(top, box.top);
          right = Math.max(right, box.right); bottom = Math.max(bottom, box.bottom);
        }
      }
      const width = viewport.width, height = viewport.height;
      const visible = target.isConnected && bounds.width > 0 && bounds.height > 0
        && right > 4 && bottom > 4 && left < width - 4 && top < height - 4;
      if (!visible) {
        frame.setAttribute('visibility', 'hidden');
        // Keep the rest of the interface usable when the user scrolls the target away.
        shade.setAttribute('d', '');
        return;
      }
      frame.removeAttribute('visibility');
      const x = round(Math.max(4, left - 6)), y = round(Math.max(4, top - 6));
      const w = round(Math.min(width - 4, right + 6) - x);
      const h = round(Math.min(height - 4, bottom + 6) - y);
      const radius = Math.min(w / 2, h / 2, Math.max(8, (parseFloat(getComputedStyle(target).borderTopLeftRadius) || 0) + 6));
      // SVG attributes keep geometry out of style-src, preserving the strict CSP.
      overlay.setAttribute('viewBox', `0 0 ${width} ${height}`);
      for (const [name, value] of Object.entries({x, y, width: w, height: h, rx: radius})) frame.setAttribute(name, value);
      shade.setAttribute('d', `M0 0H${width}V${height}H0Z M${x + radius} ${y}H${x + w - radius}A${radius} ${radius} 0 0 1 ${x + w} ${y + radius}V${y + h - radius}A${radius} ${radius} 0 0 1 ${x + w - radius} ${y + h}H${x + radius}A${radius} ${radius} 0 0 1 ${x} ${y + h - radius}V${y + radius}A${radius} ${radius} 0 0 1 ${x + radius} ${y}Z`);
      // Prefer an unobstructed corner, with only top/bottom choices on narrow screens.
      const margin = width <= 480 ? 8 : 16;
      const cardWidth = card.offsetWidth, cardHeight = card.offsetHeight;
      const placements = ['bottom-end', 'top-end', ...(width > 480 ? ['bottom-start', 'top-start'] : [])];
      let placement = placements[0], score = Infinity;
      for (const candidate of placements) {
        const cardX = candidate.endsWith('start') ? margin : width - margin - cardWidth;
        const cardY = candidate.startsWith('top') ? margin : height - margin - cardHeight;
        const overlap = Math.max(0, Math.min(x + w + 12, cardX + cardWidth) - Math.max(x - 12, cardX))
          * Math.max(0, Math.min(y + h + 12, cardY + cardHeight) - Math.max(y - 12, cardY));
        if (overlap < score) { score = overlap; placement = candidate; }
      }
      card.dataset.tourPlacement = placement;
    }
    const schedule = () => { if (animation == null) animation = requestAnimationFrame(update); };
    const resize = new ResizeObserver(schedule);
    resize.observe(target); resize.observe(card); resize.observe(document.documentElement);
    const mutation = new MutationObserver(schedule);
    mutation.observe(target, {subtree: true, childList: true, attributes: true, attributeFilter: ['open', 'hidden', 'class']});
    listen(document, 'scroll', schedule, true); listen(window, 'resize', schedule);
    if (window.visualViewport) {
      listen(window.visualViewport, 'resize', schedule); listen(window.visualViewport, 'scroll', schedule);
    }
    update();
    return () => {
      abort.abort(); resize.disconnect(); mutation.disconnect();
      if (animation != null) cancelAnimationFrame(animation);
      overlay.remove();
    };
  }
  function init(root = document) {
    current?.dispose();
    current = null;
    const marker = root.querySelector('[data-admin-tour]');
    if (!marker) return;
    let config;
    try { config = JSON.parse(marker.dataset.config); } catch (_) { return; }
    if (!config.storageKey || !Array.isArray(config.steps) || !config.steps.length) return;
    const home = new URL(config.homeUrl, location.href);
    const allowed = value => {
      try {
        const url = new URL(value, location.href);
        return url.origin === location.origin && (home.hash
          ? url.pathname === home.pathname && url.hash.startsWith('#/')
          : url.pathname.startsWith(home.pathname.endsWith('/') ? home.pathname : home.pathname + '/'));
      } catch (_) { return false; }
    };
    if (home.origin !== location.origin || config.steps.some(step => !allowed(step.url))) return;
    const route = value => {
      const url = new URL(value, location.href);
      return home.hash ? url.pathname + (url.hash || '#/').split('?')[0].replace(/\/$/, '')
        : url.pathname.replace(/\/$/, '');
    };
    const sameRoute = value => route(value) === route(location.href);
    const ru = config.language === 'ru';
    const labels = ru ? {
      title: 'Познакомиться с админкой?',
      invitation: 'Короткий тур покажет таблицы, формы, связи, календарь, экспорт, схему и историю. Он будет переходить между страницами, не заполняя и не сохраняя записи.',
      start: 'Начать тур', later: 'Не сейчас', back: 'Назад', next: 'Далее', skip: 'Пропустить тур',
      close: 'Закрыть', finish: 'Завершить', progress: 'Шаг', of: 'из',
      dirty: 'В форме есть изменения. Сохраните или отмените их перед переходом.',
      unavailable: 'Этот элемент сейчас недоступен. Можно перейти к следующему шагу.',
    } : {
      title: 'Take a tour of the admin?',
      invitation: 'A short tour covers tables, forms, relationships, the calendar, export, schema and history. It navigates between pages without filling in or saving records.',
      start: 'Start tour', later: 'Not now', back: 'Back', next: 'Next', skip: 'Skip tour',
      close: 'Close', finish: 'Finish', progress: 'Step', of: 'of',
      dirty: 'This form has changes. Save or cancel them before continuing.',
      unavailable: 'This element is currently unavailable. You can continue to the next step.',
    };
    const choiceKey = config.storageKey + ':choice', progressKey = config.storageKey + ':progress';
    const abort = new AbortController();
    const on = (target, event, callback) => target.addEventListener(event, callback, {signal: abort.signal});
    let dialog, card, targetCleanup, timer, observer, disposed = false, index = 0;
    const forms = new Map();
    const formValue = form => JSON.stringify(Array.from(new FormData(form), ([name, value]) =>
      [name, typeof value === 'string' ? value : value.name]));
    root.querySelectorAll('.record-form').forEach(form => forms.set(form, formValue(form)));
    const dirty = () => Array.from(forms).some(([form, baseline]) => form.isConnected && formValue(form) !== baseline);
    const clearStep = () => {
      clearTimeout(timer); observer?.disconnect(); observer = null;
      targetCleanup?.(); targetCleanup = null;
      card?.remove(); card = null;
    };
    const finish = choice => {
      storage('localStorage', choiceKey, choice);
      storage('sessionStorage', progressKey, null);
      const focus = root.querySelector('[data-tour-highlight] input:not([type="hidden"]), [data-tour-highlight] summary, [data-tour-highlight] a')
        || root.querySelector('[data-profile-toggle]');
      clearStep();
      focus?.focus({preventScroll: true});
    };
    const action = (text, attribute, callback, primary = false) => {
      const result = node('button', 'button ' + (primary ? 'primary' : 'secondary'), text);
      result.type = 'button';
      result.setAttribute(attribute, '');
      on(result, 'click', callback);
      return result;
    };
    const closeButton = callback => {
      const result = action('×', 'data-tour-close', callback);
      result.className = 'qa-tour-close';
      result.setAttribute('aria-label', labels.close);
      return result;
    };
    const announceDirty = () => {
      const message = (dialog?.open ? dialog : card)?.querySelector('[data-tour-message]');
      if (message) { message.textContent = labels.dirty; message.hidden = false; }
    };
    function go(nextIndex) {
      if (dirty()) { announceDirty(); return; }
      if (nextIndex >= config.steps.length) {
        finish('completed');
        if (!sameRoute(config.homeUrl)) location.assign(home.href);
        return;
      }
      index = Math.max(0, nextIndex);
      storage('sessionStorage', progressKey, JSON.stringify({active: true, index}));
      const step = config.steps[index];
      if (!sameRoute(step.url)) {
        clearStep();
        location.assign(new URL(step.url, location.href).href);
      } else show();
    }
    function highlight(step) {
      let opened;
      if (step.open === 'calendar') {
        const control = root.querySelector('.form-date-control');
        const trigger = control?.querySelector('.date-time-trigger');
        if (trigger && trigger.getAttribute('aria-expanded') !== 'true') {
          trigger.click();
          opened = () => {
            if (trigger.isConnected && trigger.getAttribute('aria-expanded') === 'true') trigger.click();
          };
        }
      }
      let target;
      try { target = root.querySelector(step.selector); } catch (_) { return false; }
      if (!target) { opened?.(); return false; }
      const details = step.open === 'details' ? target.closest('details') : null;
      if (details && !details.open) {
        details.open = true;
        opened = () => { if (details.isConnected) details.open = false; };
      }
      if (!target.getBoundingClientRect().width || !target.getBoundingClientRect().height) { opened?.(); return false; }
      const describedBy = target.getAttribute('aria-describedby');
      target.setAttribute('aria-describedby', [describedBy, 'qa-tour-body'].filter(Boolean).join(' '));
      target.classList.add('qa-tour-target');
      target.setAttribute('data-tour-highlight', '');
      // Scrolling and opening controls only happen after explicit consent.
      target.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'});
      const removeSpotlight = spotlight(target, card);
      targetCleanup = () => {
        removeSpotlight();
        target.classList.remove('qa-tour-target'); target.removeAttribute('data-tour-highlight');
        if (describedBy === null) target.removeAttribute('aria-describedby');
        else target.setAttribute('aria-describedby', describedBy);
        opened?.();
      };
      return true;
    }
    function show() {
      clearStep();
      const step = config.steps[index];
      card = node('section', 'qa-tour-card');
      card.setAttribute('data-tour-card', ''); card.dataset.tourStep = step.id;
      card.setAttribute('role', 'dialog'); card.setAttribute('aria-modal', 'false');
      card.setAttribute('aria-labelledby', 'qa-tour-title'); card.setAttribute('aria-describedby', 'qa-tour-body');
      const progress = node('p', 'qa-tour-progress', `${labels.progress} ${index + 1} ${labels.of} ${config.steps.length}`);
      const title = node('h2', '', step.title); title.id = 'qa-tour-title';
      const body = node('p', 'qa-tour-body', step.body); body.id = 'qa-tour-body';
      const message = node('p', 'qa-tour-message');
      message.setAttribute('data-tour-message', ''); message.setAttribute('role', 'status'); message.hidden = true;
      const controls = node('div', 'qa-tour-controls');
      const back = action(labels.back, 'data-tour-back', () => go(index - 1)); back.disabled = index === 0;
      const next = action(index === config.steps.length - 1 ? labels.finish : labels.next, 'data-tour-next', () => go(index + 1), true);
      controls.append(back, next);
      const footer = node('div', 'qa-tour-footer');
      const skip = action(labels.skip, 'data-tour-skip', () => finish('skipped')); skip.className = 'link-button';
      footer.append(skip, controls);
      card.append(closeButton(() => finish('dismissed')), progress, title, body, message, footer);
      document.body.append(card);
      if (!highlight(step)) {
        observer = new MutationObserver(() => {
          if (!disposed && highlight(step)) { observer?.disconnect(); clearTimeout(timer); }
        });
        observer.observe(root.body || root, {subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'open']});
        timer = setTimeout(() => {
          observer?.disconnect();
          if (card) { message.textContent = labels.unavailable; message.hidden = false; }
        }, 2000);
      }
      next.focus({preventScroll: true});
    }
    function invitation() {
      clearStep();
      if (dialog?.open) return;
      storage('sessionStorage', progressKey, null);
      const previousFocus = document.activeElement;
      dialog = node('dialog', 'qa-tour-consent'); dialog.setAttribute('data-tour-consent', '');
      dialog.setAttribute('aria-labelledby', 'qa-tour-consent-title');
      dialog.setAttribute('aria-describedby', 'qa-tour-consent-body');
      const title = node('h2', '', labels.title); title.id = 'qa-tour-consent-title';
      const body = node('p', 'qa-tour-body', labels.invitation); body.id = 'qa-tour-consent-body';
      const message = node('p', 'qa-tour-message');
      message.setAttribute('data-tour-message', ''); message.setAttribute('role', 'status'); message.hidden = true;
      const closeInvitation = restoreFocus => {
        dialog.close(); dialog.remove(); dialog = null;
        if (restoreFocus && previousFocus?.isConnected) previousFocus.focus({preventScroll: true});
      };
      const dismiss = () => { finish('dismissed'); closeInvitation(true); };
      const controls = node('div', 'qa-tour-controls');
      const later = action(labels.later, 'data-tour-decline', dismiss);
      controls.append(later, action(labels.start, 'data-tour-accept', () => {
        if (dirty()) { announceDirty(); return; }
        storage('localStorage', choiceKey, 'accepted');
        closeInvitation(false); go(0);
      }, true));
      dialog.append(closeButton(dismiss), title, body, message, controls);
      on(dialog, 'cancel', event => { event.preventDefault(); dismiss(); });
      on(dialog, 'click', event => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dismiss();
      });
      document.body.append(dialog); dialog.showModal(); later.focus();
    }
    const profile = root.querySelector('[data-profile-popover]');
    let startButton;
    if (profile) {
      startButton = action(labels.start, 'data-tour-start', () => {
        profile.closest('details').open = false;
        invitation();
      });
      startButton.className = 'qa-tour-start';
      profile.insertBefore(startButton, profile.querySelector('form'));
    }
    on(document, 'keydown', event => {
      if (event.key === 'Escape' && card && !event.defaultPrevented) { event.preventDefault(); finish('dismissed'); }
    });
    const dispose = () => {
      disposed = true; abort.abort(); clearStep(); dialog?.remove(); startButton?.remove();
    };
    on(window, 'pagehide', dispose);
    current = {dispose};
    let progress;
    try { progress = JSON.parse(storage('sessionStorage', progressKey)); } catch (_) { /* Ignore corrupt state. */ }
    if (storage('localStorage', choiceKey) === 'accepted' && progress?.active === true && Number.isInteger(progress.index)
      && progress.index >= 0 && progress.index < config.steps.length) {
      index = progress.index;
      if (sameRoute(config.steps[index].url)) show();
      else storage('sessionStorage', progressKey, null); // Manual navigation never gets redirected.
    } else if (!storage('localStorage', choiceKey) && sameRoute(config.homeUrl)) invitation();
  }
  window.quiteAdminTour = {init};
  if (document.readyState === 'complete') init();
  else document.addEventListener('DOMContentLoaded', () => init(), {once: true});
})();
