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

/* A presentation preference only; table names and data never enter browser storage. */
(function () {
  function initSidebarWidths(root = document) {
    for (const shell of root.querySelectorAll('[data-admin-shell]')) {
      const handle = shell.querySelector('[data-sidebar-resizer]');
      const sidebar = shell.querySelector('.sidebar');
      if (!handle || !sidebar || handle.dataset.ready) continue;
      handle.dataset.ready = 'true';
      handle.hidden = false;
      const key = 'quite-admin:sidebar-width:' + shell.dataset.storageKey;
      const property = '--sidebar-user-width';
      let drag = null;
      const rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize);
      const limits = () => [10 * rem(), Math.max(10 * rem(), Math.min(32 * rem(), innerWidth * .45))];
      function updateAria() {
        const [min, max] = limits();
        handle.setAttribute('aria-valuemin', Math.round(min));
        handle.setAttribute('aria-valuemax', Math.round(max));
        handle.setAttribute('aria-valuenow', Math.round(sidebar.getBoundingClientRect().width));
      }
      function save() {
        try {
          const value = shell.style.getPropertyValue(property);
          if (value) localStorage.setItem(key, value);
          else localStorage.removeItem(key);
        } catch (_) { /* Resizing works without storage. */ }
      }
      function resize(width) {
        const [min, max] = limits();
        shell.style.setProperty(property, Math.max(min, Math.min(max, width)) / rem() + 'rem');
        updateAria();
      }
      try {
        const value = localStorage.getItem(key);
        if (/^\d+(\.\d+)?rem$/.test(value || '')) {
          const width = parseFloat(value);
          if (width >= 10 && width <= 32) shell.style.setProperty(property, value);
        }
      } catch (_) { /* Keep the theme's default width. */ }
      function finish(cancel = false) {
        if (!drag) return;
        if (cancel) {
          if (drag.previous) shell.style.setProperty(property, drag.previous);
          else shell.style.removeProperty(property);
        } else save();
        const pointer = drag.pointer;
        drag = null;
        document.documentElement.classList.remove('is-resizing-sidebar');
        if (handle.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer);
        updateAria();
      }
      handle.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        event.preventDefault();
        handle.focus({preventScroll: true});
        drag = {pointer: event.pointerId, x: event.clientX, width: sidebar.getBoundingClientRect().width,
          previous: shell.style.getPropertyValue(property)};
        handle.setPointerCapture(event.pointerId);
        document.documentElement.classList.add('is-resizing-sidebar');
      });
      handle.addEventListener('pointermove', event => {
        if (drag?.pointer === event.pointerId) resize(drag.width + event.clientX - drag.x);
      });
      handle.addEventListener('pointerup', () => finish());
      handle.addEventListener('pointercancel', () => finish(true));
      handle.addEventListener('lostpointercapture', () => finish(true));
      handle.addEventListener('dblclick', () => {
        shell.style.removeProperty(property); save(); updateAria();
      });
      handle.addEventListener('keydown', event => {
        if (event.key === 'Escape' && drag) { finish(true); event.preventDefault(); return; }
        const [min, max] = limits();
        const step = rem() * (event.shiftKey ? 4 : 1);
        const current = sidebar.getBoundingClientRect().width;
        const widths = {ArrowLeft: current - step, ArrowRight: current + step, Home: min, End: max};
        if (!(event.key in widths)) return;
        event.preventDefault(); resize(widths[event.key]); save();
      });
      const observer = new ResizeObserver(() => {
        if (!shell.isConnected) { observer.disconnect(); return; }
        updateAria();
      });
      observer.observe(sidebar);
      updateAria();
    }
  }
  window.quiteAdminResizeSidebar = initSidebarWidths;
  initSidebarWidths();
})();
