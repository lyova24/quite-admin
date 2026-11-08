/* The fixed rail has no stored layout state; only the native profile is enhanced. */
(function () {
  const initialized = new WeakMap();
  function init(root = document) {
    const shells = root.matches?.('[data-admin-shell]') ? [root] : root.querySelectorAll('[data-admin-shell]');
    for (const shell of shells) {
      const profile = shell.querySelector('[data-sidebar-profile]');
      const toggle = profile?.querySelector('[data-profile-toggle]');
      if (!profile || !toggle || initialized.has(shell)) continue;
      const controller = new AbortController(), signal = controller.signal;
      function close(restoreFocus = false) {
        if (!profile.open) return;
        profile.open = false;
        toggle.setAttribute('aria-expanded', 'false');
        if (restoreFocus) toggle.focus({preventScroll: true});
      }
      toggle.setAttribute('aria-expanded', String(profile.open));
      toggle.addEventListener('click', () => toggle.focus({preventScroll: true}), {signal});
      profile.addEventListener('toggle', () => toggle.setAttribute('aria-expanded', String(profile.open)), {signal});
      document.addEventListener('focusin', event => {
        if (!profile.contains(event.target)) close();
      }, {signal});
      document.addEventListener('pointerdown', event => {
        if (!profile.contains(event.target)) close();
      }, {signal});
      document.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || event.defaultPrevented || document.querySelector('dialog[open]') || !profile.open) return;
        event.preventDefault(); close(true);
      }, {signal});
      function cleanup() {
        controller.abort(); initialized.delete(shell);
        if (shell.quiteAdminNavigationCleanup === cleanup) delete shell.quiteAdminNavigationCleanup;
      }
      initialized.set(shell, cleanup);
      shell.quiteAdminNavigationCleanup = cleanup;
    }
  }
  window.quiteAdminNavigation = init;
  window.quiteAdminResizeSidebar = () => {};
  init();
})();
