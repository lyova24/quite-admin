export function inlineDialog(t, e) {
  const messages = {none:t("None"),loading:t("Loading…"),error:t("Unable to save. Review permissions or reload the list."),conflict:t("The record changed. Reload the list before switching again.")};
  return `<p data-list-save-status class="field-error" role="status" aria-live="polite" hidden></p><dialog class="inline-dialog" data-inline-dialog data-messages="${e(JSON.stringify(messages))}"><form method="dialog"><h2 id="inline-title"></h2><div data-inline-control></div><p data-inline-error class="field-error" role="alert"></p><div class="button-group"><button type="button" class="button secondary" data-inline-cancel>${e(t('Cancel'))}</button><button type="submit" class="button primary" data-inline-save>${e(t('Save changes'))}</button></div></form></dialog>`;
}
export const inlineEndpoint = (slug, key, field) => "./demo-inline?" + new URLSearchParams({slug,key,field});
export function listCell({slug, row, field, editable, t, e}) {
  const value = row.values[field.name], endpoint = e(inlineEndpoint(slug,row.key,field.name));
  if (field.kind === "boolean") return `<span class="list-toggle-control" data-list-toggle-control data-value="${value==null?'null':value}" ${editable?`data-toggle-endpoint="${endpoint}"`:''}><button class="boolean-toggle list-boolean-toggle" type="button" role="switch" data-field-label="${e(field.label)}" aria-label="${e(field.label+(value==null?': '+t('None'):''))}" aria-checked="${value==='true'}" ${editable?'':'disabled'} data-list-switch></button><span class="toggle-null-state" ${value==null?'':'hidden'}>${e(t('None'))}</span>${field.nullable&&editable?`<button class="list-null-button" type="button" title="${e(t('None'))}" aria-label="${e(t('None')+': '+field.label)}" aria-pressed="${value==null}" data-list-null>∅</button>`:''}</span>`;
  const text = value ?? "—";
  const content = `<span data-cell-value class="${value==null?'null-value':field.primaryKey?'record-id':'cell-value'}" title="${e(text)}">${e(text.length>90?text.slice(0,87)+'…':text)}</span>`;
  return editable ? `<button class="cell-edit" type="button" data-inline-endpoint="${endpoint}" aria-label="${e(t('Edit field')+': '+field.label)}" title="${e(t('Edit field')+': '+field.label)}">${content}<span class="cell-edit-mark" aria-hidden="true">✎</span></button>` : content;
}
export function csv(collection, rows, columns) {
  const quote = value => {
    let text = String(value ?? "");
    if (/^[\s\u0000-\u001f]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"','""') + '"';
  };
  return '\uFEFF' + [columns.map(name=>collection.fields.find(field=>field.name===name).label), ...rows.map(row=>columns.map(name=>row.values[name]))].map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
}
export function matchingRows(store, slug, query) {
  const c = store.collection(slug), search = (query.get('q') || '').toLowerCase();
  const sort = c.fields.find(field=>field.name===query.get('sort') && (c.pagination!=='cursor'||field.primaryKey)) || c.fields[0];
  const direction = query.get('direction')==='desc' ? -1 : 1;
  return store.filter(slug, query).filter(row=>c.fields.some(field=>field.kind==='string'&&String(row.values[field.name]??'').toLowerCase().includes(search))).sort((a,b)=>{
    const av=a.values[sort.name],bv=b.values[sort.name];
    return direction * (['integer','number'].includes(sort.kind)?Number(av)-Number(bv):String(av??'').localeCompare(String(bv??''))) || Number(a.values.id)-Number(b.values.id);
  });
}
export function listWindow(rows, query, cursor, limit = 5) {
  const page = Math.max(1,Number(query.get('page'))||1);
  let start = (page-1)*limit;
  if(cursor){
    const after=rows.findIndex(row=>row.key===query.get('after')),before=rows.findIndex(row=>row.key===query.get('before'));
    start=after>=0?after+1:before>=0?Math.max(0,before-limit):0;
  }
  return {rows:rows.slice(start,start+limit),hasPrevious:start>0,hasNext:start+limit<rows.length};
}
