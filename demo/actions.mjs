// Local showcase commands. Python handlers and database transactions run in the ASGI example.
export function bulkCommands(collection) {
  const commands = [];
  if (collection.canDelete !== false && collection.bulkDelete !== false)
    commands.push({slug:'delete', label:'Delete selected records'});
  if (collection.canEdit !== false)
    commands.push(...(collection.bulkActions || []).map(action => ({...action, slug:'action:' + action.slug})));
  return commands;
}

export function bulkPanel(collection, {t, e}) {
  const commands = bulkCommands(collection);
  if (!commands.length) return '';
  return `<details class="bulk-panel" data-bulk-panel>
    <summary class="button secondary icon-button" title="${e(t('Bulk actions'))}" aria-label="${e(t('Bulk actions'))}"><svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M9 6h12M9 12h12M9 18h12M3 6h2M3 12h2M3 18h2"/></svg><span class="bulk-badge" data-bulk-selected aria-hidden="true" hidden></span></summary>
    <form id="bulk-actions" class="bulk-toolbar" data-bulk-form>
      <label for="bulk-action">${e(t('With selected'))}</label><select id="bulk-action" name="action">${commands.map(action => `<option value="${e(action.slug)}">${e(t(action.label))}</option>`).join('')}</select>
      <span class="muted" data-bulk-count data-label="${e(t('Selected records: {count}', {count:'{count}'}))}" aria-live="polite">${e(t('Selected records: {count}', {count:0}))}</span>
      <button class="button secondary" type="submit">${e(t('Continue'))}</button>
    </form>
  </details>`;
}

export function runRecordAction(store, slug, key, actionSlug, revision, bulk = false) {
  const collection = store.collection(slug);
  const action = (bulk ? collection.bulkActions : collection.actions)?.find(item => item.slug === actionSlug);
  if (!action?.effect || !Object.keys(action.effect).length) throw new Error('Unknown action.');
  return store.save(slug, key, action.effect, {}, revision, 'action:' + action.slug);
}

export function runBulk(store, pending) {
  const keys = [...new Set(pending.keys)];
  if (!keys.length || keys.length > 100) throw new Error('Select between 1 and 100 records.');
  if (!bulkCommands(store.collection(pending.slug)).some(action => action.slug === pending.action))
    throw new Error('Unknown action.');
  return keys.map(key => {
    const label = pending.labels[key];
    try {
      if (store.revision(pending.slug,key) !== pending.revisions[key])
        throw new Error('This record changed after you opened it. Your changes have not been saved. Reload the record and review the latest values.');
      if (pending.action === 'delete') store.delete(pending.slug, key);
      else runRecordAction(store, pending.slug, key, pending.action.slice(7), pending.revisions[key], true);
      return {label, success:true, message:'Success'};
    } catch (error) {
      return {label, success:false, message:error.message};
    }
  });
}

export function bulkPage(pending, results, {t, e}) {
  if (!pending) return `<div class="page-heading"><h1>${e(t('Confirm bulk action'))}</h1></div><p>${e(t('Select records from a table to continue.'))}</p>`;
  const back = `<a class="button secondary" href="${e(pending.back)}">${e(t(results ? 'Back to records' : 'Cancel'))}</a>`;
  const title = t(results ? 'Bulk action results' : 'Confirm bulk action');
  if (results) return `<div class="page-heading"><h1>${e(title)}</h1></div><p role="status">${e(t('Succeeded: {count}', {count:results.filter(item => item.success).length}))} · ${e(t('Failed: {count}', {count:results.filter(item => !item.success).length}))}</p><div class="table-scroll"><table><thead><tr><th>${e(t('Record'))}</th><th>${e(t('Result'))}</th></tr></thead><tbody>${results.map(item => `<tr><td>${e(item.label)}</td><td class="${item.success ? '' : 'field-error'}">${e(t(item.message))}</td></tr>`).join('')}</tbody></table></div><p>${back}</p>`;
  return `<div class="page-heading"><h1>${e(title)}</h1></div><section class="panel bulk-confirmation"><h2>${e(t(pending.label))}</h2><p>${e(t('Selected records: {count}', {count:pending.keys.length}))}</p><p class="field-help">${e(t('Each record is processed separately. Successful changes remain saved if another record fails.'))}</p><ul>${pending.keys.map(key => `<li>${e(pending.labels[key])}</li>`).join('')}</ul><form id="demo-bulk-confirm"><div class="button-group">${back}<button class="button danger" type="submit">${e(t('Confirm action'))}</button></div></form></section>`;
}
