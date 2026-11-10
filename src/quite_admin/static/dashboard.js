/* Home uses authorized catalog metadata; it never requests table records. */
(() => {
  function initView(home, shell) {
    const controls = home.querySelector('[data-home-view-controls]');
    const catalog = home.querySelector('[data-home-catalog]');
    const shortcuts = home.querySelector('[data-home-shortcuts]');
    const buttons = [...(controls?.querySelectorAll('[data-home-view-option]') || [])];
    if (!controls || !catalog || !shortcuts || !['cards', 'list'].every(view => buttons.some(button => button.dataset.homeViewOption === view))) return () => {};
    const storageKey = 'quite-admin:home-view:' + JSON.stringify([shell.dataset.storageKey || '/', shell.dataset.userKey || '']);
    let view = 'cards', snapshot = null;
    function select(next, persist = false) {
      next = next === 'list' ? 'list' : 'cards';
      if (next !== view) {
        if (next === 'list') {
          snapshot = [catalog, ...catalog.querySelectorAll('details.home-catalog-group[data-group]')].map(details => [details, details.open]);
          for (const [details] of snapshot) details.open = true;
        } else {
          for (const [details, open] of snapshot || []) details.open = open;
          snapshot = null;
        }
        view = next;
      }
      home.dataset.homeView = view;
      catalog.hidden = view === 'cards';
      shortcuts.hidden = view === 'list';
      for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.homeViewOption === view));
      if (persist) { try { localStorage.setItem(storageKey, view); } catch { /* View switching also works without storage. */ } }
    }
    function click(event) {
      const button = event.target.closest('[data-home-view-option]');
      if (!buttons.includes(button)) return;
      event.preventDefault();
      select(button.dataset.homeViewOption, true);
    }
    function groupClick(event) {
      const summary = event.target.closest('summary');
      // List expansion is temporary; keep the cards catalog's saved groups intact.
      if (view === 'list' && summary?.parentElement.matches('details.home-catalog-group[data-group]')) event.stopPropagation();
    }
    function storage(event) {
      if (event.key === storageKey || event.key === null) select(event.key === null ? 'cards' : event.newValue);
    }
    let saved = 'cards';
    try { saved = localStorage.getItem(storageKey); } catch { /* Default view without browser storage. */ }
    select(saved);
    controls.hidden = false;
    controls.addEventListener('click', click);
    catalog.addEventListener('click', groupClick, true);
    window.addEventListener('storage', storage);
    return () => {
      controls.removeEventListener('click', click);
      catalog.removeEventListener('click', groupClick, true);
      window.removeEventListener('storage', storage);
      select('cards');
      catalog.hidden = false;
      controls.hidden = true;
    };
  }
  function init(root = document) {
    const home = root.querySelector('[data-dashboard]');
    const shell = home?.closest('[data-admin-shell]');
    const tables = shell?.quiteAdminTables;
    if (!home || !tables) return () => {};
    if (home.quiteAdminDashboardCleanup) return home.quiteAdminDashboardCleanup;
    let messages = {};
    try { messages = JSON.parse(home.dataset.messages || '{}'); } catch { /* Optional labels. */ }
    const pinned = home.querySelector('[data-home-pinned]');
    const recent = home.querySelector('[data-home-recent]');
    if (!pinned || !recent) return () => {};
    const search = home.querySelector('[data-table-search]');
    const cleanupView = initView(home, shell);
    const collections = [
      {target: pinned, items: () => tables.pins(), key: 'homeUnpin', selector: '[data-home-unpin]',
        className: 'home-unpin', mark: '★', label: messages.unpin || 'Unpin table: {name}', remove: id => tables.togglePin(id),
        empty: home.querySelector('[data-home-pinned-empty]'), section: home.querySelector('[data-home-pinned-section]')},
      {target: recent, items: () => tables.recent().slice(0, 6), key: 'homeRemoveRecent', selector: '[data-home-remove-recent]',
        className: 'home-remove-recent', mark: '×', label: messages.removeRecent || 'Remove from recently opened: {name}', remove: id => tables.removeRecent(id),
        empty: home.querySelector('[data-home-recent-empty]'), section: home.querySelector('[data-home-recent-section]')},
    ];
    function renderCards(collection, items) {
      const {target, ids} = collection;
      if (ids && ids.length === items.length && items.every((item, index) => item.id === ids[index])) return;
      collection.ids = items.map(item => item.id);
      target.replaceChildren(...items.map(item => {
        const card = document.createElement('div');
        card.className = 'home-table-card';
        const link = document.createElement('a');
        link.href = item.url;
        link.dataset.homeTable = item.id;
        const label = document.createElement('strong'); label.textContent = item.label;
        const group = document.createElement('span'); group.textContent = item.group;
        const name = document.createElement('code'); name.textContent = item.name;
        link.append(label, group, name); card.append(link);
        const button = document.createElement('button');
        button.type = 'button'; button.className = collection.className; button.dataset[collection.key] = item.id;
        button.title = collection.label.replace('{name}', item.label);
        button.setAttribute('aria-label', button.title);
        button.textContent = collection.mark; card.append(button);
        return card;
      }));
    }
    function render() {
      for (const collection of collections) {
        const items = collection.items();
        renderCards(collection, items);
        collection.empty.hidden = items.length > 0;
        collection.section.hidden = false;
      }
    }
    function click(event) {
      for (const collection of collections) {
        const button = event.target.closest(collection.selector);
        if (!button || !collection.target.contains(button)) continue;
        event.preventDefault();
        const index = [...collection.target.querySelectorAll(collection.selector)].indexOf(button);
        collection.remove(button.dataset[collection.key]);
        const buttons = collection.target.querySelectorAll(collection.selector);
        (buttons[Math.min(index, buttons.length - 1)] || search)?.focus();
        return;
      }
    }
    const nativeHelp = home.querySelector('[data-home-native-help]');
    if (nativeHelp) nativeHelp.hidden = true;
    home.addEventListener('click', click);
    shell.addEventListener('quite-admin:tables-change', render);
    render();
    const cleanup = () => {
      cleanupView();
      home.removeEventListener('click', click);
      shell.removeEventListener('quite-admin:tables-change', render);
      delete home.quiteAdminDashboardCleanup;
    };
    home.quiteAdminDashboardCleanup = cleanup;
    return cleanup;
  }
  window.quiteAdminDashboard = init;
  init();
})();
