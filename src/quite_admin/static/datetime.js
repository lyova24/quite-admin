/* Shared calendar and date/time picker. Canonical values never enter browser storage. */
(function (root) {
  "use strict";
  function utcDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(0);
    date.setUTCFullYear(year, month - 1, day);
    date.setUTCHours(0, 0, 0, 0);
    return isoDay(date) === value ? date : null;
  }
  function isoDay(date) {
    const year = date.getUTCFullYear();
    return year < 1 || year > 9999 ? "" : [String(year).padStart(4, "0"),
      String(date.getUTCMonth() + 1).padStart(2, "0"), String(date.getUTCDate()).padStart(2, "0")].join("-");
  }
  function shiftDay(value, amount) {
    const date = utcDate(value);
    if (!date) return "";
    date.setUTCDate(date.getUTCDate() + amount);
    return isoDay(date);
  }
  function monthCells(year, month) {
    const date = new Date(0);
    date.setUTCFullYear(year, month, 1);
    date.setUTCHours(0, 0, 0, 0);
    date.setUTCDate(1 - (date.getUTCDay() + 6) % 7);
    return Array.from({length: 42}, () => {
      const value = isoDay(date); date.setUTCDate(date.getUTCDate() + 1); return value;
    });
  }
  function presetBounds(preset, today) {
    if (!utcDate(today)) return null;
    if (preset === "all") return {mode: "all", start: "", end: ""};
    if (preset === "today" || preset === "yesterday") {
      const day = shiftDay(today, preset === "today" ? 0 : -1);
      return day ? {mode: "day", start: day, end: day} : null;
    }
    const start = preset === "week" ? shiftDay(today, -6)
      : preset === "month" ? shiftDay(today, -29)
      : preset === "this_month" ? today.slice(0, 8) + "01" : "";
    return start ? {mode: "range", start, end: today} : null;
  }
  function splitTemporal(value, kind) {
    const pattern = kind === 'datetime'
      ? /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(Z|[+-]\d{2}:\d{2})?$/
      : /^(\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(Z|[+-]\d{2}:\d{2})?$/;
    const match = value.match(pattern);
    return !value ? ['', ''] : match ? [match[1], match[2] || ''] : null;
  }
  function parseValue(value, kind) {
    if (!value) return {day: '', time: '', fraction: '', offset: ''};
    if (kind === 'date') return utcDate(value) ? {day: value, time: '', fraction: '', offset: ''} : null;
    const parts = splitTemporal(value, kind);
    if (!parts) return null;
    const [local, offset] = parts;
    const day = kind === 'datetime' ? local.slice(0, 10) : '';
    const clock = kind === 'datetime' ? local.slice(11) : local;
    const [time, fraction = ''] = clock.split('.');
    if (day && !utcDate(day)) return null;
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(time)) return null;
    if (offset && !/^(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(offset)) return null;
    return {day, time, fraction, offset};
  }
  function composeValue(parts, kind) {
    if (kind === 'date') return !parts.day || utcDate(parts.day) ? parts.day : null;
    if (!parts.day && !parts.time && !parts.fraction && !parts.offset) return '';
    if (parts.fraction && !/^\d{1,6}$/.test(parts.fraction)) return null;
    // A fraction belongs to seconds, even when the browser normalizes :00 away.
    let time = parts.time;
    if (parts.fraction && /^\d{2}:\d{2}$/.test(time)) time += ':00';
    const value = (kind === 'datetime' ? parts.day + 'T' : '') + time
      + (parts.fraction ? '.' + parts.fraction : '') + parts.offset;
    return parseValue(value, kind) ? value : null;
  }
  function rangeReversed(lower, upper, kind) {
    if (!lower || !upper) return false;
    const a = parseValue(lower, kind), b = parseValue(upper, kind);
    if (!a || !b || Boolean(a.offset) !== Boolean(b.offset)) return null;
    function stamp(parts) {
      let value = parts.day ? BigInt(utcDate(parts.day).getTime()) * 1000n : 0n;
      if (parts.time) {
        const [hour, minute, second = 0] = parts.time.split(':').map(Number);
        value += BigInt(hour * 3600 + minute * 60 + second) * 1000000n;
        value += BigInt((parts.fraction || '').padEnd(6, '0'));
      }
      if (parts.offset && parts.offset !== 'Z') {
        const minutes = Number(parts.offset.slice(1, 3)) * 60 + Number(parts.offset.slice(4));
        value -= BigInt(minutes * (parts.offset[0] === '-' ? -1 : 1)) * 60000000n;
      }
      return value;
    }
    return stamp(a) > stamp(b);
  }
  const api = {utcDate, isoDay, shiftDay, monthCells, presetBounds, splitTemporal, parseValue, composeValue, rangeReversed};
  if (typeof module !== 'undefined') module.exports = api;
  root.QuiteAdminDateTime = api;
  const doc = root.document;
  if (!doc) return;
  let nextID = 0;
  function element(tag, className, text) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function button(label, text, action, className) {
    const item = element('button', className, text); item.type = 'button';
    item.setAttribute('aria-label', label); item.addEventListener('click', action); return item;
  }
  function localToday() {
    const now = new Date();
    return [String(now.getFullYear()).padStart(4, '0'), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
  }
  function pickerIcon(kind = 'date') {
    const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '16'); svg.setAttribute('height', '16'); svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '1.6'); svg.setAttribute('aria-hidden', 'true');
    const path = doc.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', kind === 'time' ? 'M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z' : 'M3 5h18v16H3ZM3 11h18M8 3v4M16 3v4M8 15h2m4 0h2');
    svg.append(path); return svg;
  }
  function calendar(host, {getValue, onChange, label, t, today, getRange = () => []}) {
    if (!today) today = localToday();
    const locale = doc.documentElement.lang;
    const monthFormat = new Intl.DateTimeFormat(locale, {month: 'long', timeZone: 'UTC'});
    const weekdayFormat = new Intl.DateTimeFormat(locale, {weekday: 'short', timeZone: 'UTC'});
    const monthNames = Array.from({length: 12}, (_, n) => monthFormat.format(new Date(Date.UTC(2000, n, 1))));
    const weekdayNames = Array.from({length: 7}, (_, n) => weekdayFormat.format(new Date(Date.UTC(2024, 0, n + 1))));
    host.setAttribute('role', 'group'); host.setAttribute('aria-label', t('Choose date') + ': ' + label);
    let year, month;
    const instance = {
      reset() {
        const selected = utcDate(getValue()) || utcDate(today);
        year = selected.getUTCFullYear(); month = selected.getUTCMonth(); instance.render();
      },
      render(focus = '') {
        host.replaceChildren();
        const toolbar = element('div', 'date-calendar-toolbar');
        const move = delta => {
          month += delta;
          if (month < 0) { month = 11; year--; }
          if (month > 11) { month = 0; year++; }
          instance.render();
          host.querySelector(delta < 0 ? 'button:first-child' : 'button:last-child').focus();
        };
        const previous = button(t('Previous month'), '‹', () => move(-1));
        const next = button(t('Next month'), '›', () => move(1));
        previous.disabled = year === 1 && month === 0; next.disabled = year === 9999 && month === 11;
        const months = element('select'); months.setAttribute('aria-label', t('Month') + ': ' + label);
        for (let n = 0; n < 12; n++) {
          const option = element('option', '', monthNames[n]);
          option.value = String(n); months.append(option);
        }
        months.value = String(month);
        months.addEventListener('change', () => { month = Number(months.value); instance.render(); host.querySelector('select').focus(); });
        const years = element('input'); years.type = 'number'; years.min = '1'; years.max = '9999';
        years.value = String(year); years.setAttribute('aria-label', t('Year') + ': ' + label);
        years.addEventListener('change', () => {
          if (years.value && years.checkValidity()) year = Number(years.value);
          instance.render(); host.querySelector('input[type="number"]').focus();
        });
        years.addEventListener('keydown', event => {
          if (event.key === 'Enter') { event.preventDefault(); years.dispatchEvent(new Event('change')); }
        });
        toolbar.append(previous, months, years, next);
        const grid = element('div', 'date-calendar-grid');
        for (const name of weekdayNames) grid.append(element('span', '', name));
        const cells = monthCells(year, month), value = getValue();
        const first = String(year).padStart(4, '0') + '-' + String(month + 1).padStart(2, '0') + '-01';
        const selected = focus || (cells.includes(value) ? value : first);
        const [from, to] = getRange();
        for (const day of cells) {
          if (!day) { grid.append(element('span')); continue; }
          const item = button(day, String(Number(day.slice(8))), () => {
            const chosen = utcDate(day); year = chosen.getUTCFullYear(); month = chosen.getUTCMonth();
            onChange(day);
            if (host.closest('[hidden]')) return;
            instance.render(day); host.querySelector('[data-iso="' + day + '"]')?.focus();
          });
          item.dataset.iso = day; item.tabIndex = day === selected ? 0 : -1;
          item.setAttribute('aria-pressed', String(value === day));
          if (day === today) item.setAttribute('aria-current', 'date');
          if (Number(day.slice(5, 7)) !== month + 1) item.classList.add('date-outside');
          if (from && to && day > from && day < to) item.classList.add('date-in-range');
          item.addEventListener('keydown', event => {
            let target = '';
            const offset = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[event.key];
            if (offset) target = shiftDay(day, offset);
            if (event.key === 'Home' || event.key === 'End') {
              const weekday = (utcDate(day).getUTCDay() + 6) % 7;
              target = shiftDay(day, event.key === 'Home' ? -weekday : 6 - weekday);
            }
            if (event.key === 'PageUp' || event.key === 'PageDown') {
              const date = utcDate(day), original = date.getUTCDate();
              date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth() + (event.key === 'PageUp' ? -1 : 1));
              const last = new Date(date); last.setUTCMonth(last.getUTCMonth() + 1, 0);
              date.setUTCDate(Math.min(original, last.getUTCDate())); target = isoDay(date);
            }
            if (!target) return;
            event.preventDefault(); const date = utcDate(target);
            year = date.getUTCFullYear(); month = date.getUTCMonth(); instance.render(target);
            host.querySelector('[data-iso="' + target + '"]').focus();
          });
          grid.append(item);
        }
        host.append(toolbar, grid);
      }
    };
    instance.reset(); return instance;
  }
  function precisionControls(fraction, offset) {
    fraction.maxLength = 6; fraction.pattern = '[0-9]{1,6}'; fraction.inputMode = 'numeric'; fraction.placeholder = '123456';
    offset.maxLength = 6; offset.placeholder = '+03:00'; offset.pattern = 'Z|(?:[+]|-)(?:[01][0-9]|2[0-3]):[0-5][0-9]';
  }
  function notify(input) {
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
  function bindPopover(wrapper, panel, {close, position, onKeydown = () => {}}) {
    const outside = event => { if (!wrapper.contains(event.target)) close(false); };
    const keydown = event => {
      if (!panel.hidden && event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); close(true); return;
      }
      onKeydown(event);
    };
    wrapper.addEventListener('keydown', keydown);
    doc.addEventListener('pointerdown', outside);
    root.addEventListener('resize', position);
    return () => {
      close(false);
      wrapper.removeEventListener('keydown', keydown);
      doc.removeEventListener('pointerdown', outside);
      root.removeEventListener('resize', position);
    };
  }
  function hidePanel(panel, trigger) {
    panel.hidden = true; trigger.setAttribute('aria-expanded', 'false');
    // Hidden draft controls must not participate in the enclosing form's validation.
    panel.querySelectorAll('input,select').forEach(input => { input.disabled = true; });
  }
  function attachForm(input, kind, t) {
    if (input.dataset.dateReady || input.disabled || input.readOnly) return () => {};
    const parts = parseValue(input.value, kind);
    if (!parts) return () => {}; // Keep unsupported/invalid submitted ISO text editable verbatim.
    input.dataset.dateReady = 'true';
    const cleanups = [];
    if (kind === 'date') return attachFormCalendar(input, t);
    const group = element('div', 'form-temporal');
    const row = element('div', 'form-temporal-row' + (kind === 'datetime' ? ' form-temporal-datetime' : ''));
    const outerLabel = doc.querySelector('label[for="' + CSS.escape(input.id) + '"]');
    const label = outerLabel?.textContent.trim() || input.getAttribute('aria-label') || input.name;
    function control(type, suffix) {
      const node = element('input'); node.type = type; node.id = input.id + '-' + suffix;
      for (const attribute of ['aria-describedby', 'aria-invalid', 'aria-labelledby']) {
        if (input.hasAttribute(attribute)) node.setAttribute(attribute, input.getAttribute(attribute));
      }
      return node;
    }
    let date;
    if (kind === 'datetime') {
      date = control('date', 'date'); date.min = '0001-01-01'; date.max = '9999-12-31'; date.value = parts.day;
      row.append(date);
    }
    const time = control('time', 'time'); time.step = '1'; time.value = parts.time;
    if (date) {
      time.removeAttribute('aria-labelledby'); time.setAttribute('aria-label', t('Time') + ': ' + label);
    }
    row.append(time);
    if (outerLabel) outerLabel.htmlFor = (date || time).id;
    group.append(row); input.after(group); input.type = 'hidden';
    const options = element('details', 'form-temporal-options');
    const summary = element('summary', '', t('More options'));
    const metadata = element('small'); summary.append(metadata);
    const fields = element('div', 'date-picker-precision');
    function option(text, property) {
      const label = element('label', 'date-picker-field', t(text));
      const node = element('input'); node.type = 'text'; node.value = parts[property];
      node.addEventListener('input', () => { parts[property] = node.value; sync(); });
      node.addEventListener('invalid', () => {
        options.open = true;
        // WebKit needs the opened section laid out before it can focus its first error.
        root.requestAnimationFrame(() => {
          const first = node.form?.querySelector('input:invalid,select:invalid,textarea:invalid');
          if (node.isConnected && (!first || first === node)) node.focus();
        });
      });
      label.append(node); fields.append(label); return node;
    }
    const fraction = option('Fractional seconds (optional)', 'fraction');
    const offset = option('UTC offset (optional)', 'offset');
    precisionControls(fraction, offset);
    const hint = element('p', 'field-help', t('Use Z or ±HH:MM; leave empty for no timezone.'));
    hint.id = input.id + '-timezone-help'; offset.setAttribute('aria-describedby', hint.id);
    options.append(summary, fields, hint);
    group.append(options);
    function presentation() {
      metadata.textContent = [parts.fraction ? '.' + parts.fraction : '', parts.offset].filter(Boolean).join(' · ');
    }
    function sync() {
      const empty = !parts.day && !parts.time;
      date?.setCustomValidity(parts.time && !parts.day && kind === 'datetime' ? t('Choose a date.') : '');
      time.setCustomValidity(parts.day && !parts.time ? t('Enter a time.') : '');
      const value = empty ? '' : composeValue(parts, kind);
      if (value !== null) {
        input.value = value;
        notify(input);
      }
      presentation();
    }
    function clear() {
      parts.day = parts.time = parts.fraction = parts.offset = '';
      if (date) date.value = '';
      time.value = fraction.value = offset.value = '';
    }
    date?.addEventListener('input', () => {
      parts.day = date.value;
      if (!parts.day) clear();
      else if (!parts.time) { parts.time = '00:00'; time.value = parts.time; }
      sync();
    });
    time.addEventListener('input', () => {
      parts.time = time.value;
      if (!parts.time && !parts.day) clear();
      sync();
    });
    presentation();
    if (date) cleanups.push(attachFormCalendar(date, t));
    return () => cleanups.forEach(cleanup => cleanup());
  }
  function attachFormCalendar(input, t) {
    const wrapper = element('div', 'date-time-control form-date-control');
    input.before(wrapper); wrapper.append(input);
    const trigger = button(t('Choose date'), '', () => panel.hidden ? open() : close(true), 'date-time-trigger');
    trigger.append(pickerIcon()); trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-expanded', 'false');
    const panel = element('div', 'date-picker-panel date-time-panel form-date-panel');
    panel.id = 'date-picker-' + (++nextID); panel.hidden = true; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', t('Choose date'));
    trigger.setAttribute('aria-controls', panel.id); wrapper.append(trigger, panel);
    let instance;
    function commit(value) {
      input.value = value; notify(input); close(true);
    }
    function close(focus) {
      hidePanel(panel, trigger);
      if (focus) input.focus({preventScroll: true});
    }
    function position() {
      if (panel.hidden || wrapper.closest('dialog')) return;
      panel.classList.remove('date-picker-above', 'date-panel-constrained');
      const field = wrapper.getBoundingClientRect(), bounds = panel.getBoundingClientRect(), height = bounds.height;
      panel.classList.toggle('date-panel-align-left', field.right < bounds.width + 12);
      const below = root.innerHeight - field.bottom - 12, above = field.top - 12;
      if (below < height && above > below) panel.classList.add('date-picker-above');
      if (Math.max(above, below) < height) panel.classList.add('date-panel-constrained');
    }
    function open() {
      panel.replaceChildren(); const host = element('div', 'form-date-calendar');
      instance = calendar(host, {getValue: () => input.value, onChange: commit, label: t('Date'), t});
      const footer = element('footer', 'date-picker-footer');
      footer.append(button(t('Today'), t('Today'), () => {
        commit(localToday());
      }, 'link-button'), button(t('Clear'), t('Clear'), () => commit(''), 'link-button'));
      panel.append(host, footer); panel.hidden = false; trigger.setAttribute('aria-expanded', 'true'); position();
      (panel.querySelector('[aria-pressed="true"]') || panel.querySelector('.date-calendar-grid button')).focus({preventScroll: true});
    }
    const refresh = () => { if (!panel.hidden) instance.reset(); };
    input.addEventListener('input', refresh);
    const unbind = bindPopover(wrapper, panel, {close, position, onKeydown: event => {
      if (event.target === input && event.altKey && event.key === 'ArrowDown') { event.preventDefault(); open(); }
    }});
    return () => { unbind(); input.removeEventListener('input', refresh); };
  }
  function attach(inputs, kind, t) {
    if (!inputs.length || inputs.some(input => input.dataset.dateReady || input.disabled || input.readOnly)) return () => {};
    // Exotic ISO shapes remain editable verbatim, as before; never normalize them implicitly.
    if (inputs.some(input => !parseValue(input.value, kind))) return () => {};
    const range = inputs.length === 2;
    const choose = t(range ? kind === 'time' ? 'Choose time range' : 'Choose date range'
      : kind === 'time' ? 'Choose time' : kind === 'datetime' ? 'Choose date and time' : 'Choose date');
    const wrapper = element('div', 'date-time-control' + (range ? ' date-time-range-control' : ''));
    const trigger = button(choose, '', () => panel.hidden ? open() : close(true), 'date-time-trigger');
    trigger.append(pickerIcon(kind)); trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-expanded', 'false');
    const panel = element('div', 'date-picker-panel date-time-panel' + (range ? ' date-time-range-panel' : ''));
    panel.hidden = true; panel.id = 'date-picker-' + (++nextID); panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', choose);
    trigger.setAttribute('aria-controls', panel.id);
    if (range) {
      const rows = inputs.map(input => input.parentElement);
      rows[0].before(wrapper);
      const endpoints = element('div', 'date-time-endpoints'); endpoints.append(...rows);
      wrapper.append(trigger, endpoints, panel);
    } else { inputs[0].before(wrapper); wrapper.append(trigger, inputs[0], panel); }
    inputs.forEach(input => { input.dataset.dateReady = 'true'; });
    let drafts, calendars = [], controls = [];
    function close(focus) {
      hidePanel(panel, trigger);
      if (focus) trigger.focus();
    }
    function placePanel() {
      if (panel.hidden) return;
      panel.classList.remove('date-picker-above');
      if (!wrapper.closest('dialog')) {
        const field = wrapper.getBoundingClientRect(), height = panel.getBoundingClientRect().height;
        if (root.innerHeight - field.bottom < height && field.top >= height + 16) panel.classList.add('date-picker-above');
      }
      panel.scrollIntoView({block: 'nearest', inline: 'nearest'});
    }
    function open() {
      drafts = inputs.map(input => parseValue(input.value, kind));
      if (drafts.some(value => !value)) { inputs.find((input, i) => !drafts[i]).focus(); return; }
      panel.replaceChildren(); calendars = []; controls = [];
      panel.append(element('div', 'date-picker-heading', choose));
      const columns = element('div', 'date-picker-columns' + (range ? ' date-picker-range-columns' : ''));
      drafts.forEach((draft, index) => {
        const column = element('div', 'date-picker-column');
        if (range) column.append(element('h3', 'date-picker-bound', t(index ? 'To' : 'From')));
        const prefix = range ? t(index ? 'To' : 'From') + ': ' : '';
        function control(label, type, value, property) {
          const wrap = element('label', 'date-picker-field', t(label));
          const input = element('input'); input.type = type; input.value = value;
          input.setAttribute('aria-label', prefix + t(label));
          input.addEventListener('input', () => { draft[property] = input.value; error.hidden = true; });
          wrap.append(input); column.append(wrap); controls.push(input); return input;
        }
        let date;
        if (kind !== 'time') {
          const host = element('div'); column.append(host);
          date = control('Date', 'date', draft.day, 'day'); date.min = '0001-01-01'; date.max = '9999-12-31';
          const item = calendar(host, {getValue: () => draft.day, label: prefix + t('Date'), t,
            getRange: () => range ? drafts.map(value => value.day) : [],
            onChange: day => {
              draft.day = date.value = day;
              if (kind === 'datetime' && !draft.time) { draft.time = '00:00:00'; time.value = draft.time; }
              error.hidden = true; calendars.forEach(value => value.render());
            }});
          calendars.push(item);
          date.addEventListener('change', () => { item.reset(); calendars.forEach(value => value.render()); });
        }
        let time;
        if (kind !== 'date') {
          time = control('Time', 'time', draft.time, 'time'); time.step = '1';
          if (date) {
            const dateClock = element('div', 'date-picker-date-clock');
            date.parentElement.before(dateClock); dateClock.append(date.parentElement, time.parentElement);
          }
          const advanced = element('details', 'date-picker-advanced');
          const summary = element('summary', '', t('Precision and timezone'));
          const detail = [draft.fraction ? '.' + draft.fraction : '', draft.offset].filter(Boolean).join(' · ');
          if (detail) summary.append(element('small', '', detail));
          const precision = element('div', 'date-picker-precision');
          const fraction = control('Fractional seconds (optional)', 'text', draft.fraction, 'fraction');
          const offset = control('UTC offset (optional)', 'text', draft.offset, 'offset');
          precisionControls(fraction, offset);
          precision.append(fraction.parentElement, offset.parentElement);
          advanced.append(summary, precision, element('p', 'field-help date-picker-zone-help', t('Use Z or ±HH:MM; leave empty for no timezone.')));
          advanced.addEventListener('toggle', placePanel);
          column.append(advanced);
        }
        columns.append(column);
      });
      const error = element('p', 'field-error date-picker-error'); error.setAttribute('role', 'alert'); error.hidden = true;
      function apply() {
        const invalidControl = controls.find(input => !input.checkValidity());
        if (invalidControl) {
          const details = invalidControl.closest('details'); if (details) details.open = true;
          invalidControl.reportValidity(); return;
        }
        const values = drafts.map(value => composeValue(value, kind));
        const invalid = values.some(value => value === null) ? 'Invalid date/time value.'
          : range && rangeReversed(...values, kind) ? 'The lower bound must not exceed the upper bound.' : '';
        if (invalid) { error.textContent = t(invalid); error.hidden = false; return; }
        commit(values);
      }
      function commit(values) {
        inputs.forEach((input, i) => { input.value = values[i]; notify(input); });
        close(true);
      }
      const footer = element('footer', 'date-picker-footer');
      const clear = button(t('Clear'), t('Clear'), () => commit(inputs.map(() => '')), 'link-button');
      const actions = element('div', 'button-group');
      actions.append(button(t('Cancel'), t('Cancel'), () => close(true), 'link-button'), button(t('Apply'), t('Apply'), apply, 'button primary small'));
      footer.append(clear, actions); panel.append(columns, error, footer);
      panel.hidden = false; trigger.setAttribute('aria-expanded', 'true');
      (panel.querySelector('[aria-pressed="true"]') || panel.querySelector('.date-calendar-grid button') || controls[0]).focus({preventScroll: true});
      placePanel();
    }
    return bindPopover(wrapper, panel, {close, position: placePanel, onKeydown: event => {
      if (!panel.hidden && event.key === 'Enter' && event.target.tagName === 'INPUT' && !event.defaultPrevented) {
        event.preventDefault(); event.stopPropagation(); panel.querySelector('.date-picker-footer .primary').click();
      }
    }});
  }
  Object.assign(api, {calendar, attach, attachForm});
})(typeof window !== 'undefined' ? window : globalThis);
