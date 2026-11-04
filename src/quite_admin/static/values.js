/* Value helpers use local DOM text only. No persistence, external requests or HTML parsing. */
(function () {
  function update(root, model) {
    if (!root) return;
    let element, source;
    if (!model.text) {
      element = source = document.createElement('span');
      element.className = 'null-value';element.textContent = '—';
    } else if (model.kind === 'url') {
      element = source = document.createElement(model.href ? 'a' : 'span');
      element.className = 'value-url'; element.textContent = model.text;
      if (model.href) {element.href=model.href;element.target='_blank';element.rel='noopener noreferrer';element.title=model.text;}
    } else {
      source = document.createElement('pre');source.className='value-pre';source.textContent=model.text;
      element = source;
      if (model.expandable) {
        element = document.createElement('details');element.className='value-details';
        const summary = document.createElement('summary');
        const label = document.createElement('span');label.className='sr-only';label.textContent=root.dataset.expandLabel+': ';
        summary.append(label,document.createTextNode(model.preview));element.append(summary,source);
      }
    }
    source.setAttribute('data-copy-source','');
    root.querySelector('.value-content').replaceChildren(element);
    root.dataset.empty = String(!model.text);
    root.querySelector('[data-copy-value]').hidden = !model.text;
    root.querySelector('[data-copy-status]').textContent = '';
  }
  function enhance(scope = document) {
    for (const button of scope.querySelectorAll('[data-copy-value]')) {
      if (button.dataset.copyReady) continue;
      button.dataset.copyReady = 'true';
      button.hidden = button.closest('[data-field-display]').dataset.empty === 'true';
      button.addEventListener('click', async () => {
        const root = button.closest('[data-field-display]');
        const source = root.querySelector('[data-copy-source]');
        const status = root.querySelector('[data-copy-status]');
        try {
          await navigator.clipboard.writeText(source.textContent);
          status.textContent = button.dataset.copied;
        } catch (_) {
          const details = source.closest('details');
          if (details) details.open = true;
          const range = document.createRange();
          range.selectNodeContents(source);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          status.textContent = button.dataset.copyFailed;
        }
      });
    }
  }
  window.quiteAdminEnhanceValues = enhance;
  window.quiteAdminUpdateValue = update;
  enhance();
})();
