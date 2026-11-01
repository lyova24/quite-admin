/* Progressive list behavior; no record values are persisted. */
(function () {
  function enhance(scope = document, storageKey = location.pathname) {
  const form = scope.querySelector('.list-query-form');
  if (!form) return () => {};
  const input = form.querySelector('input[name=q]');
  if (!input) return () => {};
  let timer, composing = false;
  const initial = input.value;
  const key = 'quite-admin:search-focus:' + storageKey;
  try {
    if (sessionStorage.getItem(key)) { sessionStorage.removeItem(key); input.focus({preventScroll:true}); input.setSelectionRange(input.value.length,input.value.length); }
  } catch (_) { /* Storage can be disabled. */ }
  function submit() {
    clearTimeout(timer);
    if (composing || input.value === initial) return;
    try { sessionStorage.setItem(key,'1'); } catch (_) { /* Optional focus restoration. */ }
    form.requestSubmit();
  }
  input.addEventListener('input', () => { clearTimeout(timer); if(!composing) timer=setTimeout(submit,900); });
  input.addEventListener('compositionstart', () => {composing=true;clearTimeout(timer);});
  input.addEventListener('compositionend', () => {composing=false;clearTimeout(timer);timer=setTimeout(submit,900);});
  input.addEventListener('keydown', e => {if(e.key==='Enter' && !composing){e.preventDefault();submit();}});
  form.addEventListener('submit', () => clearTimeout(timer));
  form.addEventListener('quite-admin:filter-open', () => clearTimeout(timer));
  form.addEventListener('quite-admin:filter-close', () => {if(input.value!==initial)timer=setTimeout(submit,900);});
  const lifetime = new AbortController();
  const exporter = scope.querySelector('.export-panel');
  if (exporter) {
    exporter.addEventListener('keydown', e => {if(e.key==='Escape'){exporter.open=false;exporter.querySelector('summary').focus();}});
    document.addEventListener('click', e => {if(!exporter.contains(e.target))exporter.open=false;}, {signal:lifetime.signal});
    exporter.querySelector('form').addEventListener('submit', () => {
      clearTimeout(timer);
      let search = exporter.querySelector('input[name=q]');
      if(!search){search=document.createElement('input');search.type='hidden';search.name='q';exporter.querySelector('form').append(search);}
      search.value=input.value;
    });
  }
  return () => {clearTimeout(timer);lifetime.abort();};
  }
  window.quiteAdminEnhanceListing = enhance;
  enhance();
})();
