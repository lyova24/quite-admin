import {renderValue} from './values.mjs';

export function inlineDialog(t, e) {
  const messages = {none:t("None"),loading:t("Loading…"),error:t("Unable to save. Review permissions or reload the list."),conflict:t("The record changed. Reload the list before switching again.")};
  return `<p data-list-save-status class="field-error" role="status" aria-live="polite" hidden></p><dialog class="inline-dialog" data-inline-dialog data-messages="${e(JSON.stringify(messages))}"><form method="dialog"><h2 id="inline-title"></h2><div data-inline-control></div><p data-inline-error class="field-error" role="alert"></p><div class="button-group"><button type="button" class="button secondary" data-inline-cancel>${e(t('Cancel'))}</button><button type="submit" class="button primary" data-inline-save>${e(t('Save changes'))}</button></div></form></dialog>`;
}
export const inlineEndpoint = (slug, key, field) => "./demo-inline?" + new URLSearchParams({slug,key,field});
export function listCell({slug, row, field, editable, t, e}) {
  const value = row.values[field.name], endpoint = e(inlineEndpoint(slug,row.key,field.name));
  if ((field.display && field.display !== 'text') || field.urlTemplate)
    return renderValue(field, value, {compact:true, t, e});
  if (field.kind === "boolean") return `<span class="list-toggle-control" data-list-toggle-control data-value="${value==null?'null':value}" ${editable?`data-toggle-endpoint="${endpoint}"`:''}><button class="boolean-toggle list-boolean-toggle" type="button" role="switch" data-field-label="${e(field.label)}" aria-label="${e(field.label+(value==null?': '+t('None'):''))}" aria-checked="${value==='true'}" ${editable?'':'disabled'} data-list-switch></button><span class="toggle-null-state" ${value==null?'':'hidden'}>${e(t('None'))}</span>${field.nullable&&editable?`<button class="list-null-button" type="button" title="${e(t('None'))}" aria-label="${e(t('None')+': '+field.label)}" aria-pressed="${value==null}" data-list-null>∅</button>`:''}</span>`;
  const text = value ?? "—";
  const content = `<span data-cell-value class="${value==null?'null-value':field.primaryKey?'record-id':'cell-value'}" title="${e(text)}">${e(text.length>90?text.slice(0,87)+'…':text)}</span>`;
  return editable ? `${content}<button class="cell-edit" type="button" data-inline-endpoint="${endpoint}" aria-label="${e(t('Edit field')+': '+field.label)}" title="${e(t('Edit field')+': '+field.label)}"><span class="cell-edit-mark" aria-hidden="true">✎</span></button>` : content;
}
export function exportColumns(collection, store = null) {
  const columns = collection.fields.map(field => ({name:field.name,label:field.label}));
  if (store) for (const relation of collection.relations) {
    const target = store.collection(relation.target);
    for (const field of target.fields)
      columns.push({name:relation.name+'.'+field.name,label:relation.label+' · '+field.label});
  }
  return columns;
}
export function csv(collection, rows, columns, store = null) {
  const quote = value => {
    let text = String(value ?? "");
    if (/^[\s\u0000-\u001f]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"','""') + '"';
  };
  const available = exportColumns(collection, store);
  if (!columns.length || columns.some(name=>!available.some(column=>column.name===name)))
    throw new Error('Choose valid export columns.');
  function value(row, name) {
    if (collection.fields.some(field=>field.name===name)) return row.values[name];
    const relation = collection.relations.find(relation=>name.startsWith(relation.name+'.'));
    const fieldName = name.slice(relation.name.length+1);
    return [...(row.links[relation.name]||[])].sort().map(key=>store.record(relation.target,key).values[fieldName]??'').join('\n');
  }
  return '\uFEFF' + [columns.map(name=>available.find(column=>column.name===name).label), ...rows.map(row=>columns.map(name=>value(row,name)))].map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
}
export function matchingRows(store, slug, query) {
  const c = store.collection(slug), search = (query.get('q') || '').toLowerCase();
  const sort = c.fields.find(field=>field.name===query.get('sort')) || c.fields[0];
  const direction = query.get('direction')==='desc' ? -1 : 1;
  const searchFields = c.searchFields ?? c.fields.filter(field=>field.kind==='string').map(field=>field.name);
  return store.filter(slug, query).filter(row=>!search||searchFields.some(name=>String(row.values[name]??'').toLowerCase().includes(search))).sort((a,b)=>{
    const av=a.values[sort.name],bv=b.values[sort.name];
    if((av==null)!==(bv==null))return av==null?1:-1;
    return direction * (['integer','number'].includes(sort.kind)?Number(av)-Number(bv):String(av??'').localeCompare(String(bv??''))) || a.key.localeCompare(b.key);
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
