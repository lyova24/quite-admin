import { Store } from "./store.mjs";
import { activityPage } from "./activity.mjs";
import { inlineDialog, listCell, csv, exportColumns, matchingRows, listWindow } from "./listing.mjs";
import {renderValue, valueModel} from './values.mjs';
import {bulkCommands, bulkPanel, bulkPage, runBulk, runRecordAction} from './actions.mjs';

const seed = await (await fetch("./seed.json")).json();
const read = (kind, key) => {
  try {
    return window[kind].getItem(key);
  } catch {
    return null;
  }
};
const write = (kind, key, value) => {
  try {
    window[kind].setItem(key, value);
  } catch {
    /* Keep the demo usable in memory when storage is disabled. */
  }
};
let signedIn = read("sessionStorage", "quite-admin-demo-login") === "true";
const storageKey = `quite-admin-browser-demo-${seed.version}`;
let store;
let pendingBulk = null, bulkResults = null;
try {
  store = new Store(seed, JSON.parse(read("localStorage", storageKey)));
} catch {
  store = new Store(seed);
}
const requestedLanguage = new URLSearchParams(location.search).get("lang");
const savedLanguage = read("localStorage", "quite-admin-demo-language");
const language = ["en", "ru"].includes(requestedLanguage) ? requestedLanguage
  : ["en", "ru"].includes(savedLanguage) ? savedLanguage
  : navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en";
const extra = {
  "Catalog": "Каталог", "Sales": "Продажи", "Workspace": "Рабочее пространство",
  "CSV download": "Скачать CSV",
  "Naive local time; microseconds are preserved.": "Время без часового пояса; микросекунды сохраняются.",
  "None means this event is awaiting review.": "None означает, что событие ожидает согласования.",
  "Select records from a table to continue.": "Выберите записи в таблице, чтобы продолжить.",
  "Unknown action.": "Неизвестное действие.",
  "Select between 1 and 100 records.": "Выберите от 1 до 100 записей.",
  "Publish": "Опубликовать", "Archive": "В архив", "Deactivate products": "Деактивировать товары",
};
const t = (text, values = {}) => {
  text = seed.messageAliases?.[text] || text;
  let translated = language === "ru" ? seed.translations[text] || extra[text] || text : text;
  for (const [name,value] of Object.entries(values)) translated = translated.replaceAll("{"+name+"}",value);
  return translated;
};
const records = (count) =>
  `${count} ${language === "ru" ? (count % 100 >= 11 && count % 100 <= 14 ? "записей" : count % 10 === 1 ? "запись" : count % 10 >= 2 && count % 10 <= 4 ? "записи" : "записей") : count === 1 ? "record" : "records"}`;
const display = (collection, name, row) =>
  collection.fields.find((field) => field.name === name)?.kind === "boolean" &&
  row.values[name] != null
    ? t(row.values[name] === "true" ? "True" : "False")
    : (row.values[name] ?? "—");
const e = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const href = (slug, key = "", suffix = "") =>
  `#/models/${encodeURIComponent(slug)}/${key ? encodeURIComponent(key) + suffix : ""}`;
const persist = () =>
  write("localStorage", storageKey, JSON.stringify(store.snapshot()));
const button = (path, text, cls = "secondary") =>
  `<a class="button ${cls}" href="${e(path)}">${e(t(text))}</a>`;
// These controls are serialized, so construct them outside the live document.
const controlDocument = document.implementation.createHTMLDocument("");
const input = (field, value) => {
  const control = window.QuiteAdmin.createFieldControl(
    {...field, max_length: field.maxLength}, {id:'field-' + field.name, value, t, rows:6, ownerDocument:controlDocument});
  if (field.control === 'ticket') control.setAttribute('list','ticket-suggestions');
  return control.outerHTML;
};

function login() {
  return `<main class="shell-login"><div class="content"><section class="login-card"><div class="login-brand"><span class="brand-mark large" aria-hidden="true"></span><h1>${e(seed.title)}</h1></div><form id="demo-login" class="stack"><div><label for="username">${e(t("Username"))}</label><input id="username" name="username" autocomplete="username" required></div><div><label for="password">${e(t("Password"))}</label><input id="password" name="password" type="password" autocomplete="current-password" required></div><p class="demo-error" role="alert" id="login-error"></p><button class="button primary">${e(t("Sign in"))}</button></form></section></div></main>`;
}
function dashboard() {
  return seed.homePages[language];
}

function relationLabel(relation, row) {
  return String(row.values[relation.labelField] ?? store.label(relation.target,row));
}

