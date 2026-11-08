/* Home uses authorized catalog metadata; it never requests table records. */
(() => {
  function init(root = document) {
    const home = root.querySelector('[data-dashboard]');
    const shell = home?.closest('[data-admin-shell]');
    const tables = shell?.quiteAdminTables;
    if (!home || !tables) return () => {};
    if (home.quiteAdminDashboardCleanup) return home.quiteAdminDashboardCleanup;
    let messages = {};
    try { messages = JSON.parse(home.dataset.messages || '{}'); } catch { /* Optional labels. */ }
    const unpinLabel = name => (messages.unpin || 'Unpin table: {name}').replace('{name}', name);
    const removeRecentLabel = name => (messages.removeRecent || 'Remove from recently opened: {name}').replace('{name}', name);
    const pinned = home.querySelector('[data-home-pinned]');
    const recent = home.querySelector('[data-home-recent]');
    if (!pinned || !recent) return () => {};
    function renderCards(target, items, withPin) {
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
        if (withPin) {
          const pin = document.createElement('button');
          pin.type = 'button'; pin.className = 'home-unpin'; pin.dataset.homeUnpin = item.id;
          pin.setAttribute('aria-label', unpinLabel(item.label)); pin.title = unpinLabel(item.label);
          pin.textContent = '★'; card.append(pin);
        } else {
          const remove = document.createElement('button');
          remove.type = 'button'; remove.className = 'home-remove-recent'; remove.dataset.homeRemoveRecent = item.id;
          remove.setAttribute('aria-label', removeRecentLabel(item.label)); remove.title = removeRecentLabel(item.label);
          remove.textContent = '×'; card.append(remove);
        }
        return card;
      }));
    }
    function render() {
      const pins = tables.pins(), visits = tables.recent().slice(0, 6);
      renderCards(pinned, pins, true); renderCards(recent, visits, false);
      home.querySelector('[data-home-pinned-empty]').hidden = pins.length > 0;
      home.querySelector('[data-home-recent-empty]').hidden = visits.length > 0;
      home.querySelector('[data-home-pinned-section]').hidden = false;
      home.querySelector('[data-home-recent-section]').hidden = false;
    }
    function click(event) {
      const remove = event.target.closest('[data-home-remove-recent]');
      if (remove && recent.contains(remove)) {
        event.preventDefault();
        const index = [...recent.querySelectorAll('[data-home-remove-recent]')].indexOf(remove);
        tables.removeRecent(remove.dataset.homeRemoveRecent);
        const buttons = recent.querySelectorAll('[data-home-remove-recent]');
        (buttons[Math.min(index, buttons.length - 1)] || home.querySelector('[data-table-search]'))?.focus();
        return;
      }
      const pin = event.target.closest('[data-home-unpin]');
      if (!pin || !home.contains(pin)) return;
      const index = [...pinned.querySelectorAll('[data-home-unpin]')].indexOf(pin);
      tables.togglePin(pin.dataset.homeUnpin);
      const buttons = pinned.querySelectorAll('[data-home-unpin]');
      (buttons[Math.min(index, buttons.length - 1)] || home.querySelector('[data-table-search]')).focus();
    }
    const nativeHelp = home.querySelector('[data-home-native-help]');
    if (nativeHelp) nativeHelp.hidden = true;
    home.addEventListener('click', click);
    shell.addEventListener('quite-admin:tables-change', render);
    render();
    const cleanup = () => {
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
