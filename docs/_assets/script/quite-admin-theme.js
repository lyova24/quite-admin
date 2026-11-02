// Diplodoc 5.64's static viewer reads its theme from sessionStorage before rendering.
// prepare-pages.mjs places this script before the viewer and the first content paint.
(() => {
  let theme = 'dark';
  try {
    const selected = sessionStorage.getItem('theme');
    if (selected === 'light' || selected === 'dark') {
      theme = selected;
    } else {
      sessionStorage.setItem('theme', theme);
    }
  } catch {
    // Keep the document usable when browser storage is unavailable.
  }
  document.body.classList.toggle('g-root_theme_dark', theme === 'dark');
  document.body.classList.toggle('g-root_theme_light', theme === 'light');
})();
