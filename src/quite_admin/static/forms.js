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
    return () => cleanups.forEach(cleanup => cleanup());
  }
  root.quiteAdminEnhanceFields = enhance;
  enhance(doc);

})(typeof window !== 'undefined' ? window : globalThis);
