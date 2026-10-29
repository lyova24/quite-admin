/* Progressive list filters. Values remain strings so Decimal and large IDs stay exact. */
(function () {
  "use strict";
  const ranges = new Set(["integer", "number", "date", "datetime", "time"]);
  function operators(field) {
    const items = field.kind === "relation" ? ["eq"]
      : ["json", "binary", "unsupported"].includes(field.kind) ? []
      : ranges.has(field.kind) ? ["eq", "gt", "gte", "lt", "lte", "between"] : ["eq"];
    return field.nullable ? items.concat("null", "not_null") : items;
  }
  function entries(field, operator, values) {
    if (!operators(field).includes(operator)) throw new Error("Invalid filter operator");
    if (operator === "between") return [[field.id + ".gte", values[0]], [field.id + ".lte", values[1]]];
    if (operator === "null" || operator === "not_null") return [[field.id + ".is_null", String(operator === "null")]];
    return [[field.kind === "relation" ? field.id : field.id + "." + operator, values[0]]];
  }
  function updateQuery(params, condition, replacement) {
    const next = new URLSearchParams(params);
    (condition?.parameters || []).forEach((name) => next.delete(name));
    for (const [name, value] of replacement) {
      if (next.has(name)) throw new Error("conflict");
      next.set(name, value);
    }
    next.set("page", "1");
    return next;
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {operators, entries, updateQuery};
  if (typeof document === "undefined") return;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function init(root) {
    const fields = JSON.parse(root.dataset.fields), conditions = JSON.parse(root.dataset.conditions);
    const messages = JSON.parse(root.dataset.messages), errors = JSON.parse(root.dataset.errors || "{}");
    const t = (key) => messages[key] || key;
    const add = root.querySelector("[data-filter-add]");
    const fallback = root.querySelector("[data-filter-fallback]");
    if (!add || !fallback || typeof HTMLElement.prototype.showPopover !== "function") return;
    const popover = element("div", "filter-popover");
    popover.setAttribute("popover", "auto");
    popover.setAttribute("role", "dialog");
    popover.setAttribute("aria-label", t("add"));
    popover.id = "filter-editor";
    root.append(popover);
    add.setAttribute("aria-controls", popover.id);
    add.setAttribute("aria-expanded", "false");
    let anchor = add, abort, timer, sequence = 0;
    function stopLookup() { clearTimeout(timer); abort?.abort(); sequence++; }
    function position() {
      if (!popover.matches(":popover-open")) return;
      const box = anchor.getBoundingClientRect();
      const width = Math.min(400, innerWidth - 24);
      popover.style.width = width + "px";
      popover.style.maxHeight = Math.max(160, innerHeight - 24) + "px";
      popover.style.left = Math.max(12, Math.min(box.left, innerWidth - width - 12)) + "px";
      const height = popover.getBoundingClientRect().height;
      const below = box.bottom + 8;
      popover.style.top = Math.max(12, below + height <= innerHeight - 12 ? below : box.top - height - 8) + "px";
    }
    function close() { stopLookup(); popover.hidePopover(); anchor.focus(); }
    function show(trigger) {
      anchor = trigger;
      popover.showPopover();
      position();
    }
    popover.addEventListener("toggle", () => {
      const open = popover.matches(":popover-open");
      add.setAttribute("aria-expanded", String(open));
      if (!open) {
        stopLookup(); observer.disconnect();
        window.removeEventListener("resize", position);
        window.removeEventListener("scroll", position, true);
      } else {
        observer.observe(popover);
        window.addEventListener("resize", position);
        window.addEventListener("scroll", position, true);
      }
    });
    popover.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
    });
    const observer = new ResizeObserver(position);


    function button(text, className, action) {
      const node = element("button", className, text);
      node.type = "button";
      node.addEventListener("click", action);
      return node;
    }
    function menu(trigger = add) {
      stopLookup();
      popover.replaceChildren();
      popover.setAttribute("aria-label", t("add"));
      const header = element("div", "filter-menu-header");
      const search = element("input");
      search.type = "search";
      search.placeholder = t("find");
      search.setAttribute("aria-label", t("find"));
      search.autocomplete = "off";
      header.append(search);
      const list = element("div", "filter-field-menu");
      const help = element("p", "filter-menu-help", t("hint"));
      const render = () => {
        list.replaceChildren();
        fields.filter((field) => field.label.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())).forEach((field) => {
          const active = conditions.find((item) => item.id === field.id);
          const item = button(field.label, "filter-field-option", () => editor(field, active));
          if (active) {
            const mark = element("span", "filter-option-note", "✓"); mark.setAttribute("aria-hidden", "true");
            item.setAttribute("aria-label", field.label + " · " + t("selected")); item.append(mark);
          }
          list.append(item);
        });
        if (!list.children.length) list.append(element("p", "filter-menu-help", t("empty")));
      };
      search.addEventListener("input", render);
      // Normal buttons remain tab-accessible; arrows also move through the field menu.
      popover.onkeydown = (event) => {
        const items = [search, ...list.querySelectorAll("button")];
        const index = items.indexOf(document.activeElement);
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          items[(index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
        } else if (event.key === "Enter" && document.activeElement === search) {
          event.preventDefault(); list.querySelector("button")?.click();
        }
      };
      popover.append(header, list, help);
      render(); show(trigger); search.focus();
    }
    function editor(field, condition) {
      stopLookup();
      popover.onkeydown = null;
      popover.replaceChildren();
      popover.setAttribute("aria-label", field.label + " · " + t("operator"));
      const heading = element("div", "filter-editor-heading");
      heading.append(button("←", "filter-back", () => menu(anchor)), element("strong", "", field.label));
      heading.firstChild.setAttribute("aria-label", t("back"));
      const body = element("div", "filter-editor-body");
      const label = element("label", "", t("operator"));
      label.htmlFor = "filter-operator";
      const operator = element("select"); operator.id = label.htmlFor;
      operators(field).forEach((op) => { const option = element("option", "", t(op)); option.value = op; operator.append(option); });
      operator.value = condition?.operator === "is_null" ? condition.values[0] === "true" ? "null" : "not_null" : condition?.operator || operators(field)[0];
      const values = element("div", "filter-editor-values");
      const error = element("p", "field-error");
      error.id = "filter-condition-error"; error.setAttribute("role", "alert"); error.hidden = true;
      const footer = element("div", "filter-editor-footer");
      const apply = button(t("apply"), "button primary", submit);
      footer.append(button(t("cancel"), "button secondary", close), apply);
      body.append(label, operator, values, error);
      popover.append(heading, body, footer);
      let drafts = condition?.values.slice() || [];
      let inputs = [], selected = field.kind === "relation" ? condition?.values[0] || "" : "";
      let relationLabel = (field.choices || []).find((item) => item[0] === selected)?.[1] || "";
      function showError(text) { error.textContent = text; error.hidden = false; inputs.forEach((input) => { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", error.id); }); }
      function renderValues(initial = false) {
        stopLookup(); values.replaceChildren(); inputs = []; error.hidden = true;
        if (["null", "not_null"].includes(operator.value)) return;
        if (field.kind === "relation") { renderRelated(); return; }
        values.classList.toggle("filter-editor-range", operator.value === "between");
        const count = operator.value === "between" ? 2 : 1;
        for (let index = 0; index < count; index++) {
          const wrap = element("div");
          const valueLabel = element("label", "", t(count === 2 ? index === 0 ? "from" : "to" : "value"));
          valueLabel.htmlFor = "filter-value-" + index;
          let input;
          if (field.kind === "boolean" || field.choices.length) {
            input = element("select");
            const choices = field.kind === "boolean" ? [["true", t("true")], ["false", t("false")]] : field.choices.map((value) => [value, value]);
            const empty = element("option", "", "—"); empty.value = ""; input.append(empty);
            choices.forEach(([value, text]) => { const option = element("option", "", text); option.value = value; input.append(option); });
          } else {
            input = element("input"); input.type = field.kind === "date" ? "date" : "text";
            if (["integer", "number"].includes(field.kind)) input.inputMode = field.kind === "integer" ? "numeric" : "decimal";
            input.maxLength = 500; input.autocomplete = "off";
            if (field.kind === "datetime") input.placeholder = "2026-10-30T12:00:00+03:00";
            if (field.kind === "time") input.placeholder = "12:00:00";
          }
          input.id = valueLabel.htmlFor;
          const raw = (initial ? condition?.values[index] : drafts[index]) || "";
          input.value = field.kind === "boolean" ? raw === "1" ? "true" : raw === "0" ? "false" : raw.toLowerCase() : raw;
          input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); submit(); } });
          input.addEventListener("input", () => { error.hidden = true; input.removeAttribute("aria-invalid"); });
          inputs.push(input); wrap.append(valueLabel, input); values.append(wrap);
        }
        if (["datetime", "time"].includes(field.kind)) {
          const hint = element("p", "field-help", t("iso")); hint.id = "filter-iso-help";
          inputs.forEach((input) => input.setAttribute("aria-describedby", hint.id)); values.append(hint);
        }
      }
      function renderRelated() {
        const chosen = element("p", "filter-related-selected");
        function showSelected() { chosen.textContent = selected ? t("selected") + ": " + relationLabel : ""; chosen.hidden = !selected; }
        showSelected();
        const search = element("input"); search.type = "search"; search.placeholder = t("search"); search.setAttribute("aria-label", t("search"));
        const status = element("p", "filter-lookup-status"); status.setAttribute("role", "status");
        const results = element("div", "filter-related-results");
        const pages = element("div", "filter-lookup-pages");
        values.append(search, chosen, status, results, pages);
        async function load(page = 1) {
          abort?.abort(); abort = new AbortController(); const current = ++sequence;
          status.textContent = t("loading"); results.replaceChildren(); pages.replaceChildren();
          results.setAttribute("aria-busy", "true");
          try {
            let data;
            if (root.loadOptions) data = await root.loadOptions(field, {search: search.value, page});
            else {
              const url = new URL(field.endpoint, location.href); url.searchParams.set("q", search.value); url.searchParams.set("page", page);
              const response = await fetch(url, {signal: abort.signal, credentials: "same-origin", headers: {Accept: "application/json"}});
              if (!response.ok || response.redirected) throw new Error("lookup");
              data = await response.json();
            }
            if (current !== sequence) return;
            results.removeAttribute("aria-busy");
            status.textContent = data.items.length ? "" : t("no_records");
            data.items.forEach((item) => {
              const option = button(item.label, "filter-field-option", () => {
                selected = item.key; relationLabel = item.label; showSelected();
                results.querySelectorAll("button").forEach((node) => node.setAttribute("aria-pressed", String(node === option)));
                error.hidden = true;
              });
              option.setAttribute("aria-pressed", String(selected === item.key)); results.append(option);
            });
            if (page > 1) pages.append(button(t("previous"), "button secondary small", () => load(page - 1)));
            if (data.has_next) pages.append(button(t("next"), "button secondary small", () => load(page + 1)));
          } catch (err) {
            if (current !== sequence || err.name === "AbortError") return;
            results.removeAttribute("aria-busy"); status.textContent = t("failed");
            pages.append(button(t("retry"), "button secondary small", () => load(page)));
          }
        }
        search.addEventListener("input", () => { stopLookup(); timer = setTimeout(() => load(), 200); });
        load();
      }
      function submit() {
        const raw = field.kind === "relation" ? [selected] : inputs.map((input) => input.value);
        if (!["null", "not_null"].includes(operator.value) && (!raw.length || raw.some((value) => !value))) {
          showError(t("required")); (inputs.find((input) => !input.value) || inputs[0])?.focus(); return;
        }
        try {
          const params = new URLSearchParams(new FormData(root));
          const next = updateQuery(params, condition, entries(field, operator.value, raw));
          if (root.navigate) root.navigate(next);
          else location.assign(root.action.split("?")[0] + "?" + next);
        } catch (err) { if (err.message !== "conflict") throw err; showError(t("conflict")); }
      }
      operator.addEventListener("change", () => { if (inputs.length) drafts = inputs.map((input) => input.value); renderValues(); position(); });
      renderValues(true);
      const messagesForCondition = condition?.parameters.map((name) => errors[name]).filter(Boolean);
      if (messagesForCondition?.length) showError(messagesForCondition.join(" "));
      position(); (inputs[0] || values.querySelector("input") || operator).focus();
    }
    // Keep GET search usable with active conditions while disabling duplicate fallback controls.
    conditions.forEach((condition) => condition.parameters.forEach((name, index) => {
      const input = element("input"); input.type = "hidden"; input.name = name; input.value = condition.values[index]; root.append(input);
    }));
    fallback.disabled = true; fallback.hidden = true; add.hidden = false;
    add.addEventListener("click", () => menu());
    root.closest(".record-list").querySelectorAll("[data-filter-edit]").forEach((link) => {
      const condition = conditions[Number(link.dataset.filterEdit)], field = fields.find((item) => item.id === condition.id);
      link.hidden = false; link.previousElementSibling.hidden = true;
      link.setAttribute("aria-haspopup", "dialog");
      if (condition.parameters.some((name) => errors[name])) link.classList.add("has-filter-error");
      link.addEventListener("click", (event) => { event.preventDefault(); anchor = link; editor(field, condition); show(link); (popover.querySelector(".filter-editor-values input, .filter-editor-values select") || popover.querySelector("select")).focus(); });
    });
    root.dataset.filterReady = "true";
    if (Object.keys(errors).length) {
      const bad = conditions.find((item) => item.parameters.some((name) => errors[name]));
      if (bad) { editor(fields.find((item) => item.id === bad.id), bad); show(add); (popover.querySelector('[aria-invalid="true"]') || popover.querySelector("select")).focus(); }
      if (errors.__all__ || !bad) {
        const alert = element("p", "alert", errors.__all__ || Object.values(errors).join(" "));
        alert.setAttribute("role", "alert"); root.append(alert);
      }
    }
  }
  window.QuiteAdmin = window.QuiteAdmin || {};
  window.QuiteAdmin.initFilters = () => document.querySelectorAll("[data-filter-builder]:not([data-filter-ready])").forEach(init);
  window.QuiteAdmin.initFilters();
})();
