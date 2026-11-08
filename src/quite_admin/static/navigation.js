/* Only collection-group state is persisted, scoped to this admin mount. */
(function () {
  for (const nav of document.querySelectorAll('[data-collection-navigation]')) {
    for (const group of nav.querySelectorAll('[data-group]')) {
      const key = 'quite-admin:group:' + nav.dataset.storageKey + ':' + group.dataset.group;
      try { if (!group.hasAttribute('data-current-group')) group.open = localStorage.getItem(key) === 'open'; } catch (_) { /* Storage may be disabled. */ }
      group.querySelector('summary').addEventListener('click', () => {
        try { localStorage.setItem(key, group.open ? 'closed' : 'open'); } catch (_) { /* Native details still work. */ }
      });
    }
  }
})();