function relationOptions(relation, term, page) {
  const target = store.collection(relation.target);
  const searchFields = [...new Set([...(target.searchFields ?? target.fields.filter(field => field.kind === 'string').map(field => field.name)), relation.labelField].filter(Boolean))];
  const keys = target.fields.filter(field => field.primaryKey);
  let objectKey;
  try { objectKey = JSON.parse(term); } catch (_) { /* Ordinary text search. */ }
  const rows = target.records.filter(row => !term || searchFields.some(name => String(row.values[name] ?? '').toLowerCase().includes(term.toLowerCase()))
    || keys.length === 1 && row.values[keys[0].name] === term
    || objectKey && typeof objectKey === 'object' && keys.length && keys.every(field => String(objectKey[field.name]) === row.values[field.name]));
  return {items:rows.slice((page - 1) * 25,page * 25).map(row => ({key:row.key,label:relationLabel(relation,row),
    identity:keys.map(field => row.values[field.name]).join(' · '),
    description:searchFields.map(name => row.values[name]).filter(Boolean).join(' · ')})), total:rows.length,has_next:page * 25 < rows.length};
}

function demoFilters(slug, query, queryUrl) {
  const c = store.collection(slug);
  const fields = c.fields.filter((field) => field.nullable || !["json", "binary", "unsupported"].includes(field.kind)).map((field) => ({...field, id: "f." + field.name}));
  fields.push(...c.relations.map((relation) => {
    const key = query.get("r." + relation.name), target = store.collection(relation.target);
    const row = target.records.find((item) => item.key === key);
    return {id: "r." + relation.name, label: relation.label, kind: "relation", endpoint: "./", key_search:true, search_labels:target.fields.filter(f=>f.kind==='string').map(f=>f.label), choices: row ? [[key, store.label(relation.target, row)]] : []};
  }));
  const active = [], consumed = new Set();
  for (const [name, value] of query) {
    if (!value || consumed.has(name)) continue;
    const match = /^f\.(.+)\.(eq|ne|gt|gte|lt|lte|is_null|is_empty|in|on|icontains|not_icontains|istartswith|iendswith)(~[1-9][0-9]?)?$/.exec(name);
    const field = fields.find((field) => field.id === (match ? "f." + match[1] : name));
    if (!field) continue;
    const condition = {id: field.id, operator: match ? match[2] : "eq", parameters: [name], values: [value]};
    const lower = field.id + ".gte" + (match?.[3]||''), upper = field.id + ".lte" + (match?.[3]||'');
    if (["gte", "lte"].includes(condition.operator) && query.get(lower) && query.get(upper)) {
      condition.operator = "between"; condition.parameters = [lower, upper]; condition.values = [query.get(lower), query.get(upper)];
      consumed.add(lower); consumed.add(upper);
      condition.label = field.label + " " + condition.values.join(" – ");
    } else if (field.kind === "relation") condition.label = field.label + ": " + (field.choices[0]?.[1] || "—");
    else condition.label = field.label + " " + (condition.operator === "is_null" ? t(value === "true" ? "Is NULL" : "Is not NULL") : condition.operator === 'is_empty' ? t(value === 'true' ? 'Is empty text' : 'Is not empty text') : (seed.filterMessages[language][condition.operator] || condition.operator) + " " + (field.kind === "boolean" ? t(value === "true" ? "True" : "False") : value));
    condition.remove_url = queryUrl({...Object.fromEntries(condition.parameters.map((key) => [key,null])), page:1});
    active.push(condition);
  }
  const messages = seed.filterMessages[language];
  const clear = Object.fromEntries([...query.keys()].filter((name) => name === "q" || name.startsWith("f.") || name.startsWith("r.")).map((name) => [name,null]));
  return {
    attributes: `data-filter-builder data-fields="${e(JSON.stringify(fields))}" data-conditions="${e(JSON.stringify(active))}" data-messages="${e(JSON.stringify(messages))}"`,
    add: `<button class="button secondary filter-add" type="button" data-filter-add hidden>+ ${e(t("Add filter"))}</button>`,
    panel: '<fieldset class="filter-fallback" data-filter-fallback></fieldset>',
    active: active.length ? `<div class="active-filters">${active.map((item,index) => `<span class="filter-chip filter-condition"><span class="filter-label">${e(item.label)}</span><button class="filter-edit" type="button" data-filter-edit="${index}" hidden>${e(item.label)}</button><a class="filter-remove" aria-label="${e(t("Remove") + ": " + item.label)}" href="${e(item.remove_url)}">×</a></span>`).join("")}<a class="link-button" href="${e(queryUrl({...clear,page:1}))}">${e(t("Clear all"))}</a></div>` : "",
  };
}
function listing(slug, query) {
  const c = store.collection(slug);
  const search = query.get("q") || "";
  const sort = c.fields.find((field) => field.name === query.get("sort")) || c.fields[0];
  const descending = query.get("direction") === "desc";
  const primaryName = c.fields.find((field) => c.columns.includes(field.name) && !field.primaryKey && field.kind === "string")?.name;
  const queryUrl = (updates) => {
    const params = new URLSearchParams(query);
    for (const [name, value] of Object.entries(updates)) { if (value == null) params.delete(name); else params.set(name, value); }
    return href(slug) + "?" + params;
  };
  const filters = demoFilters(slug, query, queryUrl);
  const allRows = matchingRows(store, slug, query), cursor = c.pagination === "cursor";
  const page = Math.max(1, Number(query.get("page")) || 1), limit = 5;
  const total = allRows.length;
  const {rows,hasPrevious,hasNext} = listWindow(allRows,query,cursor,limit);
  const selectable = rows.length > 0 && bulkCommands(c).length > 0;
  const columns = exportColumns(c, store);
  return `<div class="page-heading list-heading"><div class="heading-with-count"><h1>${e(c.label)}</h1>${seed.tablePins[language][slug]}<span class="record-count">${e(cursor?t("{count} on this page",{count:rows.length}):records(total))}</span></div></div>
  ${inlineDialog(t,e)}<section class="record-list"><div class="list-tools"><form id="demo-search" class="list-query-form" ${filters.attributes}><div class="toolbar list-toolbar"><div class="search-form" role="search"><input name="q" aria-label="${e(t("Search records"))}" placeholder="${e(t("Search records…"))}" value="${e(search)}"></div>${filters.add}</div>${filters.panel}</form><div class="list-actions"><details class="export-panel"><summary class="button secondary" aria-label="${e(t('Export data'))}">↓ CSV</summary><form id="demo-export" class="export-form"><p class="field-help">${e(t('Exports all matching records using the current search, filters and sorting. Apply filters before exporting.'))}</p><fieldset><legend>${e(t('Columns'))}</legend><div class="export-columns">${columns.map(field=>`<label class="checkbox-label"><input type="checkbox" name="columns" value="${e(field.name)}" ${c.columns.includes(field.name)?'checked':''}> ${e(field.label)}</label>`).join('')}</div></fieldset><button class="button secondary" type="submit">${e(t('CSV download'))}</button></form></details>${selectable ? bulkPanel(c,{t,e}) : ""}${c.canCreate !== false ? button(href(slug, "new"), "+ " + t("Create record"), "primary list-create") : ""}</div></div>${filters.active}
  ${search ? `<div class="active-filters"><span class="filter-chip">${e(t("Search"))}: ${e(search)}</span><a class="link-button" href="${e(queryUrl({ q: "", page: 1 }))}">${e(t("Clear"))}</a></div>` : ""}
  <div class="table-scroll list-table-scroll"><table aria-label="${e(c.label)}"><thead><tr>${selectable ? `<th class="selection-col" scope="col"><input type="checkbox" data-bulk-all disabled aria-label="${e(t("Select all records on this page"))}"></th>` : ""}${c.columns.map((name) => {
    const field = c.fields.find((field) => field.name === name), active = sort.name === name;
    return `<th scope="col" class="${["integer", "number"].includes(field.kind) ? "numeric" : ""}" ${active ? `aria-sort="${descending ? "descending" : "ascending"}"` : ""}><a href="${e(queryUrl({ sort: name, direction: active && !descending ? "desc" : "asc", page: 1,after:null,before:null }))}">${e(field.label)}<span class="sort-icon" aria-hidden="true">${active ? descending ? "↓" : "↑" : "↕"}</span></a></th>`;
  }).join("")}${c.canDelete !== false ? `<th scope="col" class="delete-col"><span class="sr-only">${e(t("Delete"))}</span></th>` : ""}</tr></thead><tbody>${rows.map((row) => `<tr class="record-row record-row-clickable">${selectable ? `<td class="selection-col"><input type="checkbox" name="keys" value="${e(row.key)}" form="bulk-actions" data-bulk-key aria-label="${e(t("Select record") + ": " + store.label(slug,row))}"></td>` : ""}${c.columns.map((name, index) => {
    const field = c.fields.find((field) => field.name === name), value = row.values[name];
    const relation = c.relations.find(relation => relation.sourceFields.includes(name));
    const linked = relation && row.links[relation.name]?.[0] && store.record(relation.target, row.links[relation.name][0]);
    const content = linked ? `<a class="relation-value" href="${href(relation.target,linked.key)}">${e(store.label(relation.target,linked))}</a>` : listCell({slug,row,field,editable:c.canEdit !== false && c.inline.includes(name),t,e});
    const independent = c.inline.includes(name) || field.kind === "boolean" || field.display || field.urlTemplate || relation;
    return `<td data-list-field="${e(name)}" class="${["integer", "number"].includes(field.kind) ? "numeric" : field.name === primaryName ? "cell-primary" : ""}">${index === 0 ? `<a class="record-row-link" href="${href(slug, row.key)}" aria-label="${e(t("Open record") + ": " + store.label(slug, row))}">${independent?"↗":content}</a>${independent?content:""}` : content}</td>`;
  }).join("")}${c.canDelete !== false ? `<td class="delete-col"><a class="button small danger-outline delete-action" href="${href(slug, row.key, "/delete")}" title="${e(t("Delete record") + ": " + store.label(slug, row))}"><span class="sr-only">${e(t("Delete"))}</span><svg class="action-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></a></td>` : ""}</tr>`).join("") || `<tr><td colspan="${c.columns.length + (c.canDelete !== false ? 1 : 0) + (selectable ? 1 : 0)}"><div class="empty-state"><h2>${e(t(search ? "No matching records" : "No records"))}</h2><p>${e(t(search ? "Try a different search." : "This collection has no records yet."))}</p>${search || c.canCreate !== false ? button(search ? queryUrl({ q: "", page: 1 }) : href(slug, "new"), search ? "Clear" : "Create record") : ""}</div></td></tr>`}</tbody></table></div>
  <footer class="pagination"><span>${e(cursor?t("Browse records"):t("Page {number}",{number:page}))}<span class="pagination-divider">·</span>${e(t("{count} per page").replace("{count}", limit))}</span><div>${hasPrevious ? button(queryUrl(cursor?{before:rows[0].key,after:null}:{page:page-1}), "Previous", "secondary small") : ""}${hasNext ? button(queryUrl(cursor?{after:rows.at(-1).key,before:null}:{page:page+1}), "Next", "secondary small") : ""}</div></footer></section>`;
}
function recordPage(slug, key) {
  const c = store.collection(slug), creating = key === "new";
  if (creating && c.canCreate === false) throw new Error("This table is read only.");
  const row = creating ? { values: {}, links: {} } : store.record(slug, key);
  const managed = c.relations.flatMap((relation) => relation.sourceFields);
  const editable = creating ? c.canCreate !== false : c.canEdit !== false;
  const writable = editable ? c.writable[creating ? "create" : "edit"] : [];
  const fields = c.fields.filter((field) => !managed.includes(field.name) && (!creating || !field.generated))
    .map(field => slug === 'schedules' && ['date','datetime','time'].includes(field.kind)
      ? {...field,label:t(field.label)} : field);
  const renderField = (field) => {
    const editable = writable.includes(field.name), value = row.values[field.name] ?? "";
    return `<div class="form-field ${field.kind === "json" || field.multiline ? "wide" : ""}${editable ? "" : " is-readonly"}"><label id="label-${e(field.name)}" for="field-${e(field.name)}">${e(field.label)} ${editable ? field.nullable ? `<span class="optional-label">${e(t("optional"))}</span>` : "" : `<span class="field-tag">${e(t("Read only"))}</span>`}</label>${editable ? (field.control === "ticket" ? `<div class="demo-ticket-control">${input(field,value)}<datalist id="ticket-suggestions"><option value="DEMO-42"></option><option value="DEMO-73"></option><option value="DEMO-108"></option></datalist></div>` : input(field, value)) : `<div class="readonly-value" id="field-${e(field.name)}" aria-labelledby="label-${e(field.name)}">${field.display || field.urlTemplate ? renderValue(field,value,{t,e}) : e(display(c, field.name, row))}</div>`}${editable && (field.display === "url" || field.urlTemplate) && value ? `<div class="field-url-preview">${renderValue(field,value,{t,e})}</div>` : ""}${field.help?`<p class="field-help">${e(t(field.help))}</p>`:""}${creating && editable && field.hasDefault ? `<label class="checkbox-label"><input type="checkbox" name="__default__${e(field.name)}" checked>${e(t("Use model / database default"))}</label>` : ""}</div>`;
  };
  const section = (title, content, id) => content ? `<section class="form-section${id === "section-readonly" ? " form-section-readonly" : ""}" aria-labelledby="${id}"><h2 id="${id}">${e(t(title))}</h2><div class="form-grid">${content}</div></section>` : "";
  const groups = [
    ["Record fields", fields.filter((f) => writable.includes(f.name) && f.kind !== "json")],
    ["Structured data", fields.filter((f) => writable.includes(f.name) && f.kind === "json")],
  ];
  const pickerMessages = Object.fromEntries(Object.entries({ choose: "Choose records", chooseOne: "Choose a record", change: "Change selection", clear: "Clear selection", search: "Search related records", remove: "Remove", previous: "Previous", next: "Next", loading: "Loading…", empty: "No matching records.", failed: "Could not load records. Try again.", retry: "Retry", selected: "Selected", results: "Results", limit: "Select up to 1000 records." }).map(([key, value]) => [key, t(value)]));
  const relations = c.relations.map((relation) => {
    const selected = row.links[relation.name] || [], multiple = ["one_to_many", "many_to_many"].includes(relation.kind);
    if (!editable || relation.readonly || c.readonlyRelations?.includes(relation.name))
      return `<div class="form-field wide is-readonly"><label>${e(relation.label)} <span class="field-tag">${e(t("Read only"))}</span></label><div class="readonly-value">${selected.map(key => `<a href="${href(relation.target,key)}">${e(store.label(relation.target,store.record(relation.target,key)))}</a>`).join(", ") || "—"}</div></div>`;
    return `<div class="form-field wide"><label for="relation-${e(relation.name)}">${e(relation.label)}</label><div class="relation-picker" data-relation-picker data-endpoint="./" data-relation="${e(relation.name)}" data-messages="${e(JSON.stringify(pickerMessages))}"><select class="picker-native" id="relation-${e(relation.name)}" name="__relation__${e(relation.name)}" aria-describedby="relation-help-${e(relation.name)}" ${multiple ? `multiple size="6"` : ""}>${multiple ? "" : '<option value="">—</option>'}${store.collection(relation.target).records.map((other) => `<option value="${e(other.key)}" ${selected.includes(other.key) ? "selected" : ""}>${e(relationLabel(relation,other))}</option>`).join("")}</select></div><p class="field-help" id="relation-help-${e(relation.name)}">${e(t(multiple ? "Select one or more related records." : "Select one related record."))}</p></div>`;
  }).join("");
  return `<div class="record-editor"><a class="back-link" href="${href(slug)}">← ${e(c.label)}</a><div class="page-heading record-heading"><div><p class="eyebrow">${e(c.label)}</p><h1>${e(creating ? t("Create record") : store.label(slug, row))}</h1></div>${creating || c.canDelete === false ? "" : button(href(slug, key, "/delete"), "Delete record", "danger-outline")}</div><form id="demo-record" class="panel record-form">${creating ? "" : `<input type="hidden" name="__revision" value="${e(store.revision(slug, key))}">`}<div class="alert" role="alert" id="form-error" hidden></div><button id="demo-reload" class="button secondary conflict-reload" type="button" hidden>${e(t("Reload record"))}</button>${groups.map(([heading, fields], index) => section(heading, fields.map(renderField).join(""), `section-${index}`)).join("")}${section("Relationships", relations, "section-relations")}${section("Read-only fields", fields.filter(f => !writable.includes(f.name)).map(renderField).join(""), "section-readonly")}<div class="form-footer"><div class="button-group">${button(href(slug), editable ? "Cancel" : "Back")}${editable ? `<button class="button primary">${e(t(creating ? "Create record" : "Save changes"))}</button>` : ""}</div></div></form>${!creating && editable && c.actions?.length ? `<section class="record-actions"><h2>${e(t("Actions"))}</h2><div class="button-group">${c.actions.map(action => `<form data-demo-action="${e(action.slug)}" data-revision="${e(store.revision(slug,key))}"><button class="button secondary" type="submit">${e(t(action.label))}</button></form>`).join("")}</div></section>` : ""}</div>`;
}
function deletion(slug, key) {
  if (store.collection(slug).canDelete === false) throw new Error("This table is read only.");
  const row = store.record(slug, key);
  return `<div class="page-heading"><h1>${e(t("Delete this record?"))}</h1></div><div class="panel delete-panel"><p>${e(store.label(slug, row))}</p><div class="alert" id="form-error" role="alert" hidden></div><form id="demo-delete"><div class="button-group">${button(href(slug, key), "Keep record")}<button class="button danger">${e(t("Delete permanently"))}</button></div></form></div>`;
}
const shellTemplates = new Map();
function shell(content, slug, key) {
  // Parse each language's real template once; each page mutates its own clone.
  if (!shellTemplates.has(language)) {
    const doc = new DOMParser().parseFromString(seed.shellPages[language], "text/html");
    shellTemplates.set(language, doc.querySelector('[data-admin-shell]'));
  }
  const shell = shellTemplates.get(language).cloneNode(true);
  shell.dataset.storageKey = 'quite-admin-browser-demo';
  shell.dataset.currentTable = slug || '';
  shell.querySelector('.content').innerHTML = content;
  const section = location.hash.split('?')[0] || '#/';
  for (const link of shell.querySelectorAll('a[aria-current]')) link.removeAttribute('aria-current');
  for (const link of shell.querySelectorAll('.active')) link.classList.remove('active');
  const activePath = slug ? href(slug) : section.replace('#/pages/','#/');
  for (const link of shell.querySelectorAll('.sidebar a')) {
    if (link.getAttribute('href') === activePath) {
      link.classList.add('active'); link.setAttribute('aria-current','page');
      const group = link.closest('[data-group]');
      if (group) { group.open = true; group.setAttribute('data-current-group',''); }
    }
  }
  shell.querySelector('.topbar').hidden = section === '#/';
  const c = slug ? store.collection(slug) : null;
  const crumbs = [{label:t('Home'),url:c || section !== '#/' ? '#/' : null}];
  if (c) crumbs.push({label:c.label,url:key ? href(slug) : null});
  if (key) crumbs.push({label:key==='new'?t('Create record'):store.label(slug,store.record(slug,key)),url:null});
  if (section === '#/schema') crumbs.push({label:t('Database schema'),url:null});
  if (section === '#/history') crumbs.push({label:t('Activity history'),url:null});
  shell.querySelector('.breadcrumbs ol').innerHTML = crumbs.map((crumb,index)=>`<li>${index?'<span class="breadcrumb-divider" aria-hidden="true">/</span>':''}${crumb.url?`<a href="${e(crumb.url)}"${index===0?` aria-label="${e(crumb.label)}"`:""}>${e(crumb.label)}</a>`:`<span aria-current="page">${e(crumb.label)}</span>`}</li>`).join('');
  const logout = shell.querySelector('[data-profile-popover] form');
  logout.querySelector('button').id = 'demo-logout';
  logout.removeAttribute('action');
  return shell.outerHTML;
}

