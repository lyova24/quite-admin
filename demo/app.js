import { Store } from "./store.mjs";
import { activityPage } from "./activity.mjs";
import { inlineDialog, listCell, csv, matchingRows, listWindow } from "./listing.mjs";

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
try {
  store = new Store(seed, JSON.parse(read("localStorage", storageKey)));
} catch {
  store = new Store(seed);
}
let language = read("localStorage", "quite-admin-demo-language") || "en";
const extra = {
  "Browser demo · changes stay in this browser":
    "Демо в браузере · изменения сохраняются только здесь",
  "Reset demo": "Сбросить демо",
  "Use admin / admin": "Используйте admin / admin",
  "Explore the interface": "Знакомство с интерфейсом",
  "Edit a list cell": "Измените ячейку списка",
  "Dates, time and JSON": "Даты, время и JSON",
  "Inspect field changes": "Посмотрите изменения полей",
  "Groups, relations and schema": "Группы, связи и схема",
  "Fictional sample events and your local actions. Reset demo restores both.": "Вымышленные примеры событий и ваши локальные действия. Сброс демо восстанавливает и данные, и историю.",
  "Catalog": "Каталог", "Sales": "Продажи", "Workspace": "Рабочее пространство",
  "CSV download": "Скачать CSV",
  "Naive local time; microseconds are preserved.": "Время без часового пояса; микросекунды сохраняются.",
  "None means this event is awaiting review.": "None означает, что событие ожидает согласования.",
};
const t = (text, values = {}) => {
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
const notice = () =>
  `<div class="demo-notice"><span>${e(t("Browser demo · changes stay in this browser"))}</span><select aria-label="Language" id="demo-language"><option value="en" ${language === "en" ? "selected" : ""}>English</option><option value="ru" ${language === "ru" ? "selected" : ""}>Русский</option></select><button class="link-button" id="demo-reset">${e(t("Reset demo"))}</button></div>`;
const button = (path, text, cls = "secondary") =>
  `<a class="button ${cls}" href="${e(path)}">${e(t(text))}</a>`;
const input = (field, value) => window.QuiteAdmin.createFieldControl(
  {...field, max_length: field.maxLength},
  {id: 'field-' + field.name, value, t, rows: 6},
).outerHTML;

function login() {
  return `${notice()}<main class="shell-login"><div class="content"><section class="login-card"><span class="brand-mark large">q.</span><h1>${e(seed.title)}</h1><form id="demo-login" class="stack"><div><label for="username">${e(t("Username"))}</label><input id="username" name="username" autocomplete="username" required></div><div><label for="password">${e(t("Password"))}</label><input id="password" name="password" type="password" autocomplete="current-password" required></div><p class="field-help">${e(t("Use admin / admin"))}</p><p class="demo-error" role="alert" id="login-error"></p><button class="button primary">${e(t("Sign in"))}</button></form></section></div></main>`;
}
function dashboard() {
  return `<div class="page-heading"><h1>${e(seed.title)}</h1></div><div class="demo-tour"><h2>${e(t("Explore the interface"))}</h2><div class="button-group">${button(href("products"),"Edit a list cell")}${button(href("schedules",store.collection("schedules").records[0]?.key||"new"),"Dates, time and JSON")}${button("#/history","Inspect field changes")}${button("#/schema","Groups, relations and schema")}</div></div><div class="section-heading"><h2>${e(t("Collections"))}</h2></div><section class="collection-grid">${Object.entries(store.state)
    .map(([slug, c]) => `<a class="collection-card" href="${href(slug)}"><h2>${e(c.label)}</h2><p class="muted">${e(records(c.records.length))}</p><div class="card-footer">${e(t("Open collection"))}<span aria-hidden="true">→</span></div></a>`)
    .join("")}</section>`;
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
  return `<div class="page-heading list-heading"><div class="heading-with-count"><h1>${e(c.label)}</h1><span class="record-count">${e(cursor?t("{count} on this page",{count:rows.length}):records(total))}</span></div></div>
  ${inlineDialog(t,e)}<section class="record-list"><div class="list-tools"><form id="demo-search" class="list-query-form" ${filters.attributes}><div class="toolbar list-toolbar"><div class="search-form" role="search"><input name="q" aria-label="${e(t("Search records"))}" placeholder="${e(t("Search records…"))}" value="${e(search)}"></div>${filters.add}</div>${filters.panel}</form><details class="export-panel"><summary class="button secondary" aria-label="${e(t('Export data'))}">↓ CSV</summary><form id="demo-export" class="export-form"><p class="field-help">${e(t('Exports all matching records using the current search, filters and sorting. Apply filters before exporting.'))}</p><fieldset><legend>${e(t('Columns'))}</legend><div class="export-columns">${c.fields.map(field=>`<label class="checkbox-label"><input type="checkbox" name="columns" value="${e(field.name)}" ${c.columns.includes(field.name)?'checked':''}> ${e(field.label)}</label>`).join('')}</div></fieldset><button class="button secondary" type="submit">${e(t('CSV download'))}</button></form></details>${button(href(slug, "new"), "+ " + t("Create record"), "primary list-create")}</div>${filters.active}
  ${search ? `<div class="active-filters"><span class="filter-chip">${e(t("Search"))}: ${e(search)}</span><a class="link-button" href="${e(queryUrl({ q: "", page: 1 }))}">${e(t("Clear"))}</a></div>` : ""}
  <div class="table-scroll list-table-scroll"><table aria-label="${e(c.label)}"><thead><tr>${c.columns.map((name) => {
    const field = c.fields.find((field) => field.name === name), active = sort.name === name;
    return `<th scope="col" class="${["integer", "number"].includes(field.kind) ? "numeric" : ""}" ${active ? `aria-sort="${descending ? "descending" : "ascending"}"` : ""}>${cursor&&!field.primaryKey?"":`<a href="${e(queryUrl({ sort: name, direction: active && !descending ? "desc" : "asc", page: 1,after:null,before:null }))}">`}${e(field.label)}${cursor&&!field.primaryKey?"":`<span class="sort-icon" aria-hidden="true">${active ? descending ? "↓" : "↑" : "↕"}</span></a>`}</th>`;
  }).join("")}<th scope="col" class="delete-col"><span class="sr-only">${e(t("Delete"))}</span></th></tr></thead><tbody>${rows.map((row) => `<tr class="record-row record-row-clickable">${c.columns.map((name, index) => {
    const field = c.fields.find((field) => field.name === name), value = row.values[name];
    const content = listCell({slug,row,field,editable:c.inline.includes(name),t,e});
    return `<td data-list-field="${e(name)}" class="${["integer", "number"].includes(field.kind) ? "numeric" : field.name === primaryName ? "cell-primary" : ""}">${index === 0 ? `<a class="record-row-link" href="${href(slug, row.key)}" aria-label="${e(t("Open record") + ": " + store.label(slug, row))}">${content}</a>` : content}</td>`;
  }).join("")}<td class="delete-col"><a class="button small danger-outline delete-action" href="${href(slug, row.key, "/delete")}" title="${e(t("Delete record") + ": " + store.label(slug, row))}"><span class="sr-only">${e(t("Delete"))}</span><svg class="action-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></a></td></tr>`).join("") || `<tr><td colspan="${c.columns.length + 1}"><div class="empty-state"><h2>${e(t(search ? "No matching records" : "No records"))}</h2><p>${e(t(search ? "Try a different search." : "This collection has no records yet."))}</p>${button(search ? queryUrl({ q: "", page: 1 }) : href(slug, "new"), search ? "Clear" : "Create record")}</div></td></tr>`}</tbody></table></div>
  <footer class="pagination"><span>${e(cursor?t("Browse records"):t("Page {number}",{number:page}))}<span class="pagination-divider">·</span>${e(t("{count} per page").replace("{count}", limit))}</span><div>${hasPrevious ? button(queryUrl(cursor?{before:rows[0].key,after:null}:{page:page-1}), "Previous", "secondary small") : ""}${hasNext ? button(queryUrl(cursor?{after:rows.at(-1).key,before:null}:{page:page+1}), "Next", "secondary small") : ""}</div></footer></section>`;
}
function recordPage(slug, key) {
  const c = store.collection(slug), creating = key === "new";
  const row = creating ? { values: {}, links: {} } : store.record(slug, key);
  const managed = c.relations.flatMap((relation) => relation.sourceFields);
  const writable = c.writable[creating ? "create" : "edit"];
  const fields = c.fields.filter((field) => !managed.includes(field.name) && (!creating || !field.generated));
  const renderField = (field) => {
    const editable = writable.includes(field.name), value = row.values[field.name] ?? "";
    return `<div class="form-field ${field.kind === "json" || field.multiline ? "wide" : ""}"><label id="label-${e(field.name)}" for="field-${e(field.name)}">${e(field.label)} ${editable ? field.nullable ? `<span class="optional-label">${e(t("optional"))}</span>` : "" : `<span class="field-tag">${e(t("Read only"))}</span>`}</label>${editable ? input(field, value) : `<div class="readonly-value" id="field-${e(field.name)}">${e(display(c, field.name, row))}</div>`}${field.help?`<p class="field-help">${e(t(field.help))}</p>`:""}${creating && editable && field.hasDefault ? `<label class="checkbox-label"><input type="checkbox" name="__default__${e(field.name)}" checked>${e(t("Use model / database default"))}</label>` : ""}</div>`;
  };
  const section = (title, content, id) => content ? `<section class="form-section" aria-labelledby="${id}"><h2 id="${id}">${e(t(title))}</h2><div class="form-grid">${content}</div></section>` : "";
  const groups = [
    ["Record fields", fields.filter((f) => writable.includes(f.name) && f.kind !== "json")],
    ["Structured data", fields.filter((f) => writable.includes(f.name) && f.kind === "json")],
    ["Read-only fields", fields.filter((f) => !writable.includes(f.name))],
  ];
  const pickerMessages = Object.fromEntries(Object.entries({ choose: "Choose records", search: "Search related records", remove: "Remove", previous: "Previous", next: "Next", loading: "Loading…", empty: "No matching records.", failed: "Could not load records. Try again.", retry: "Retry", selected: "Selected", results: "Results", limit: "Select up to 1000 records." }).map(([key, value]) => [key, t(value)]));
  const relations = c.relations.map((relation) => {
    const selected = row.links[relation.name] || [], multiple = ["one_to_many", "many_to_many"].includes(relation.kind);
    return `<div class="form-field wide"><label for="relation-${e(relation.name)}">${e(relation.label)}</label><div class="relation-picker" data-relation-picker data-endpoint="./" data-relation="${e(relation.name)}" data-messages="${e(JSON.stringify(pickerMessages))}"><select class="picker-native" id="relation-${e(relation.name)}" name="__relation__${e(relation.name)}" ${multiple ? `multiple size="6" aria-describedby="relation-help-${e(relation.name)}"` : ""}>${multiple ? "" : '<option value="">—</option>'}${store.collection(relation.target).records.map((other) => `<option value="${e(other.key)}" ${selected.includes(other.key) ? "selected" : ""}>${e(store.label(relation.target, other))}</option>`).join("")}</select></div></div>`;
  }).join("");
  return `<a class="back-link" href="${href(slug)}">← ${e(c.label)}</a><div class="page-heading"><div><p class="eyebrow">${e(c.label)}</p><h1>${e(creating ? t("Create record") : store.label(slug, row))}</h1></div>${creating ? "" : button(href(slug, key, "/delete"), "Delete record", "danger-outline")}</div><form id="demo-record" class="panel record-form">${creating ? "" : `<input type="hidden" name="__revision" value="${e(store.revision(slug, key))}">`}<div class="alert" role="alert" id="form-error" hidden></div><button id="demo-reload" class="button secondary conflict-reload" type="button" hidden>${e(t("Reload record"))}</button>${groups.map(([heading, fields], index) => section(heading, fields.map(renderField).join(""), `section-${index}`)).join("")}${section("Relationships", relations, "section-relations")}<div class="form-footer"><div class="button-group">${button(href(slug), "Cancel")}<button class="button primary">${e(t(creating ? "Create record" : "Save changes"))}</button></div></div></form>`;
}
function deletion(slug, key) {
  const row = store.record(slug, key);
  return `<div class="page-heading"><h1>${e(t("Delete this record?"))}</h1></div><div class="panel delete-panel"><p>${e(store.label(slug, row))}</p><div class="alert" id="form-error" role="alert" hidden></div><form id="demo-delete"><div class="button-group">${button(href(slug, key), "Keep record")}<button class="button danger">${e(t("Delete permanently"))}</button></div></form></div>`;
}
function shell(content, slug, key) {
  const c = slug ? store.collection(slug) : null;
  const section = location.hash.split("?")[0];
  const navLink = (path,label,active) => `<a class="nav-link ${active?'active':''}" href="${path}" ${active?'aria-current="page"':''}>${e(t(label))}</a>`;
  const crumb = `<a href="#/">${e(t("Overview"))}</a>${c ? ` / <a href="${href(slug)}">${e(c.label)}</a>` : ""}${section==="#/schema"?` / ${e(t("Database schema"))}`:section==="#/history"?` / ${e(t("Activity history"))}`:""}${key && key !== "new" ? ` / <span aria-current="page">${e(store.label(slug, store.record(slug, key)))}</span>` : ""}`;
  const groups = new Map();
  for (const [name,collection] of Object.entries(store.state)) {
    const label=collection.group||"Other collections";
    if(!groups.has(label))groups.set(label,[]);
    groups.get(label).push([name,collection]);
  }
  const navigation = [...groups].map(([group,items])=>`<details class="nav-group" data-demo-group="${e(group)}" ${items.some(([name])=>name===slug)||read("localStorage","quite-admin-demo-group-"+group)!=="closed"?'open':''}><summary>${e(t(group))}<span>${items.length}</span></summary>${items.map(([name,collection])=>navLink(href(name),collection.label,name===slug)).join('')}</details>`).join('');
  return `<div class="shell"><aside class="sidebar"><a class="brand" href="#/"><span class="brand-mark">q.</span>${e(seed.title)}</a>${navLink('#/','Overview',section==='#/'||!location.hash)}${navLink('#/schema','Database schema',section==='#/schema')}${navLink('#/history','Activity history',section==='#/history')}<p class="nav-label">${e(t("COLLECTIONS"))} <span>${Object.keys(store.state).length}</span></p><nav aria-label="${e(t('Collections'))}">${navigation}</nav><p class="nav-label">${e(t("PAGES"))}</p>${navLink('#/report','Store report',section==='#/report')}<div class="sidebar-bottom">Quite Admin <span class="muted">v${e(seed.version)}</span></div></aside><main class="main">${notice()}<header class="topbar"><nav aria-label="${e(t("Breadcrumbs"))}" class="breadcrumbs">${crumb}</nav><div class="account"><span>admin</span><button class="link-button" id="demo-logout">${e(t("Sign out"))}</button></div></header><div class="content">${content}</div></main></div>`;
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
    if(!c.inline.includes(name)) return respond({},403);
    if(options.method !== "POST") return respond({name,label:field.label,kind:field.kind,multiline:field.multiline,nullable:field.nullable,choices:field.choices,max_length:field.maxLength,value:row.values[name]??"",raw_boolean:row.values[name]==null?null:row.values[name]==="true",csrf:"browser-demo",revision:store.revision(slug,key)});
    const data = options.body;
    try {
      store.save(slug,key,{[name]:data.get(name)===""&&field.nullable?null:data.get(name)},{},data.get("__revision"),"inline_edit");
      persist();
      const latest = store.record(slug,key);
      return respond({label_record:t("Open record")+": "+store.label(slug,latest),cells:Object.fromEntries(c.fields.map(field=>[field.name,{text:latest.values[field.name]??"—",null:latest.values[field.name]==null,boolean:latest.values[field.name]==="true"}]))});
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
  let slug, key, content;
  try {
    if (!loggedIn) content = login();
    else if (parts[0] === "models") {
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
    else if (parts[0] === "report")
      content = shell(
        `<div class="page-heading"><h1>Store report</h1></div><div class="collection-grid">${["customers", "orders"].map((name) => `<div class="collection-card"><h2>${e(store.collection(name).label)}</h2><p class="report-value">${store.collection(name).records.length}</p><div class="card-footer"><a href="${href(name)}">${e(t("Open collection"))} →</a></div></div>`).join("")}</div>`,
      );
    else content = shell(dashboard());
  } catch (error) {
    content = shell(`<h1>${e(t("Not Found"))}</h1>${button("#/", "Overview")}`);
  }
  document.querySelectorAll("[data-schema-workspace]").forEach((root) => root.schemaCleanup?.());
  cleanupInline?.(); cleanupHistory?.(); cleanupListing?.(); cleanupFields?.();
  document.querySelector("#app").innerHTML = content;
  const formMessages = document.createElement("div"); formMessages.hidden = true;
  formMessages.setAttribute("data-form-messages", ""); formMessages.dataset.messages = JSON.stringify(seed.formMessages[language]);
  document.querySelector("#app").prepend(formMessages);
  cleanupFields = window.quiteAdminEnhanceFields(document);
  window.QuiteAdmin.initSchemas();
  cleanupInline = window.quiteAdminEnhanceInline(document, inlineRequest);
  initActivity(query);
  for (const group of document.querySelectorAll('[data-demo-group]')) group.addEventListener('toggle',()=>write('localStorage','quite-admin-demo-group-'+group.dataset.demoGroup,group.open?'open':'closed'));
  document.querySelector("#demo-language").onchange = (event) => {
    language = event.target.value;
    write("localStorage", "quite-admin-demo-language", language);
    render();
  };
  document.querySelector("#demo-reset").onclick = () => {
    store = new Store(seed);
    persist();
    location.hash = "#/";
    render();
  };
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
      const target = store.collection(relation.target);
      const rows = target.records.filter(row => target.fields.some(f => f.kind === 'string' && String(row.values[f.name] || '').toLowerCase().includes(term.toLowerCase())) || target.fields.filter(f=>f.primaryKey).every(f=>String(row.values[f.name])===term));
      return {items: rows.slice((page - 1) * 25, page * 25).map((row) => ({key:row.key,label:store.label(relation.target,row),identity:target.fields.filter(f=>f.primaryKey).map(f=>row.values[f.name]).join(" · "),description:target.fields.filter(f=>f.kind==='string').map(f=>row.values[f.name]).filter(Boolean).join(" · ")})), total:rows.length,has_next:page * 25 < rows.length};
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
        const rows = store.collection(relation.target).records.filter((row) => store.label(relation.target, row).toLowerCase().includes(search.toLowerCase()));
        return {items: rows.slice((page - 1) * 25, page * 25).map((row) => ({key: row.key, label: store.label(relation.target, row)})), total: rows.length, has_next: page * 25 < rows.length};
      };
    });
    window.QuiteAdmin.initRelationPickers();
  }
  cleanupListing = window.quiteAdminEnhanceListing(document, location.pathname + "#/models/" + slug);
  const exportForm = document.querySelector("#demo-export");
  if(exportForm) exportForm.onsubmit = event => {
    event.preventDefault();
    const data = new FormData(exportForm), columns = data.getAll("columns");
    if(!columns.length)return;
    const exportQuery = new URLSearchParams(query); exportQuery.set("q",data.get("q")||"");
    const blob = new Blob([csv(store.collection(slug),matchingRows(store,slug,exportQuery),columns)],{type:"text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href=url;link.download=slug+".csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    store.log(slug,"export");persist();
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
                : data.get(field.name);
        for (const relation of c.relations)
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
  render();
  window.scrollTo(0, 0);
});
render();
