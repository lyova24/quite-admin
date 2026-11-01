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
  const picker = root.QuiteAdminDateTime || (typeof module !== 'undefined' ? require('./datetime.js') : null);
  const {splitTemporal} = picker;
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
  function describe(input, id) {
    input.setAttribute('aria-describedby', [input.getAttribute('aria-describedby'), id].filter(Boolean).join(' '));
  }
  const enhanced = new WeakSet();
  // The same controls are used by inline edits and the standalone browser demo.
  function createFieldControl(field, {id, value = '', t = text => text, rows = 6, enhance = true, noneLabel = '—'} = {}) {
    let control;
    if (field.kind === 'boolean' || field.choices?.length) {
      control = doc.createElement('select');
      const choices = field.kind === 'boolean'
        ? [['true', t('True')], ['false', t('False')]] : field.choices.map(choice => [choice, choice]);
      if (field.nullable) choices.unshift(['', noneLabel]);
      for (const [key, text] of choices) {
        const option = doc.createElement('option'); option.value = key; option.textContent = text;
        option.defaultSelected = key === value; control.append(option);
      }
      if (enhance && field.kind === 'boolean') control.dataset.booleanToggle = '';
    } else if (field.kind === 'json' || field.multiline) {
      control = doc.createElement('textarea'); control.rows = rows; control.textContent = value;
      if (field.kind === 'json') {
        control.className = 'code-input'; control.spellcheck = false;
        if (enhance) control.dataset.jsonEditor = '';
      }
    } else {
      control = doc.createElement('input');
      control.type = ['integer', 'number'].includes(field.kind) ? 'number' : field.kind === 'date' ? 'date' : 'text';
      if (['integer', 'number'].includes(field.kind)) control.step = field.kind === 'integer' ? '1' : 'any';
      if (field.kind === 'date') control.dataset.calendarInput = '';
      if (['datetime', 'time'].includes(field.kind)) control.dataset.temporal = field.kind;
      control.setAttribute('value', value);
    }
    control.id = id; control.name = field.name; control.value = value;
    if (field.max_length) control.maxLength = field.max_length;
    return control;
  }
  function enhanceBoolean(select, t) {
    const group = doc.createElement('div'); group.className = 'toggle-control';
    const toggle = doc.createElement('button'); toggle.type = 'button'; toggle.className = 'boolean-toggle';
    toggle.id = select.id + '-switch'; toggle.setAttribute('role','switch');
    const label = select.labels[0] || doc.querySelector('label[for="' + CSS.escape(select.id) + '"]');
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
  function enhanceJSON(input, t) {
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
      const fragment = doc.createDocumentFragment();
      const large = text.length > maxJSON;
      wrap.classList.toggle('json-plain', large);
      if (!large) {
        for (const [kind, value] of tokens(text)) {
          const span = doc.createElement('span'); span.className = 'json-' + kind;
          span.textContent = value; fragment.append(span);
        }
        fragment.append(doc.createTextNode('\n'));
      }
      pre.replaceChildren(fragment);
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
  function enhance(scope) {
    const config = doc.querySelector('[data-form-messages]');
    const messages = config ? JSON.parse(config.dataset.messages) : {};
    const t = name => messages[name] || name;
    const cleanups = [];
    const ranges = [...scope.querySelectorAll('[data-temporal-range]')];
    if (scope.matches?.('[data-temporal-range]')) ranges.unshift(scope);
    for (const host of ranges) {
      const inputs = [...host.querySelectorAll('input[data-calendar-input],input[data-temporal]')];
      cleanups.push(picker.attach(inputs, host.dataset.temporalRange, t));
    }
    for (const input of scope.querySelectorAll('input[data-calendar-input],input[data-temporal]')) {
      if (input.dataset.dateReady) continue;
      const kind = input.dataset.temporal || 'date';
      cleanups.push(input.closest('.record-form,[data-inline-dialog]')
        ? picker.attachForm(input, kind, t) : picker.attach([input], kind, t));
    }
    for (const select of scope.querySelectorAll('[data-boolean-toggle]')) {
      if (enhanced.has(select)) continue;
      enhanceBoolean(select, t);
      enhanced.add(select);
    }
    for (const input of scope.querySelectorAll('[data-json-editor]')) {
      if (enhanced.has(input)) continue;
      enhanceJSON(input, t);
      enhanced.add(input);
    }
    return () => cleanups.forEach(cleanup => cleanup());
  }
  root.QuiteAdmin = {...root.QuiteAdmin, createFieldControl};
  root.quiteAdminEnhanceFields = enhance;
  enhance(doc);

})(typeof window !== 'undefined' ? window : globalThis);
