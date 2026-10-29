import { Store } from "./store.mjs";

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
};
const t = (text) =>
  language === "ru" ? seed.translations[text] || extra[text] || text : text;
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
  write("localStorage", storageKey, JSON.stringify(store.state));
const notice = () =>
  `<div class="demo-notice"><span>${e(t("Browser demo · changes stay in this browser"))}</span><select aria-label="Language" id="demo-language"><option value="en" ${language === "en" ? "selected" : ""}>English</option><option value="ru" ${language === "ru" ? "selected" : ""}>Русский</option></select><button class="link-button" id="demo-reset">${e(t("Reset demo"))}</button></div>`;
const button = (path, text, cls = "secondary") =>
  `<a class="button ${cls}" href="${e(path)}">${e(t(text))}</a>`;
const input = (field, value) => {
  const attrs = `id="field-${e(field.name)}" name="${e(field.name)}"`;
  if (field.kind === "json")
    return `<textarea class="code-input" ${attrs} rows="4">${e(value)}</textarea>`;
  if (field.kind === "boolean" || field.choices.length) {
    const choices =
      field.kind === "boolean" ? ["true", "false"] : field.choices;
    return `<select ${attrs}>${field.nullable ? '<option value="">—</option>' : ""}${choices.map((choice) => `<option value="${e(choice)}" ${choice === value ? "selected" : ""}>${e(field.kind === "boolean" ? t(choice === "true" ? "True" : "False") : choice)}</option>`).join("")}</select>`;
  }
  return `<input ${attrs} type="${["integer", "number"].includes(field.kind) ? "number" : field.kind === "date" ? "date" : "text"}" step="${field.kind === "integer" ? "1" : "any"}" value="${e(value)}" ${field.maxLength ? `maxlength="${field.maxLength}"` : ""}>`;
};

