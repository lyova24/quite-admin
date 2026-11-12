/* Progressive relationship selection. The native select remains the form value. */
(() => {
  "use strict";
  let closeActivePicker;
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
      const heading = element("div", null, "picker-selection-heading");
      const selectionCount = element("span");
      const selected = element("div", null, "picker-selection");
      selected.setAttribute("role", "group");
      selected.setAttribute("aria-label", messages.selected);
      const details = element("details", null, "picker-menu");
      const summary = element("summary", null, "button secondary picker-trigger");
      const triggerLabel = element("span");
      const count = element("span", null, "picker-count");
      count.id = select.id + "-count";
      summary.append(triggerLabel, count);
      summary.id = select.id + "-choose";
      const label = select.labels[0];
      if (label) {
        if (!label.id) label.id = select.id + "-label";
        triggerLabel.id = select.id + "-trigger-label";
        summary.setAttribute("aria-labelledby", label.id + " " + triggerLabel.id + " " + count.id);
        label.htmlFor = summary.id;
        label.addEventListener("click", () => { details.open = true; summary.focus(); });
      }
      for (const attribute of ["aria-describedby", "aria-invalid"]) {
        if (select.hasAttribute(attribute)) summary.setAttribute(attribute, select.getAttribute(attribute));
      }
      const panel = element("div", null, "picker-panel");
      panel.id = select.id + "-panel";
      summary.setAttribute("aria-controls", panel.id);
      summary.setAttribute("aria-expanded", "false");
      const search = element("input");
      search.type = "search";
      search.maxLength = 500;
      search.placeholder = messages.search;
      search.setAttribute("aria-label", messages.search + (label ? ": " + label.textContent.trim() : ""));
      const status = element("p", null, "field-help picker-status");
      status.setAttribute("role", "status");
      const results = element("div", null, "picker-results");
      results.setAttribute("role", "group");
      results.setAttribute("aria-label", messages.results);
      const pager = element("div", null, "picker-pagination");
      let page = 1, items = [], controller, sequence = 0, timer, loaded = false, pending = false;
      let openLifetime, detachObserver, preferredHeight = 0;

      function closePicker(restoreFocus = false) {
        details.open = false;
        summary.setAttribute("aria-expanded", "false");
        openLifetime?.abort();
        openLifetime = null;
        detachObserver?.disconnect();
        if (closeActivePicker === closePicker) closeActivePicker = null;
        if (restoreFocus) summary.focus({preventScroll:true});
      }

      function positionPanel(remeasure = false) {
        if (!details.open || !root.isConnected) return;
        if (remeasure === true || !preferredHeight) {
          details.classList.remove("picker-constrained");
          preferredHeight = panel.getBoundingClientRect().height;
        }
        const trigger = summary.getBoundingClientRect();
        const viewport = window.visualViewport;
        const top = viewport?.offsetTop || 0;
        const bottom = top + (viewport?.height || document.documentElement.clientHeight);
        const below = bottom - trigger.bottom - 8;
        const above = trigger.top - top - 8;
        details.classList.toggle("picker-opens-up", below < preferredHeight && above > below);
        details.classList.toggle("picker-constrained", Math.max(above, below) < preferredHeight);
      }
      const clear = button(messages.clear || "Clear selection", () => {
        chosen.clear();
        sync();
        renderItems();
        summary.focus();
      });
      clear.classList.add("picker-clear");
      heading.append(selectionCount, clear);

      function sync() {
        const available = new Set(Array.from(select.options, option => option.value));
        for (const [key, label] of chosen) {
          if (!available.has(key)) select.add(new Option(label, key));
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
        heading.hidden = selected.hidden = !chosen.size;
        selectionCount.textContent = `${messages.selected} · ${chosen.size}`;
        triggerLabel.textContent = select.multiple ? messages.choose
          : chosen.size ? (messages.change || "Change selection") : (messages.chooseOne || "Choose a record");
        count.textContent = chosen.size;
        count.setAttribute("aria-label", messages.selected + ": " + chosen.size);
        count.hidden = !select.multiple || !chosen.size;
        positionPanel();
      }
      function renderItems() {
        results.replaceChildren();
        for (const item of items) {
          const label = element("label", null, "picker-option");
          const check = element("input");
          check.type = select.multiple ? "checkbox" : "radio";
          check.checked = chosen.has(item.key);
          check.disabled = pending;
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
            if (!select.multiple) closePicker(true);
          });
          check.dataset.key = item.key;
          const text = element("span", null, "picker-option-text");
          const name = element("span", item.label);
          name.title = item.label;
          text.append(name);
          const description = [item.identity, item.description]
            .filter((part, index, parts) => part && part !== item.label && parts.indexOf(part) === index).join(" · ");
          if (description) {
            const context = element("small", description, "picker-option-description");
            context.title = description;
            text.append(context);
          }
          label.append(check, text);
          results.append(label);
        }
      }
      function busy() {
        pending = true;
        results.setAttribute("aria-busy", "true");
        for (const input of results.querySelectorAll("input")) input.disabled = true;
        for (const control of pager.querySelectorAll("button")) control.disabled = true;
      }
      async function load() {
        clearTimeout(timer);
        controller?.abort();
        controller = new AbortController();
        const current = ++sequence;
        status.textContent = messages.loading;
        busy();
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
          pending = false;
          renderItems();
          status.textContent = data.total ? `${messages.results}: ${data.total} · ${page}` : messages.empty;
          pager.replaceChildren();
          const previous = button(messages.previous, () => { page--; load(); search.focus(); });
          previous.disabled = page <= 1;
          const next = button(messages.next, () => { page++; load(); search.focus(); });
          next.disabled = !data.has_next;
          pager.append(previous, next);
          pager.hidden = page <= 1 && !data.has_next;
        } catch (error) {
          if (error.name === "AbortError" || current !== sequence) return;
          loaded = false;
          pending = false;
          items = [];
          results.replaceChildren();
          status.textContent = messages.failed;
          pager.hidden = false;
          pager.replaceChildren(button(messages.retry, () => { load(); search.focus({preventScroll:true}); }));
        } finally {
          if (current === sequence) {
            results.removeAttribute("aria-busy");
            positionPanel(true);
          }
        }
      }
      search.addEventListener("input", () => {
        page = 1;
        loaded = false;
        controller?.abort();
        ++sequence;
        busy();
        clearTimeout(timer);
        timer = setTimeout(load, 250);
      });
      root.addEventListener("keydown", (event) => {
        if (!details.open) return;
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          closePicker(true);
        }
        if (event.target === search && event.key === "Enter") { event.preventDefault(); load(); }
        const options = [...results.querySelectorAll("input:not(:disabled)")];
        if (event.target === search && event.key === "ArrowDown" && options.length) {
          event.preventDefault(); options[0].focus();
        } else if (options.includes(event.target)) {
          const index = options.indexOf(event.target);
          const next = event.key === "ArrowDown" ? (index + 1) % options.length
            : event.key === "ArrowUp" ? (index + options.length - 1) % options.length
            : event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : -1;
          if (next >= 0) { event.preventDefault(); options[next].focus(); }
          if (event.key === "Enter") { event.preventDefault(); event.target.click(); }
        }
      });
      details.addEventListener("toggle", () => {
        summary.setAttribute("aria-expanded", String(details.open));
        if (!details.open) { closePicker(); return; }
        closeActivePicker?.();
        closeActivePicker = closePicker;
        openLifetime = new AbortController();
        const options = {signal:openLifetime.signal};
        document.addEventListener("pointerdown", event => {
          if (!root.contains(event.target)) closePicker();
        }, options);
        window.addEventListener("resize", () => positionPanel(true), options);
        window.addEventListener("blur", () => closePicker(), options);
        window.addEventListener("scroll", positionPanel, {...options, capture:true, passive:true});
        window.visualViewport?.addEventListener("resize", () => positionPanel(true), options);
        window.visualViewport?.addEventListener("scroll", positionPanel, options);
        detachObserver = new MutationObserver(() => { if (!root.isConnected) closePicker(); });
        detachObserver.observe(document.body, {childList:true, subtree:true});
        positionPanel(true);
        search.focus({preventScroll:true});
        if (!loaded) load();
      });
      details.addEventListener("focusout", event => {
        // Clicking label text briefly focuses the body before its native input.
        // Let that activation finish; outside pointers and window blur close separately.
        if (event.relatedTarget && !details.contains(event.relatedTarget)) closePicker();
      });
      panel.append(search, status, results, pager);
      details.append(summary, panel);
      root.append(heading, selected, details);
      root.classList.add("is-enhanced");
      sync();
    });
  }
  window.QuiteAdmin = { ...window.QuiteAdmin, initRelationPickers };
  initRelationPickers();
})();
