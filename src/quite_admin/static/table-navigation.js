/* Authorized metadata only. Browser storage contains table slugs, never searches or records. */
(function () {
  const initialized = new WeakMap(), live = new Set();
  const RESULT_LIMIT = 60, RECENT_LIMIT = 8, PIN_LIMIT = 12;
  const normalize = value => String(value).normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().trim();
  const defaults = {search: 'Search tables', close: 'Close', tables: 'Tables', empty: 'No matching tables.',
    count: 'Matching tables: {count}', more: 'Showing first {count} matches. Refine your search.',
    pin: 'Pin table: {name}', unpin: 'Unpin table: {name}', pinLimit: 'Pin up to {count} tables.'};
  const parse = (value, fallback) => { try { return JSON.parse(value); } catch (_) { return fallback; } };

  function setup(shell) {
    const directory = shell.querySelector('[data-table-directory]');
    const dialog = shell.querySelector('[data-table-search-dialog]');
    if (!directory || !dialog || typeof dialog.showModal !== 'function') return null;
    const input = dialog.querySelector('[data-table-search-input]');
    const results = dialog.querySelector('[data-table-search-results]');
    const count = dialog.querySelector('[data-table-search-count]');
    const more = dialog.querySelector('[data-table-search-more]');
    const notice = dialog.querySelector('[data-table-search-notice]');
    if (!input || !results || !count || !more || !notice) return null;
    const messages = {...defaults, ...parse(directory.dataset.messages, {})};
    const rawCatalog = parse(directory.dataset.catalog, []);
    const byId = new Map();
    for (const item of Array.isArray(rawCatalog) ? rawCatalog : []) {
      if (!item || !['id', 'name', 'label', 'group', 'url'].every(key => typeof item[key] === 'string') || !item.id || byId.has(item.id)) continue;
      // Server URLs are local admin routes; reject executable/foreign URLs if metadata is malformed.
      let target;
      try { target = new URL(item.url, location.href); } catch (_) { continue; }
      if (!['http:', 'https:'].includes(target.protocol) || target.origin !== location.origin) continue;
      byId.set(item.id, {id: item.id, name: item.name, label: item.label, group: item.group, url: item.url});
    }
    const catalog = [...byId.values()];
    const indexed = catalog.map(item => ({item, text: normalize([item.label, item.name, item.group].join(' '))}));
    const scope = JSON.stringify([shell.dataset.storageKey || '/', shell.dataset.userKey || '']);
    const storageKey = 'quite-admin:tables:' + scope;
    const controller = new AbortController(), signal = controller.signal;
    const buttons = [...shell.querySelectorAll('[data-table-search]')];
    const copy = items => items.map(item => ({...item}));
    const format = (key, values = {}) => Object.entries(values).reduce((text, [name, value]) => text.replaceAll('{' + name + '}', String(value)), messages[key]);
    let memory = {recent: [], pins: [], groups: []}, storageAvailable = true;
    let previousFocus = null, activeIndex = 0;

    function cleanIds(value, limit) {
      return [...new Set((Array.isArray(value) ? value : []).filter(id => typeof id === 'string' && byId.has(id)))].slice(0, limit);
    }
    function sanitize(value) {
      return {recent: cleanIds(value?.recent, RECENT_LIMIT), pins: cleanIds(value?.pins, PIN_LIMIT), groups: cleanIds(value?.groups, catalog.length)};
    }
    function read() {
      if (storageAvailable) {
        try {
          const raw = localStorage.getItem(storageKey);
          if (raw === null) memory = {recent: [], pins: [], groups: []};
          else if (raw.length <= 1000000) {
            const saved = parse(raw, null);
            if (saved && typeof saved === 'object' && !Array.isArray(saved)) memory = sanitize(saved);
          }
        } catch (_) { storageAvailable = false; }
      }
      memory = sanitize(memory);
      return {...memory, recent: [...memory.recent], pins: [...memory.pins], groups: [...memory.groups]};
    }
    function changed() {
      shell.dispatchEvent(new CustomEvent('quite-admin:tables-change', {bubbles: true}));
    }
    function save(value, notify = true) {
      memory = sanitize(value);
      if (storageAvailable) {
        try { localStorage.setItem(storageKey, JSON.stringify(memory)); }
        catch (_) { storageAvailable = false; }
      }
      if (notify) changed();
    }
    const metadata = kind => copy(read()[kind].map(id => byId.get(id)));
    function remember(id) {
      if (!byId.has(id)) return metadata('recent');
      const state = read();
      if (state.recent[0] !== id) save({...state, recent: [id, ...state.recent.filter(value => value !== id)]});
      return metadata('recent');
    }
    function removeRecent(id) {
      const state = read();
      if (state.recent.includes(id)) save({...state, recent: state.recent.filter(value => value !== id)});
      return metadata('recent');
    }
    function togglePin(id) {
      const state = read();
      if (!byId.has(id)) return metadata('pins');
      notice.hidden = true;
      for (const status of shell.querySelectorAll('[data-table-pin-notice]')) { status.hidden = true; status.textContent = ''; }
      if (state.pins.includes(id)) save({...state, pins: state.pins.filter(value => value !== id)});
      else if (state.pins.length < PIN_LIMIT) save({...state, pins: [...state.pins, id]});
      else {
        notice.textContent = format('pinLimit', {count: PIN_LIMIT});
        notice.hidden = false;
        for (const status of shell.querySelectorAll('[data-table-pin-notice]')) {
          status.textContent = notice.textContent; status.hidden = false;
        }
      }
      return metadata('pins');
    }
    function starIcon() {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      for (const [name, value] of Object.entries({'data-table-pin-icon': '', width: '20', height: '20', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.6', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false'})) svg.setAttribute(name, value);
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', 'm12 3 2.78 5.63 6.22.9-4.5 4.39 1.06 6.2L12 17.19l-5.56 2.93 1.06-6.2L3 9.53l6.22-.9Z');
      svg.append(path); return svg;
    }
    function updatePins() {
      const pins = new Set(read().pins);
      for (const button of shell.querySelectorAll('button[data-table-pin]')) {
        const item = byId.get(button.dataset.tablePin);
        if (!item) { button.hidden = true; continue; }
        const pinned = pins.has(item.id);
        button.type = 'button'; button.hidden = false; button.classList.add('table-pin');
        if (!button.querySelector('svg[data-table-pin-icon]')) button.replaceChildren(starIcon());
        button.setAttribute('aria-pressed', String(pinned));
        button.setAttribute('aria-label', format(pinned ? 'unpin' : 'pin', {name: item.label}));
        button.title = button.getAttribute('aria-label');
      }
    }
    function render() {
      const terms = normalize(input.value).split(/\s+/).filter(Boolean);
      const matches = indexed.filter(({text}) => terms.every(term => text.includes(term)));
      const fragment = document.createDocumentFragment();
      for (const {item} of matches.slice(0, RESULT_LIMIT)) {
        const row = document.createElement('li'); row.className = 'table-search-result';
        const link = document.createElement('a'); link.href = item.url; link.dataset.tableLink = item.id;
        if (item.id === shell.dataset.currentTable) link.setAttribute('aria-current', 'page');
        const label = document.createElement('span'); label.className = 'table-search-result-label'; label.textContent = item.label;
        const meta = document.createElement('span'); meta.className = 'table-search-result-meta'; meta.textContent = item.name + ' · ' + item.group;
        link.append(label, meta);
        const pin = document.createElement('button'); pin.type = 'button'; pin.className = 'table-search-pin'; pin.dataset.tablePin = item.id;
        row.append(link, pin); fragment.append(row);
      }
      results.replaceChildren(fragment); activeIndex = 0; results.scrollTop = 0;
      count.textContent = matches.length ? format('count', {count: matches.length}) : messages.empty;
      more.hidden = matches.length <= RESULT_LIMIT;
      more.textContent = more.hidden ? '' : format('more', {count: RESULT_LIMIT});
      notice.hidden = true;
      updatePins();
    }
    function focusResult(index) {
      const links = results.querySelectorAll('a[data-table-link]');
      if (!links.length) { input.focus(); return; }
      activeIndex = (index + links.length) % links.length;
      links[activeIndex].focus({preventScroll: true});
      links[activeIndex].scrollIntoView({block: 'nearest'});
    }
    function openSearch(query = '', opener = document.activeElement) {
      if (document.querySelector('dialog[open]:not([data-table-search-dialog])')) return;
      if (!dialog.open) {
        previousFocus = opener;
        input.value = String(query);
        render();
        dialog.showModal();
      } else if (query) { input.value = String(query); render(); }
      input.focus(); input.select();
    }
    const api = {catalog: () => copy(catalog), recent: () => metadata('recent'), pins: () => metadata('pins'), remember, removeRecent, togglePin, openSearch};
    shell.quiteAdminTables = api;
    // Keep global search independent of the current page's collapsible catalog.
    shell.append(dialog);
    for (const button of buttons) {
      button.hidden = false;
      button.addEventListener('click', event => { event.preventDefault(); openSearch('', button); }, {signal});
    }
    input.addEventListener('input', render, {signal});
    dialog.querySelector('[data-table-search-close]')?.addEventListener('click', () => dialog.close(), {signal});
    dialog.addEventListener('close', () => {
      // A rapid shortcut may reopen the dialog before the previous close event runs.
      if (dialog.open) return;
      input.value = ''; results.replaceChildren();
      if (previousFocus === null) return;
      const opener = previousFocus?.isConnected && previousFocus !== document.body && previousFocus !== document.documentElement && !previousFocus.closest('[inert]') && previousFocus.getClientRects().length ? previousFocus : shell.querySelector('a[data-home-link], a.sidebar-home');
      opener?.focus({preventScroll: true});
      previousFocus = null;
    }, {signal});
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); }, {signal});
    dialog.addEventListener('keydown', event => {
      if (event.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); dialog.close(); return; }
      const row = event.target.closest('.table-search-result');
      const rows = [...results.children];
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const index = row ? rows.indexOf(row) : event.key === 'ArrowDown' ? -1 : 0;
        focusResult(index + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Enter' && event.target === input) {
        event.preventDefault(); results.querySelectorAll('a[data-table-link]')[activeIndex]?.click();
      }
    }, {signal});
    shell.addEventListener('click', event => {
      const link = event.target.closest('a[data-table-link]');
      if (link && shell.contains(link)) remember(link.dataset.tableLink);
      const pin = event.target.closest('[data-table-pin]');
      if (pin?.matches('button[data-table-pin]') && shell.contains(pin) && byId.has(pin.dataset.tablePin)) {
        event.preventDefault(); togglePin(pin.dataset.tablePin);
      }
    }, {signal});
    shell.addEventListener('quite-admin:tables-change', updatePins, {signal});
    document.addEventListener('keydown', event => {
      if (!shell.isConnected || event.defaultPrevented || event.repeat || event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'k') return;
      const focusedShell = document.activeElement?.closest('[data-admin-shell]');
      if ((focusedShell && focusedShell !== shell) || (!focusedShell && document.querySelector('[data-admin-shell]') !== shell)) return;
      if (document.querySelector('dialog[open]:not([data-table-search-dialog])')) return;
      event.preventDefault(); openSearch();
    }, {signal});
    window.addEventListener('storage', event => { if (event.key === storageKey || event.key === null) changed(); }, {signal});
    const openGroups = new Set(read().groups);
    for (const group of shell.querySelectorAll('[data-collection-navigation] [data-group]')) {
      const id = group.querySelector('a[data-table-link]')?.dataset.tableLink;
      if (!byId.has(id)) continue;
      if (!group.hasAttribute('data-current-group')) group.open = openGroups.has(id);
      group.querySelector('summary')?.addEventListener('click', () => {
        const state = read();
        save({...state, groups: group.open ? state.groups.filter(value => value !== id) : [...state.groups, id]}, false);
      }, {signal});
    }
    remember(shell.dataset.currentTable);
    updatePins();
    function cleanup() {
      controller.abort();
      if (dialog.open) dialog.close();
      if (shell.quiteAdminTables === api) delete shell.quiteAdminTables;
      for (const button of buttons) button.hidden = true;
      initialized.delete(shell); live.delete(state);
    }
    const state = {shell, cleanup};
    return state;
  }

  function init(root = document) {
    for (const state of live) if (!state.shell.isConnected) state.cleanup();
    const shells = root.matches?.('[data-admin-shell]') ? [root] : root.querySelectorAll('[data-admin-shell]');
    const states = [];
    for (const shell of shells) {
      let state = initialized.get(shell);
      if (!state) {
        state = setup(shell);
        if (state) { initialized.set(shell, state); live.add(state); }
      }
      if (state) states.push(state);
    }
    return () => states.forEach(state => { if (initialized.get(state.shell) === state) state.cleanup(); });
  }
  window.quiteAdminInitTables = init;
  init();
})();
