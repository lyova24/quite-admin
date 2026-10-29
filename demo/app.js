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
    return `<textarea ${attrs} rows="8">${e(value)}</textarea>`;
  if (field.kind === "boolean" || field.choices.length) {
    const choices =
      field.kind === "boolean" ? ["true", "false"] : field.choices;
    return `<select ${attrs}>${field.nullable ? '<option value="">—</option>' : ""}${choices.map((choice) => `<option value="${e(choice)}" ${choice === value ? "selected" : ""}>${e(field.kind === "boolean" ? t(choice === "true" ? "True" : "False") : choice)}</option>`).join("")}</select>`;
  }
  return `<input ${attrs} type="${["integer", "number"].includes(field.kind) ? "number" : field.kind === "date" ? "date" : "text"}" step="${field.kind === "integer" ? "1" : "any"}" value="${e(value)}" ${field.maxLength ? `maxlength="${field.maxLength}"` : ""}>`;
};

function login() {
  return `${notice()}<main class="panel demo-login"><h1>${e(seed.title)}</h1><form id="demo-login"><label>${e(t("Username"))}<input name="username" autocomplete="username" required></label><label>${e(t("Password"))}<input name="password" type="password" autocomplete="current-password" required></label><p class="field-help">${e(t("Use admin / admin"))}</p><p class="demo-error" role="alert" id="login-error"></p><button class="button primary">${e(t("Sign in"))}</button></form></main>`;
}
function dashboard() {
  return `<div class="page-heading"><h1>${e(seed.title)}</h1></div><section class="collection-grid">${Object.entries(
    store.state,
  )
    .map(
      ([slug, c]) =>
        `<a class="collection-card" href="${href(slug)}"><span class="nav-icon">▦</span><h2>${e(c.label)}</h2><span>${e(records(c.records.length))}</span></a>`,
    )
    .join("")}</section>`;
}
function listing(slug, query) {
  const c = store.collection(slug);
  const search = query.get("q") || "";
  const sort =
    c.fields.find((field) => field.name === query.get("sort")) || c.fields[0];
  const descending = query.get("direction") === "desc";
  let rows = c.records.filter((row) =>
    c.fields.some(
      (field) =>
        field.kind === "string" &&
        String(row.values[field.name] ?? "")
          .toLowerCase()
          .includes(search.toLowerCase()),
    ),
  );
  rows = rows.slice().sort((a, b) => {
    const av = a.values[sort.name],
      bv = b.values[sort.name];
    const cmp = ["integer", "number"].includes(sort.kind)
      ? Number(av) - Number(bv)
      : String(av ?? "").localeCompare(String(bv ?? ""));
    return (
      (descending ? -cmp : cmp) || Number(a.values.id) - Number(b.values.id)
    );
  });
  const page = Math.max(1, Number(query.get("page")) || 1),
    limit = 5;
  const total = rows.length;
  rows = rows.slice((page - 1) * limit, page * limit);
  return `<div class="page-heading"><h1>${e(c.label)}</h1>${button(href(slug, "new"), "Create record", "primary")}</div><div class="panel"><form id="demo-search" class="search-bar"><input name="q" aria-label="${e(t("Search records"))}" placeholder="${e(t("Search records"))}" value="${e(search)}"><button class="button secondary">${e(t("Search"))}</button><span>${e(records(total))}</span></form><div class="table-scroll"><table><thead><tr>${c.columns.map((name) => `<th><a href="${href(slug)}?sort=${encodeURIComponent(name)}&direction=${descending ? "asc" : "desc"}&q=${encodeURIComponent(search)}">${e(c.fields.find((field) => field.name === name).label)} ↕</a></th>`).join("")}<th class="sr-only">${e(t("Delete"))}</th></tr></thead><tbody>${rows.map((row) => `<tr class="record-row record-row-clickable">${c.columns.map((name, index) => `<td>${index === 0 ? `<a class="record-row-link" href="${href(slug, row.key)}" aria-label="${e(t("Open record") + ": " + store.label(slug, row))}">${e(display(c, name, row))}</a>` : e(display(c, name, row))}</td>`).join("")}<td class="delete-col">${button(href(slug, row.key, "/delete"), "Delete", "small danger-outline")}</td></tr>`).join("") || `<tr><td colspan="${c.columns.length + 1}">${e(t("No records"))}</td></tr>`}</tbody></table></div><div class="pagination">${page > 1 ? button(href(slug) + `?page=${page - 1}&q=${encodeURIComponent(search)}`, "Previous") : ""}<span>${page}</span>${page * limit < total ? button(href(slug) + `?page=${page + 1}&q=${encodeURIComponent(search)}`, "Next") : ""}</div></div>`;
}
function recordPage(slug, key) {
  const c = store.collection(slug),
    creating = key === "new";
  const row = creating ? { values: {}, links: {} } : store.record(slug, key);
  const managed = c.relations.flatMap((relation) => relation.sourceFields);
  const writable = c.writable[creating ? "create" : "edit"];
  return `<a class="back-link" href="${href(slug)}">← ${e(c.label)}</a><div class="page-heading"><h1>${e(creating ? t("Create record") : store.label(slug, row))}</h1>${creating ? "" : button(href(slug, key, "/delete"), "Delete record", "danger-outline")}</div><form id="demo-record" class="panel record-form"><div class="alert" role="alert" id="form-error" hidden></div><div class="form-grid">${c.fields
    .filter(
      (field) =>
        !managed.includes(field.name) && (!creating || !field.generated),
    )
    .map((field) => {
      const editable = writable.includes(field.name),
        value = row.values[field.name] ?? "";
      return `<div class="form-field ${field.kind === "json" ? "wide" : ""}"><label for="field-${e(field.name)}">${e(field.label)} ${editable ? "" : `<span class="field-tag">${e(t("Read only"))}</span>`}</label>${editable ? input(field, value) : `<div class="readonly-value">${e(value || "—")}</div>`}${creating && editable && field.hasDefault ? `<label class="checkbox-label"><input type="checkbox" name="__default__${e(field.name)}" checked>${e(t("Use model / database default"))}</label>` : ""}</div>`;
    })
    .join("")}${c.relations
    .map((relation) => {
      const selected = row.links[relation.name] || [],
        multiple = ["one_to_many", "many_to_many"].includes(relation.kind);
      return `<div class="form-field wide"><label for="relation-${e(relation.name)}">${e(relation.label)}</label><select id="relation-${e(relation.name)}" name="__relation__${e(relation.name)}" ${multiple ? 'multiple size="6"' : ""}>${multiple ? "" : '<option value="">—</option>'}${store
        .collection(relation.target)
        .records.map(
          (other) =>
            `<option value="${e(other.key)}" ${selected.includes(other.key) ? "selected" : ""}>${e(store.label(relation.target, other))}</option>`,
        )
        .join(
          "",
        )}</select>${multiple ? `<p class="field-help">${e(t("Hold Ctrl or Command to select multiple records."))}</p>` : ""}</div>`;
    })
    .join(
      "",
    )}</div><div class="form-footer"><div class="button-group">${button(href(slug), "Cancel")}<button class="button primary">${e(t(creating ? "Create record" : "Save changes"))}</button></div></div></form>`;
}
function deletion(slug, key) {
  const row = store.record(slug, key);
  return `<div class="page-heading"><h1>${e(t("Delete this record?"))}</h1></div><div class="panel delete-panel"><p>${e(store.label(slug, row))}</p><div class="alert" id="form-error" role="alert" hidden></div><form id="demo-delete"><div class="button-group">${button(href(slug, key), "Keep record")}<button class="button danger">${e(t("Delete permanently"))}</button></div></form></div>`;
}
function shell(content, slug, key) {
  const c = slug ? store.collection(slug) : null;
  const crumb = `<a href="#/">${e(t("Overview"))}</a>${c ? ` / <a href="${href(slug)}">${e(c.label)}</a>` : ""}${key && key !== "new" ? ` / <span aria-current="page">${e(store.label(slug, store.record(slug, key)))}</span>` : ""}`;
  return `<div class="shell"><aside class="sidebar"><a class="brand" href="#/"><span class="brand-mark">q.</span>${e(seed.title)}</a><a class="nav-link" href="#/">${e(t("Overview"))}</a><p class="nav-label">${e(t("COLLECTIONS"))}</p><nav>${Object.entries(
    store.state,
  )
    .map(
      ([name, c]) =>
        `<a class="nav-link ${name === slug ? "active" : ""}" href="${href(name)}"><span class="nav-icon">▦</span>${e(c.label)}</a>`,
    )
    .join(
      "",
    )}</nav><p class="nav-label">${e(t("PAGES"))}</p><a class="nav-link" href="#/report">Store report</a><div class="sidebar-bottom">Quite Admin <span class="muted">v${e(seed.version)}</span></div></aside><main class="main">${notice()}<header class="topbar"><nav aria-label="${e(t("Breadcrumbs"))}" class="breadcrumbs">${crumb}</nav><div class="account"><span>admin</span><button class="link-button" id="demo-logout">${e(t("Sign out"))}</button></div></header><div class="content">${content}</div></main></div>`;
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
        `<h1>Store report</h1><div class="panel">${store.collection("customers").records.length} customers · ${store.collection("orders").records.length} orders</div>`,
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
      location.hash =
        href(slug) +
        `?q=${encodeURIComponent(new FormData(event.target).get("q"))}`;
    };
  const form = document.querySelector("#demo-record");
  if (form)
    form.onsubmit = (event) => {
      event.preventDefault();
      try {
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
        const saved = store.save(
          slug,
          key === "new" ? null : key,
          values,
          selections,
        );
        persist();
        if (location.hash === href(slug, saved)) render();
        else location.hash = href(slug, saved);
      } catch (error) {
        const alert = document.querySelector("#form-error");
        alert.hidden = false;
        alert.textContent = t(error.message);
      }
    };
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