function login() {
  return `${notice()}<main class="shell-login"><div class="content"><section class="login-card"><span class="brand-mark large">q.</span><h1>${e(seed.title)}</h1><form id="demo-login" class="stack"><div><label for="username">${e(t("Username"))}</label><input id="username" name="username" autocomplete="username" required></div><div><label for="password">${e(t("Password"))}</label><input id="password" name="password" type="password" autocomplete="current-password" required></div><p class="field-help">${e(t("Use admin / admin"))}</p><p class="demo-error" role="alert" id="login-error"></p><button class="button primary">${e(t("Sign in"))}</button></form></section></div></main>`;
}
function dashboard() {
  return `<div class="page-heading"><h1>${e(seed.title)}</h1></div><div class="section-heading"><h2>${e(t("Collections"))}</h2></div><section class="collection-grid">${Object.entries(store.state)
    .map(([slug, c]) => `<a class="collection-card" href="${href(slug)}"><h2>${e(c.label)}</h2><p class="muted">${e(records(c.records.length))}</p><div class="card-footer">${e(t("Open collection"))}<span aria-hidden="true">→</span></div></a>`)
    .join("")}</section>`;
}
function demoFilters(slug, query, queryUrl) {
  const c = store.collection(slug);
  const value = (name) => e(query.get(name) || "");
  const control = (name, label, type = "text") => `<div><label for="${e(name)}">${e(t(label))}</label><input id="${e(name)}" name="${e(name)}" type="${type}" step="any" value="${value(name)}"></div>`;
  const select = (name, choices) => `<select id="${e(name)}" name="${e(name)}"><option value="">${e(t("Any value"))}</option>${choices.map(([key, label]) => `<option value="${e(key)}" ${query.get(name) === key ? "selected" : ""}>${e(label)}</option>`).join("")}</select>`;
  const messages = Object.fromEntries(Object.entries({ choose: "Choose records", search: "Search related records", remove: "Remove", previous: "Previous", next: "Next", loading: "Loading…", empty: "No matching records.", failed: "Could not load records. Try again.", retry: "Retry", selected: "Selected", results: "Results", limit: "Select up to 1000 records." }).map(([key, val]) => [key, t(val)]));
  const clear = Object.fromEntries([...query.keys()].filter((name) => name === "q" || name.startsWith("f.") || name.startsWith("r.")).map((name) => [name, null]));
  const active = [...query].filter(([name, val]) => val && (name.startsWith("f.") || name.startsWith("r."))).map(([name, val]) => {
    let label;
    if (name.startsWith("r.")) {
      const relation = c.relations.find((item) => item.name === name.slice(2));
      const row = store.collection(relation.target).records.find((item) => item.key === val);
      label = relation.label + ": " + (row ? store.label(relation.target, row) : "—");
    } else {
      const match = /^f\.(.+)\.(eq|gte|lte|is_null)$/.exec(name);
      const field = c.fields.find((item) => item.name === match[1]);
      label = field.label + " " + (match[2] === "is_null" ? t(val === "true" ? "Is NULL" : "Is not NULL") : ({eq:"=",gte:"≥",lte:"≤"}[match[2]] + " " + (field.kind === "boolean" ? t(val === "true" ? "True" : "False") : val)));
    }
    return `<a class="filter-chip" href="${e(queryUrl({[name]: null, page: 1}))}">${e(label)} ×</a>`;
  }).join("");
  const fields = c.fields.filter((field) => field.nullable || !["json", "binary", "unsupported"].includes(field.kind)).map((field) => {
    const prefix = `f.${field.name}.`;
    const range = ["integer", "number", "date", "datetime", "time"].includes(field.kind);
    const input = range ? `<div class="filter-range">${control(prefix+"gte", "From", field.kind === "date" ? "date" : ["integer","number"].includes(field.kind) ? "number" : "text")}${control(prefix+"lte", "To", field.kind === "date" ? "date" : ["integer","number"].includes(field.kind) ? "number" : "text")}</div>` : field.kind === "boolean" || field.choices.length ? `<label class="sr-only" for="${e(prefix)}eq">${e(field.label)}</label>${select(prefix+"eq", field.kind === "boolean" ? [["true",t("True")],["false",t("False")]] : field.choices.map((v) => [v,v]))}` : ["json", "binary", "unsupported"].includes(field.kind) ? "" : control(prefix+"eq", "Equals");
    return `<fieldset class="filter-field"><legend>${e(field.label)}</legend>${input}${field.nullable ? `<label class="sr-only" for="${e(prefix)}is_null">${e(t("Empty values"))}</label>${select(prefix+"is_null", [["true",t("Is NULL")],["false",t("Is not NULL")]])}` : ""}</fieldset>`;
  }).join("");
  const related = c.relations.map((relation) => {
    const name = "r." + relation.name, key = query.get(name), target = store.collection(relation.target);
    const row = target.records.find((row) => row.key === key);
    return `<div class="filter-field"><label for="filter-relation-${e(relation.name)}">${e(relation.label)}</label><div class="relation-picker" data-relation-picker data-relation="${e(relation.name)}" data-endpoint="./" data-messages="${e(JSON.stringify(messages))}"><select class="picker-native" id="filter-relation-${e(relation.name)}" name="${e(name)}"><option value="">${e(t("Any value"))}</option>${row ? `<option value="${e(key)}" selected>${e(store.label(relation.target, row))}</option>` : ""}</select></div></div>`;
  }).join("");
  return {panel:`<details class="filter-disclosure"><summary class="button secondary">${e(t("Filters"))}</summary><div class="filter-panel"><div class="filter-grid">${fields}${related}</div><div class="filter-footer button-group"><button class="button primary">${e(t("Apply filters"))}</button>${button(queryUrl({...clear,page:1}),"Clear all")}</div></div></details>`, active: active ? `<div class="active-filters">${active}${button(queryUrl({...clear,page:1}),"Clear all")}</div>` : ""};
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
  let rows = store.filter(slug, query).filter((row) => c.fields.some((field) =>
    field.kind === "string" && String(row.values[field.name] ?? "").toLowerCase().includes(search.toLowerCase()),
  ));
  rows = rows.slice().sort((a, b) => {
    const av = a.values[sort.name], bv = b.values[sort.name];
    const cmp = ["integer", "number"].includes(sort.kind)
      ? Number(av) - Number(bv)
      : String(av ?? "").localeCompare(String(bv ?? ""));
    return (descending ? -cmp : cmp) || Number(a.values.id) - Number(b.values.id);
  });
  const page = Math.max(1, Number(query.get("page")) || 1), limit = 5;
  const total = rows.length;
  rows = rows.slice((page - 1) * limit, page * limit);
  return `<div class="page-heading list-heading"><div class="heading-with-count"><h1>${e(c.label)}</h1><span class="record-count">${e(records(total))}</span></div>${button(href(slug, "new"), "Create record", "primary")}</div>
  <section class="record-list"><form id="demo-search"><div class="toolbar list-toolbar"><div class="search-form" role="search"><input name="q" aria-label="${e(t("Search records"))}" placeholder="${e(t("Search records…"))}" value="${e(search)}"><button class="button secondary">${e(t("Search"))}</button></div></div>${filters.panel}</form>${filters.active}
  ${search ? `<div class="active-filters"><span class="filter-chip">${e(t("Search"))}: ${e(search)}</span><a class="link-button" href="${e(queryUrl({ q: "", page: 1 }))}">${e(t("Clear"))}</a></div>` : ""}
  <div class="table-scroll list-table-scroll"><table aria-label="${e(c.label)}"><thead><tr>${c.columns.map((name) => {
    const field = c.fields.find((field) => field.name === name), active = sort.name === name;
    return `<th scope="col" class="${["integer", "number"].includes(field.kind) ? "numeric" : ""}" ${active ? `aria-sort="${descending ? "descending" : "ascending"}"` : ""}><a href="${e(queryUrl({ sort: name, direction: active && !descending ? "desc" : "asc", page: 1 }))}">${e(field.label)}<span class="sort-icon" aria-hidden="true">${active ? descending ? "↓" : "↑" : "↕"}</span></a></th>`;
  }).join("")}<th scope="col" class="delete-col"><span class="sr-only">${e(t("Delete"))}</span></th></tr></thead><tbody>${rows.map((row) => `<tr class="record-row record-row-clickable">${c.columns.map((name, index) => {
    const field = c.fields.find((field) => field.name === name), value = row.values[name];
    const content = value == null ? '<span class="null-value">—</span>' : field.kind === "boolean"
      ? `<span class="boolean-badge ${value === "true" ? "yes" : "no"}">${e(display(c, name, row))}</span>`
      : `<span class="${field.primaryKey ? "record-id" : "cell-value"}">${e(display(c, name, row))}</span>`;
    return `<td class="${["integer", "number"].includes(field.kind) ? "numeric" : field.name === primaryName ? "cell-primary" : ""}">${index === 0 ? `<a class="record-row-link" href="${href(slug, row.key)}" aria-label="${e(t("Open record") + ": " + store.label(slug, row))}">${content}</a>` : content}</td>`;
  }).join("")}<td class="delete-col"><a class="button small danger-outline delete-action" href="${href(slug, row.key, "/delete")}" title="${e(t("Delete record") + ": " + store.label(slug, row))}"><span class="sr-only">${e(t("Delete"))}</span><svg class="action-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></a></td></tr>`).join("") || `<tr><td colspan="${c.columns.length + 1}"><div class="empty-state"><h2>${e(t(search ? "No matching records" : "No records"))}</h2><p>${e(t(search ? "Try a different search." : "This collection has no records yet."))}</p>${button(search ? queryUrl({ q: "", page: 1 }) : href(slug, "new"), search ? "Clear" : "Create record")}</div></td></tr>`}</tbody></table></div>
  <footer class="pagination"><span>${e(t("Page {number}").replace("{number}", page))}<span class="pagination-divider">·</span>${e(t("{count} per page").replace("{count}", limit))}</span><div>${page > 1 ? button(queryUrl({ page: page - 1 }), "Previous", "secondary small") : ""}${page * limit < total ? button(queryUrl({ page: page + 1 }), "Next", "secondary small") : ""}</div></footer></section>`;
}
function recordPage(slug, key) {
  const c = store.collection(slug), creating = key === "new";
  const row = creating ? { values: {}, links: {} } : store.record(slug, key);
  const managed = c.relations.flatMap((relation) => relation.sourceFields);
  const writable = c.writable[creating ? "create" : "edit"];
  const fields = c.fields.filter((field) => !managed.includes(field.name) && (!creating || !field.generated));
  const renderField = (field) => {
    const editable = writable.includes(field.name), value = row.values[field.name] ?? "";
    return `<div class="form-field ${field.kind === "json" ? "wide" : ""}"><label for="field-${e(field.name)}">${e(field.label)} ${editable ? field.nullable ? `<span class="optional-label">${e(t("optional"))}</span>` : "" : `<span class="field-tag">${e(t("Read only"))}</span>`}</label>${editable ? input(field, value) : `<div class="readonly-value" id="field-${e(field.name)}">${e(display(c, field.name, row))}</div>`}${creating && editable && field.hasDefault ? `<label class="checkbox-label"><input type="checkbox" name="__default__${e(field.name)}" checked>${e(t("Use model / database default"))}</label>` : ""}</div>`;
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
  const crumb = `<a href="#/">${e(t("Overview"))}</a>${c ? ` / <a href="${href(slug)}">${e(c.label)}</a>` : ""}${key && key !== "new" ? ` / <span aria-current="page">${e(store.label(slug, store.record(slug, key)))}</span>` : ""}`;
  return `<div class="shell"><aside class="sidebar"><a class="brand" href="#/"><span class="brand-mark">q.</span>${e(seed.title)}</a><a class="nav-link ${!slug && location.hash !== "#/report" ? "active" : ""}" href="#/">${e(t("Overview"))}</a><p class="nav-label">${e(t("COLLECTIONS"))}</p><nav>${Object.entries(
    store.state,
  )
    .map(
      ([name, c]) =>
        `<a class="nav-link ${name === slug ? "active" : ""}" href="${href(name)}">${e(c.label)}</a>`,
    )
    .join(
      "",
    )}</nav><p class="nav-label">${e(t("PAGES"))}</p><a class="nav-link ${location.hash === "#/report" ? "active" : ""}" href="#/report">Store report</a><div class="sidebar-bottom">Quite Admin <span class="muted">v${e(seed.version)}</span></div></aside><main class="main">${notice()}<header class="topbar"><nav aria-label="${e(t("Breadcrumbs"))}" class="breadcrumbs">${crumb}</nav><div class="account"><span>admin</span><button class="link-button" id="demo-logout">${e(t("Sign out"))}</button></div></header><div class="content">${content}</div></main></div>`;
}
function render() {
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
    } else if (parts[0] === "report")
      content = shell(
        `<div class="page-heading"><h1>Store report</h1></div><div class="collection-grid">${["customers", "orders"].map((name) => `<div class="collection-card"><h2>${e(store.collection(name).label)}</h2><p class="report-value">${store.collection(name).records.length}</p><div class="card-footer"><a href="${href(name)}">${e(t("Open collection"))} →</a></div></div>`).join("")}</div>`,
      );
    else content = shell(dashboard());
  } catch (error) {
    content = shell(`<h1>${e(t("Not Found"))}</h1>${button("#/", "Overview")}`);
  }
  document.querySelector("#app").innerHTML = content;
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
    signedIn = false;
    write("sessionStorage", "quite-admin-demo-login", "false");
    render();
  };
  const search = document.querySelector("#demo-search");
  if (search)
    search.onsubmit = (event) => {
      event.preventDefault();
      const params = new URLSearchParams(query);
      for (const name of [...params.keys()]) if (name.startsWith("f.") || name.startsWith("r.")) params.delete(name);
      for (const [name, value] of new FormData(event.target)) if (value) params.set(name, value); else params.delete(name);
      params.set("page", "1");
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
    remove.onsubmit = (event) => {
      event.preventDefault();
      try {
        store.delete(slug, key);
        persist();
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