function restoreLatest() {
  const saved = read("localStorage", storageKey);
  if (saved) store = new Store(seed, JSON.parse(saved));
}
async function withStoreLock(work) {
  const transaction = () => { restoreLatest(); return work(); };
  return navigator.locks ? navigator.locks.request(storageKey, transaction) : transaction();
}
async function inlineRequest(endpoint, options = {}) {
  const params = new URL(endpoint, location.href).searchParams;
  const slug = params.get("slug"), key = params.get("key"), name = params.get("field");
  const respond = (data,status=200) => new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json"}});
  const operation = () => {
    const c = store.collection(slug), row = store.record(slug,key), field = c.fields.find(field=>field.name===name);
    if(c.canEdit === false || !c.inline.includes(name)) return respond({},403);
    if(options.method !== "POST") return respond({name,label:field.label,kind:field.kind,multiline:field.multiline,nullable:field.nullable,choices:field.choices,max_length:field.maxLength,value:row.values[name]??"",raw_boolean:row.values[name]==null?null:row.values[name]==="true",csrf:"browser-demo",revision:store.revision(slug,key)});
    const data = options.body;
    try {
      store.save(slug,key,{[name]:data.get(name)===""&&field.nullable?null:data.get(name)},{},data.get("__revision"),"inline_edit");
      persist();
      const latest = store.record(slug,key);
      return respond({label_record:t("Open record")+": "+store.label(slug,latest),cells:Object.fromEntries(c.fields.map(field=>[field.name,{text:latest.values[field.name]??"—",null:latest.values[field.name]==null,boolean:latest.values[field.name]==="true",...(field.display || field.urlTemplate ? {display:valueModel(field,latest.values[field.name],{compact:true})} : {})}]))});
    } catch(error) {
      const status=error.message.startsWith("This record changed")?409:422;
      store.log(slug,"inline_edit",key,[],"failure",status);persist();
      return respond({errors:{[name]:t(error.message)}},status);
    }
  };
  return withStoreLock(operation);
}
function initActivity(query) {
  const form = document.querySelector('[data-demo-history]');
  if(!form)return;
  const period = form.querySelector('[data-history-period]');
  period.dataset.today = new Date().toISOString().slice(0,10);
  for (const name of ['date_mode','date','date_from','date_to']) form.elements[name].value = query.get(name) || (name==='date_mode'?'all':'');
  const day = form.elements.date.value, from = form.elements.date_from.value, to = form.elements.date_to.value;
  const dateLabel = value=>value.split('-').reverse().join('.');
  period.querySelector('[data-period-label]').textContent = form.elements.date_mode.value==='day' ? dateLabel(day) : form.elements.date_mode.value==='range'&&(from||to) ? from&&to?dateLabel(from)+' → '+dateLabel(to):t(from?'From {date}':'To {date}',{date:dateLabel(from||to)}) : t('Any date');
  form.navigate = params => {params.delete('page');location.hash='#/history?'+params;};
  form.loadOptions = async (field,{search,page}) => {
    const rows = field.choices.filter(([value,label])=>(value+' '+label).toLowerCase().includes(search.toLowerCase()));
    return {items:rows.slice((page-1)*25,page*25).map(([key,label])=>({key,label,identity:field.id==='subject'?key:''})),has_next:page*25<rows.length};
  };
  cleanupHistory = window.quiteAdminEnhanceHistory(document);
  window.QuiteAdmin.initFilters();
  form.addEventListener('submit',event=>{event.preventDefault();form.navigate(new URLSearchParams(new FormData(form)));});
}
let trackedRoute;
function trackRoute() {
  if(!signedIn || trackedRoute===location.hash)return;
  trackedRoute=location.hash;
  try {
    const [path] = location.hash.slice(1).split('?'), parts=path.split('/').filter(Boolean).map(decodeURIComponent);
    if(parts[0]!=='models'||parts[2]==='new'||parts[3])return;
    restoreLatest();store.log(parts[1],parts[2]?'view':'list',parts[2]||null);persist();
  } catch { /* Invalid hash routes have no record event. */ }
}

