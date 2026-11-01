/* Progressive list behavior; no record values are persisted. */
(function () {
  const form = document.querySelector('.list-query-form');
  if (!form) return;
  const input = form.querySelector('input[name=q]');
  if (!input) return;
  let timer, composing = false;
  const initial = input.value;
  const key = 'quite-admin:search-focus:' + location.pathname;
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
})();
