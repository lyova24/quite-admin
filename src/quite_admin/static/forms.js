(function (root) {
  'use strict';
  const maxJSON = 200000;
  const tokenRE = /"(?:[^"\\]|\\.)*"\s*:|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\b(?:true|false|null)\b/g;
  function tokens(text) {
    const result = [];
    let last = 0;
    for (const match of text.matchAll(tokenRE)) {
      if (match.index > last) result.push(['plain', text.slice(last, match.index)]);
      const value = match[0];
      result.push([value.startsWith('"') ? (value.trimEnd().endsWith(':') ? 'key' : 'string') : /^(true|false|null)$/.test(value) ? 'literal' : 'number', value]);
      last = match.index + value.length;
    }
    result.push(['plain', text.slice(last)]);
    return result;
  }
  function splitTemporal(value, kind) {
    const pattern = kind === 'datetime'
      ? /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(Z|[+-]\d{2}:\d{2})?$/
      : /^(\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(Z|[+-]\d{2}:\d{2})?$/;
    const match = value.match(pattern);
    return !value ? ['', ''] : match ? [match[1], match[2] || ''] : null;
  }
  // Format lexical JSON without parsing numbers through JavaScript's binary float.
  // Validation still uses JSON.parse, but never serializes its numeric values.
  function formatJSON(text) {
    JSON.parse(text);
    let output = '', depth = 0, quoted = false, escaped = false;
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (quoted) {
        output += char;
        if (escaped) escaped = false;
        else if (char === '\\') escaped = true;
        else if (char === '"') quoted = false;
        continue;
      }
      if (/\s/.test(char)) continue;
      if (char === '"') { quoted = true; output += char; }
      else if (char === '{' || char === '[') {
        output += char;
        const next = text.slice(i + 1).trimStart()[0];
        if (next === '}' || next === ']') { output += next; i = text.indexOf(next, i + 1); }
        else { depth++; if (depth > 40) throw new RangeError('depth'); output += '\n' + '  '.repeat(depth); }
      } else if (char === '}' || char === ']') {
        depth--; output += '\n' + '  '.repeat(depth) + char;
      } else if (char === ',') output += ',\n' + '  '.repeat(depth);
      else if (char === ':') output += ': ';
      else output += char;
    }
    return output;
  }
  if (typeof module !== 'undefined') module.exports = {tokens, splitTemporal, formatJSON};
  if (!root.document) return;
  const doc = root.document;
  const config = doc.querySelector('[data-form-messages]');
  const messages = config ? JSON.parse(config.dataset.messages) : {};
  const t = name => messages[name] || name;
  function describe(input, id) {
    input.setAttribute('aria-describedby', [input.getAttribute('aria-describedby'), id].filter(Boolean).join(' '));
  }
  function attachCalendar(input, datetime) {
    const wrapper = doc.createElement('div'); wrapper.className = 'calendar-control';
    input.before(wrapper); wrapper.append(input); input.setAttribute('data-calendar-input', '');
    const trigger = doc.createElement('button'); trigger.type = 'button';
    trigger.className = 'button secondary calendar-trigger';
    trigger.textContent = '▦'; trigger.setAttribute('aria-label', t('Choose date'));
    trigger.setAttribute('aria-expanded', 'false');
    const panel = doc.createElement('div'); panel.className = 'calendar-panel'; panel.hidden = true;
    panel.id = input.id + '-calendar'; panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', t('Choose date')); trigger.setAttribute('aria-controls', panel.id);
    wrapper.append(trigger, panel);
    let year, month;
    function close(focus) { panel.hidden = true; trigger.setAttribute('aria-expanded', 'false'); if (focus) trigger.focus(); }
    function render() {
      panel.replaceChildren();
      const toolbar = doc.createElement('div'); toolbar.className = 'calendar-toolbar';
      function button(label, text, action) {
        const b = doc.createElement('button'); b.type = 'button'; b.className = 'button secondary small';
        b.textContent = text; b.setAttribute('aria-label', t(label)); b.addEventListener('click', action); return b;
      }
      const prev = button('Previous month', '‹', () => move(-1));
      const next = button('Next month', '›', () => move(1));
      prev.disabled = year === 1 && month === 0; next.disabled = year === 9999 && month === 11;
      const months = doc.createElement('select'); months.setAttribute('aria-label', t('Choose date'));
      for (let m = 0; m < 12; m++) {
        const option = doc.createElement('option'); option.value = m;
        option.textContent = new Intl.DateTimeFormat(doc.documentElement.lang, {month:'long', timeZone:'UTC'}).format(new Date(Date.UTC(2000,m,1)));
        months.append(option);
      }
      months.value = month; months.addEventListener('change', () => { month = Number(months.value); render(); });
      const years = doc.createElement('input'); years.type = 'number'; years.min = 1; years.max = 9999;
      years.value = year; years.setAttribute('aria-label', t('Year'));
      years.addEventListener('change', () => { if (years.checkValidity() && years.value) { year = Number(years.value); render(); } else years.value=year; });
      years.addEventListener('keydown', e => {if(e.key==='Enter'){e.preventDefault();years.dispatchEvent(new Event('change'));}});
      toolbar.append(prev, months, years, next); panel.append(toolbar);
      const grid = doc.createElement('div'); grid.className = 'calendar-grid';
      // Monday-first calendar, using UTC only for calendar arithmetic, never for record conversion.
      for (let d = 0; d < 7; d++) {
        const day = doc.createElement('span');
        day.textContent = new Intl.DateTimeFormat(doc.documentElement.lang,{weekday:'short',timeZone:'UTC'}).format(new Date(Date.UTC(2024,0,d+1)));
        grid.append(day);
      }
      const first = new Date(0); first.setUTCFullYear(year,month,1); first.setUTCHours(0,0,0,0);
      const count = new Date(first); count.setUTCMonth(month+1,0);
      for(let n=0; n<(first.getUTCDay()+6)%7; n++) grid.append(doc.createElement('span'));
      for(let day=1; day<=count.getUTCDate(); day++) {
        const iso = String(year).padStart(4,'0') + '-' + String(month+1).padStart(2,'0') + '-' + String(day).padStart(2,'0');
        const b = button('Choose date', String(day), () => {
          input.value = datetime ? iso + (input.value.includes('T') ? input.value.slice(input.value.indexOf('T')) : 'T00:00:00') : iso;
          input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); close(true);
        });
        b.setAttribute('aria-label',iso); b.setAttribute('aria-pressed',String(input.value.slice(0,10) === iso));
        grid.append(b);
      }
      panel.append(grid, button('Close', t('Close'), () => close(true)));
    }
    function move(delta) {
      month += delta; if(month<0){month=11;year--;} if(month>11){month=0;year++;} render();
    }
    trigger.addEventListener('click', () => {
      if(!panel.hidden){close(false);return;}
      const match = input.value.match(/^(\d{4})-(\d{2})-/); const now = new Date();
      year = match ? Number(match[1]) : now.getFullYear(); month = match ? Number(match[2])-1 : now.getMonth();
      render(); panel.hidden=false; trigger.setAttribute('aria-expanded','true');
      (panel.querySelector('[aria-pressed="true"]') || panel.querySelector('.calendar-grid button')).focus();
    });
    wrapper.addEventListener('keydown', e => {if(e.key==='Escape'){e.preventDefault();close(true);}});
    const outside = e => {if(!wrapper.contains(e.target))close(false);};
    doc.addEventListener('click', outside);
    return () => doc.removeEventListener('click', outside);
  }
  function enhance(scope) {
    const cleanups = [];
  for (const input of scope.querySelectorAll('[data-calendar-input]')) cleanups.push(attachCalendar(input, false));
  for (const select of scope.querySelectorAll('[data-boolean-toggle]')) {
    const group = doc.createElement('div'); group.className = 'toggle-control';
    const toggle = doc.createElement('button'); toggle.type = 'button'; toggle.className = 'boolean-toggle';
    toggle.id = select.id + '-switch'; toggle.setAttribute('role','switch');
    const label = doc.querySelector('label[for="' + CSS.escape(select.id) + '"]');
    if(label){label.htmlFor=toggle.id;toggle.setAttribute('aria-labelledby',label.id);}
    else if(select.hasAttribute('aria-labelledby'))toggle.setAttribute('aria-labelledby',select.getAttribute('aria-labelledby'));
    if(select.hasAttribute('aria-describedby')) toggle.setAttribute('aria-describedby',select.getAttribute('aria-describedby'));
    if(select.hasAttribute('aria-invalid')) toggle.setAttribute('aria-invalid',select.getAttribute('aria-invalid'));
    const state = doc.createElement('span'); state.className = 'field-help';
    group.append(toggle,state);
    let previous = select.value || 'false';
    const nullButton = doc.createElement('button'); nullButton.type='button';
    nullButton.className='button secondary small';nullButton.textContent=t('None');
    const nullable = Array.from(select.options).some(option=>option.value==='');
    function render(){
      const empty=select.value==='';toggle.disabled=empty;
      toggle.setAttribute('aria-checked',String(select.value==='true'));
      state.textContent=t(empty?'None':select.value==='true'?'True':'False');
      nullButton.setAttribute('aria-pressed',String(empty));
    }
    function change(value){select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));render();}
    toggle.addEventListener('click',()=>{previous=select.value==='true'?'false':'true';change(previous);});
    if(nullable){group.append(nullButton);nullButton.addEventListener('click',()=>{if(select.value){previous=select.value;change('');}else change(previous);});}
    select.after(group);select.hidden=true;select.addEventListener('change',render);render();
  }
  for (const input of scope.querySelectorAll('[data-json-editor]')) {
    const wrap = doc.createElement('div');
    wrap.className = 'json-editor';
    input.before(wrap); wrap.append(input);
    const pre = doc.createElement('pre');
    pre.className = 'json-highlight code-input'; pre.setAttribute('aria-hidden', 'true');
    wrap.prepend(pre);
    const toolbar = doc.createElement('div'); toolbar.className = 'json-toolbar';
    const button = doc.createElement('button'); button.type = 'button';
    button.className = 'button secondary small'; button.textContent = t('Format JSON');
    const status = doc.createElement('span'); status.className = 'field-help';
    status.id = input.id + '-json-status'; status.setAttribute('role', 'status');
    toolbar.append(button, status); wrap.after(toolbar); describe(input, status.id);
    input.wrap = 'off';
    function render() {
      const text = input.value;
      pre.replaceChildren();
      const large = text.length > maxJSON;
      wrap.classList.toggle('json-plain', large);
      if (!large) {
        for (const [kind, value] of tokens(text)) {
          const span = doc.createElement('span'); span.className = 'json-' + kind;
          span.textContent = value; pre.append(span);
        }
        pre.append(doc.createTextNode('\n'));
      }
      button.disabled = large || !text.trim();
      if (large) status.textContent = t('JSON is too large for highlighting.');
      else if (!text.trim()) status.textContent = '';
      else {
        try { JSON.parse(text); status.textContent = t('Valid JSON'); }
        catch (_) { status.textContent = t('Invalid JSON'); button.disabled = true; }
      }
      pre.scrollTop = input.scrollTop; pre.scrollLeft = input.scrollLeft;
    }
    input.addEventListener('input', render);
    input.addEventListener('scroll', () => { pre.scrollTop = input.scrollTop; pre.scrollLeft = input.scrollLeft; });
    button.addEventListener('click', () => {
      if (input.value.length > maxJSON) return;
      try { input.value = formatJSON(input.value); input.dispatchEvent(new Event('input', {bubbles: true})); }
      catch (_) { status.textContent = t('JSON nesting is too deep to format.'); }
    });
    render();
  }
  for (const input of scope.querySelectorAll('[data-temporal]')) {
    const kind = input.dataset.temporal;
    const parts = splitTemporal(input.value, kind);
    if (!parts) continue; // Preserve unrecognized submitted values and exotic ISO offsets verbatim.
    const picker = doc.createElement('input');
    picker.type = kind === 'datetime' ? 'datetime-local' : 'time';
    if (picker.type === 'text') continue;
    picker.step = '1'; picker.value = parts[0].replace(/\.\d+$/, '');
    if (parts[0] && !picker.value) continue;
    const group = doc.createElement('div'); group.className = 'temporal-controls';
    picker.id = input.id + '-picker';
    for (const name of ['aria-describedby', 'aria-invalid']) {
      if (input.hasAttribute(name)) picker.setAttribute(name, input.getAttribute(name));
    }
    const label = doc.querySelector('label[for="' + CSS.escape(input.id) + '"]');
    if (label) label.htmlFor = picker.id;
    const fractionLabel = doc.createElement('label'); fractionLabel.className = 'field-help temporal-fraction';
    fractionLabel.append(doc.createTextNode(t('Fractional seconds (optional)')));
    const fraction = doc.createElement('input'); fraction.type = 'text';
    fraction.value = (parts[0].match(/\.(\d+)$/) || ['', ''])[1];
    fraction.placeholder = '123456'; fraction.maxLength = 6; fraction.pattern = '[0-9]{1,6}';
    fraction.inputMode = 'numeric'; fractionLabel.append(fraction);
    const offsetLabel = doc.createElement('label'); offsetLabel.className = 'field-help temporal-offset';
    offsetLabel.append(doc.createTextNode(t('UTC offset (optional)')));
    const offset = doc.createElement('input'); offset.type = 'text'; offset.value = parts[1];
    offset.placeholder = '+03:00'; offset.maxLength = 6;
    offset.pattern = 'Z|(?:[+]|-)(?:[01][0-9]|2[0-3]):[0-5][0-9]';
    const hint = doc.createElement('p'); hint.className = 'field-help';
    hint.id = input.id + '-timezone-help'; hint.textContent = t('Use Z or ±HH:MM; leave empty for no timezone.');
    describe(offset, hint.id);
    offsetLabel.append(offset); group.append(picker, fractionLabel, offsetLabel);
    input.after(group, hint); input.type = 'hidden';
    // Do not rewrite the original value until the user changes a control. Browsers
    // may normalize :00 or fractional seconds in datetime-local display values.
    const sync = () => { input.value = picker.value ? picker.value + (fraction.value ? '.' + fraction.value : '') + offset.value : ''; };
    picker.addEventListener('input', sync); fraction.addEventListener('input', sync); offset.addEventListener('input', sync);
    if (kind === 'datetime') cleanups.push(attachCalendar(picker, true));
  }
    return () => cleanups.forEach(cleanup => cleanup());
  }
  root.quiteAdminEnhanceFields = enhance;
  enhance(doc);

})(typeof window !== 'undefined' ? window : globalThis);