let cleanupFields, cleanupInline, cleanupHistory, cleanupListing;
function render() {
  trackRoute();
  document.documentElement.lang = language;
  const loggedIn = signedIn;
  const route = (location.hash.slice(1) || "/").split("?"),
    parts = route[0]
      .split("/")
      .filter(Boolean)
      .map((part) => {
        try {
          return decodeURIComponent(part);
        } catch {
          return "";
        }
      }),
    query = new URLSearchParams(route[1] || "");
  document.body.classList.toggle("listing-page",loggedIn&&parts[0]==="models"&&!parts[2]);
  document.body.classList.toggle("schema-page",loggedIn&&parts[0]==="schema");
  let slug, key, content;
  try {
    if (!loggedIn) content = login();
    else if (parts[0] === "bulk") {
      slug = parts[1];
      content = shell(bulkPage(pendingBulk?.slug === slug ? pendingBulk : null, bulkResults, {t,e}), slug);
    } else if (parts[0] === "models") {
      slug = parts[1];
      key = parts[2];
      content = shell(
        key
          ? parts[3] === "delete"
            ? deletion(slug, key)
            : recordPage(slug, key)
          : listing(slug, query),
        slug,
        key,
      );
    } else if (parts[0] === "history") content = shell(activityPage({store,seed,language,t,e,href,query}));
    else if (parts[0] === "schema") content = shell(seed.schemaPages[language]);
    else content = shell(dashboard());
  } catch (error) {
    content = shell(`<h1>${e(t("Not Found"))}</h1>${button("#/", "Home")}`);
  }
  document.querySelectorAll("[data-schema-workspace]").forEach((root) => root.schemaCleanup?.());
  cleanupInline?.(); cleanupHistory?.(); cleanupListing?.(); cleanupFields?.();
  const previousShell = document.querySelector('[data-admin-shell]');
  previousShell?.quiteAdminNavigationCleanup?.();
  previousShell?.quiteAdminTablesCleanup?.();
  document.querySelector('[data-dashboard]')?.quiteAdminDashboardCleanup?.();
  document.querySelector("#app").innerHTML = content;
  window.quiteAdminInitTables(document);
  window.quiteAdminNavigation(document);
  window.quiteAdminDashboard(document);
  window.quiteAdminEnhanceValues(document);
  const formMessages = document.createElement("div"); formMessages.hidden = true;
  formMessages.setAttribute("data-form-messages", ""); formMessages.dataset.messages = JSON.stringify(seed.formMessages[language]);
  document.querySelector("#app").prepend(formMessages);
  cleanupFields = window.quiteAdminEnhanceFields(document);
  window.QuiteAdmin.initSchemas();
  cleanupInline = window.quiteAdminEnhanceInline(document, inlineRequest);
  initActivity(query);
  if (loggedIn) {
    const marker = document.createElement("div");
    marker.hidden = true;
    marker.setAttribute("data-admin-tour", "");
    marker.dataset.config = JSON.stringify({...seed.tourConfigs[language],
      storageKey: `quite-admin-browser-demo-tour:${location.pathname}:admin`});
    document.querySelector("#app").append(marker);
  }
  window.quiteAdminTour.init(document);
  if (!loggedIn) {
    document.querySelector("#demo-login").onsubmit = (event) => {
      event.preventDefault();
      const data = new FormData(event.target);
      if (
        data.get("username") === "admin" &&
        data.get("password") === "admin"
      ) {
        store.log("","login"); persist();
        signedIn = true;
        write("sessionStorage", "quite-admin-demo-login", "true");
        render();
      } else
        document.querySelector("#login-error").textContent = t(
          "Invalid username or password.",
        );
    };
    return;
  }
  document.querySelector("#demo-logout").onclick = () => {
    store.log("","logout"); persist();
    signedIn = false;
    write("sessionStorage", "quite-admin-demo-login", "false");
    render();
  };
  const search = document.querySelector("#demo-search");
  if (search) {
    search.navigate = (params) => {
      const next = new URLSearchParams(query);
      for (const name of [...next.keys()]) if (name.startsWith("f.") || name.startsWith("r.") || ["before","after","page"].includes(name)) next.delete(name);
      for (const [name,value] of params) next.set(name,value);
      location.hash = href(slug) + "?" + next;
    };
    search.loadOptions = async (field, {search: term, page}) => {
      const relation = store.collection(slug).relations.find((item) => "r." + item.name === field.id);
      return relationOptions(relation,term,page);
    };
    window.QuiteAdmin.initFilters();
  }
  if (search)
    search.onsubmit = (event) => {
      event.preventDefault();
      const params = new URLSearchParams(query);
      for (const name of [...params.keys()]) if (name.startsWith("f.") || name.startsWith("r.")) params.delete(name);
      for (const [name, value] of new FormData(event.target)) if (value) params.set(name, value); else params.delete(name);
      params.set("page", "1"); params.delete("before"); params.delete("after");
      location.hash = href(slug) + "?" + params;
    };
  if (slug) {
    document.querySelectorAll("[data-relation-picker]").forEach((root) => {
      const relation = store.collection(slug).relations.find((item) => item.name === root.dataset.relation);
      root.loadOptions = async ({search, page}) => {
        return relationOptions(relation,search,page);
      };
    });
    window.QuiteAdmin.initRelationPickers();
  }
  cleanupListing = window.quiteAdminEnhanceListing(document, location.pathname + "#/models/" + slug);
  const bulk = document.querySelector('[data-bulk-form]');
  if (bulk) bulk.onsubmit = event => {
    event.preventDefault();
    const data = new FormData(bulk), keys = [...new Set(data.getAll('keys'))];
    if (!keys.length || keys.length > 100) return;
    const command = bulkCommands(store.collection(slug)).find(action => action.slug === data.get('action'));
    if (!command) return;
    pendingBulk = {slug, keys, action:command.slug, label:command.label, back:location.hash,
      labels:Object.fromEntries(keys.map(key => [key,store.label(slug,store.record(slug,key))])),
      revisions:Object.fromEntries(keys.map(key => [key,store.revision(slug,key)]))};
    bulkResults = null;
    location.hash = '#/bulk/' + encodeURIComponent(slug);
  };
  const confirmation = document.querySelector('#demo-bulk-confirm');
  if (confirmation) confirmation.onsubmit = async event => {
    event.preventDefault();
    const button = confirmation.querySelector('button[type=submit]');
    button.disabled = true;
    await withStoreLock(() => {bulkResults = runBulk(store,pendingBulk); persist();});
    render();
  };
  for (const action of document.querySelectorAll('[data-demo-action]')) action.onsubmit = async event => {
    event.preventDefault();
    try {
      await withStoreLock(() => {
        runRecordAction(store,slug,key,action.dataset.demoAction,action.dataset.revision);
        persist();
      });
      render();
    } catch (error) {
      const alert = document.querySelector('#form-error');
      alert.hidden = false; alert.textContent = t(error.message);
    }
  };
  const exportForm = document.querySelector("#demo-export");
  if(exportForm) exportForm.onsubmit = async event => {
    event.preventDefault();
    const data = new FormData(exportForm), columns = data.getAll("columns");
    if(!columns.length)return;
    const exportQuery = new URLSearchParams(query);
    exportQuery.set("q",data.get("q") ?? document.querySelector('#demo-search [name=q]')?.value ?? query.get('q') ?? '');
    const content = await withStoreLock(() => {
      const content = csv(store.collection(slug),matchingRows(store,slug,exportQuery),columns,store);
      store.log(slug,"export");persist();
      return content;
    });
    const blob = new Blob([content],{type:"text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href=url;link.download=slug+".csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  const form = document.querySelector("#demo-record");
  if (form)
    form.onsubmit = async (event) => {
      event.preventDefault();
      const save = () => { try {
        const c = store.collection(slug),
          data = new FormData(form),
          values = {},
          selections = {};
        for (const field of c.fields)
          if (data.has(field.name) && !data.has("__default__" + field.name))
            values[field.name] =
              data.get(field.name) === "" && field.nullable
                ? null
                : field.control === "ticket" ? data.get(field.name).trim().toUpperCase() : data.get(field.name);
        for (const relation of c.relations.filter(relation => form.elements.namedItem("__relation__" + relation.name)))
          selections[relation.name] = data
            .getAll("__relation__" + relation.name)
            .filter(Boolean);
        const restored = read("localStorage", storageKey);
        if (restored) store = new Store(seed, JSON.parse(restored));
        const saved = store.save(
          slug,
          key === "new" ? null : key,
          values,
          selections,
          key === "new" ? null : data.get("__revision"),
        );
        persist();
        if (location.hash === href(slug, saved)) render();
        else location.hash = href(slug, saved);
      } catch (error) {
        const alert = document.querySelector("#form-error");
        alert.hidden = false;
        alert.textContent = t(error.message);
        if (error.message.startsWith("This record changed")) document.querySelector("#demo-reload").hidden = false;
      }};
      if (navigator.locks) await navigator.locks.request(storageKey, save);
      else save();
    };
  const reload = document.querySelector("#demo-reload");
  if (reload) reload.onclick = () => render();
  const remove = document.querySelector("#demo-delete");
  if (remove)
    remove.onsubmit = async (event) => {
      event.preventDefault();
      try {
        await withStoreLock(() => {store.delete(slug, key);persist();});
        location.hash = href(slug);
      } catch (error) {
        const alert = document.querySelector("#form-error");
        alert.hidden = false;
        alert.textContent = t(error.message);
      }
    };
}
window.addEventListener("hashchange", () => {
  window.scrollTo(0, 0);
  render();
});
render();
