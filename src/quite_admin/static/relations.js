/* Progressive relationship selection. The native select remains the form value. */
(() => {
  "use strict";
  function initRelationPickers() {
  document.querySelectorAll("[data-relation-picker]:not([data-picker-ready])").forEach((root) => {
    root.dataset.pickerReady = "true";
    const select = root.querySelector("select");
    const messages = JSON.parse(root.dataset.messages);
    const chosen = new Map(Array.from(select.selectedOptions)
      .filter((option) => option.value).map((option) => [option.value, option.textContent]));
    const element = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text != null) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const button = (text, run) => {
      const node = element("button", text, "button secondary small");
      node.type = "button";
      node.addEventListener("click", run);
      return node;
    };
    const selected = element("div", null, "picker-selection");
    selected.setAttribute("aria-label", messages.selected);
    const details = element("details", null, "picker-menu");
    const summary = element("summary", messages.choose, "button secondary picker-trigger");
    summary.id = select.id + "-choose";
    select.labels[0].htmlFor = summary.id;
    const count = element("span", null, "muted");
    summary.append(count);
    const panel = element("div", null, "picker-panel");
    const search = element("input");
    search.type = "search";
    search.maxLength = 500;
    search.placeholder = messages.search;
    search.setAttribute("aria-label", messages.search + ": " + root.parentElement.querySelector("label").textContent.trim());
    const status = element("p", null, "field-help picker-status");
    status.setAttribute("role", "status");
    const results = element("div", null, "picker-results");
    results.setAttribute("role", "group");
    results.setAttribute("aria-label", messages.results);
    const pager = element("div", null, "picker-pagination");
    let page = 1, items = [], controller, sequence = 0, timer, loaded = false;

    function sync() {
      for (const [key, label] of chosen) {
        if (!Array.from(select.options).some((option) => option.value === key)) {
          select.add(new Option(label, key));
        }
      }
      for (const option of select.options) option.selected = chosen.has(option.value);
      if (!chosen.size && !select.multiple) select.value = "";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      selected.replaceChildren();
      for (const [key, label] of chosen) {
        const chip = element("span", null, "picker-chip");
        chip.append(element("span", label));
        const remove = button("×", () => {
          chosen.delete(key);
          sync();
          renderItems();
          summary.focus();
        });
        remove.setAttribute("aria-label", messages.remove + ": " + label);
        chip.append(remove);
        selected.append(chip);
      }
      count.textContent = chosen.size ? ` · ${chosen.size}` : "";
    }
    function renderItems() {
      results.replaceChildren();
      for (const item of items) {
        const label = element("label", null, "picker-option");
        const check = element("input");
        check.type = "checkbox";
        check.checked = chosen.has(item.key);
        check.addEventListener("change", () => {
          if (check.checked) {
            if (select.multiple && chosen.size >= 1000) {
              check.checked = false;
              status.textContent = messages.limit;
              return;
            }
            if (!select.multiple) chosen.clear();
            chosen.set(item.key, item.label);
          } else chosen.delete(item.key);
          sync();
          for (const input of results.querySelectorAll("input")) {
            input.checked = chosen.has(input.dataset.key);
          }
          if (!select.multiple) { details.open = false; summary.focus(); }
        });
        check.dataset.key = item.key;
        label.append(check, element("span", item.label));
        results.append(label);
      }
    }
    async function load() {
      clearTimeout(timer);
      controller?.abort();
      controller = new AbortController();
      const current = ++sequence;
      status.textContent = messages.loading;
      results.setAttribute("aria-busy", "true");
      const url = new URL(root.dataset.endpoint, location.href);
      url.searchParams.set("q", search.value);
      url.searchParams.set("page", page);
      try {
        let data;
        if (root.loadOptions) data = await root.loadOptions({ search: search.value, page });
        else {
          const response = await fetch(url, { signal: controller.signal, mode: "same-origin", credentials: "same-origin" });
          if (!response.ok) throw new Error("Request failed");
          data = await response.json();
        }
        if (current !== sequence) return;
        items = data.items;
        loaded = true;
        renderItems();
        status.textContent = data.total ? `${messages.results}: ${data.total} · ${page}` : messages.empty;
        pager.replaceChildren();
        const previous = button(messages.previous, () => { page--; load(); });
        previous.disabled = page <= 1;
        const next = button(messages.next, () => { page++; load(); });
        next.disabled = !data.has_next;
        pager.append(previous, next);
      } catch (error) {
        if (error.name === "AbortError" || current !== sequence) return;
        loaded = false;
        results.replaceChildren();
        status.textContent = messages.failed;
        pager.replaceChildren(button(messages.retry, load));
      } finally {
        if (current === sequence) results.removeAttribute("aria-busy");
      }
    }
    search.addEventListener("input", () => {
      page = 1;
      controller?.abort();
      ++sequence;
      clearTimeout(timer);
      timer = setTimeout(load, 250);
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); load(); }
      if (event.key === "Escape") { details.open = false; summary.focus(); }
    });
    details.addEventListener("toggle", () => {
      if (details.open) { search.focus(); if (!loaded) load(); }
    });
    panel.append(search, status, results, pager);
    details.append(summary, panel);
    root.append(selected, details);
    root.classList.add("is-enhanced");
    sync();
  });
  }
  window.QuiteAdmin = { ...window.QuiteAdmin, initRelationPickers };
  initRelationPickers();
})();
