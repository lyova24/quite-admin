/* UTC calendar selection and activity controls. No record values enter browser storage. */
(function (root) {
  "use strict";
  const picker = root.QuiteAdminDateTime || (typeof module !== "undefined" ? require('./datetime.js') : null);
  const {utcDate, isoDay, shiftDay, monthCells, presetBounds} = picker;
  if (typeof module !== "undefined") module.exports = {utcDate, isoDay, shiftDay, monthCells, presetBounds};
  const doc = root.document;
  if (!doc) return;
  function enhance(scope = doc) {
  const lifetime = new AbortController();
  const builder = scope.querySelector("[data-history-filter-builder]");
  if (builder) {
    builder.navigate ||= next => {
      next.delete("before"); next.delete("page");
      if (!next.has("action")) next.set("action", "");
      root.location.assign((builder.getAttribute("action") || root.location.pathname).split("?")[0] + "?" + next);
    };
    builder.loadOptions ||= async (field, {search, page, signal}) => {
      if (field.id === "subject") {
        const url = new URL(field.endpoint, root.location.href);
        url.searchParams.set("q", search.slice(0, 200));
        const response = await fetch(url, {signal, credentials: "same-origin", headers: {Accept: "application/json"}});
        if (!response.ok || response.redirected) throw new Error("lookup");
        const users = await response.json();
        return {items: users.map(user => ({key: user.subject, label: user.label, identity: user.subject})), has_next: false};
      }
      const matched = field.choices.filter(([value, label]) =>
        (value + " " + label).toLocaleLowerCase().includes(search.toLocaleLowerCase()));
      return {items: matched.slice((page - 1) * 25, page * 25).map(([key, label]) => ({key, label})),
        has_next: page * 25 < matched.length};
    };
  }
  const period = scope.querySelector("[data-history-period]");
  if (period) {
    const form = period.closest("form");
    const panel = period.querySelector(".history-period-panel");
    const summary = period.querySelector("summary");
    const mode = period.querySelector('[name="date_mode"]');
    const day = period.querySelector('[name="date"]');
    const from = period.querySelector('[name="date_from"]');
    const to = period.querySelector('[name="date_to"]');
    const today = period.dataset.today;
    const messages = JSON.parse(period.dataset.messages);
    const t = name => messages[name] || name;
    const fields = [mode, day, from, to];
    const tabs = Array.from(period.querySelectorAll("[data-period-tab]"));
    const calendars = [];
    let applied = fields.map(input => input.value);
    let submitted = false;
    function validate() {
      const invalid = mode.value === "range" && from.value && to.value && from.value > to.value;
      from.setCustomValidity(invalid ? t("Invalid history date range.") : "");
      period.querySelector("[data-period-error]").hidden = !invalid;
    }
    function renderCalendars() { calendars.forEach(calendar => calendar.render()); }
    function setView(view, seed = false) {
      if (seed && view === "day" && !day.value) day.value = from.value || to.value || today;
      if (seed && view === "range") {
        if (!from.value) from.value = day.value || today;
        if (!to.value) to.value = day.value || today;
      }
      panel.dataset.periodView = view;
      mode.value = view === "quick" ? "all" : view;
      day.disabled = view !== "day"; day.required = view === "day";
      from.disabled = to.disabled = view !== "range";
      tabs.forEach(tab => {
        const selected = tab.dataset.periodTab === view;
        tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1;
      });
      period.querySelectorAll("[data-period-panel]").forEach(item => {
        item.hidden = item.dataset.periodPanel !== view;
      });
      calendars.forEach(calendar => calendar.reset()); validate();
      if (period.open) panel.scrollIntoView({block: "nearest", inline: "nearest"});
    }
    function restore() {
      fields.forEach((input, index) => { input.value = applied[index]; });
      setView(mode.value === "all" ? "quick" : mode.value);
    }
    function close(focus) {
      period.open = false;
      if (!submitted) restore();
      if (focus) summary.focus();
    }
    period.querySelectorAll("[data-period-calendar]").forEach(host => {
      const input = period.querySelector('[name="' + host.dataset.periodCalendar + '"]');
      const label = t(input.name === "date" ? "Date (UTC)" : input.name === "date_from" ? "Date from (UTC)" : "Date to (UTC)");
      const calendar = picker.calendar(host, {
        getValue: () => input.value, label, t, today,
        getRange: () => mode.value === "range" ? [from.value, to.value] : [],
        onChange: value => { input.value = value; validate(); renderCalendars(); }
      });
      calendars.push(calendar);
      input.addEventListener("change", () => { calendar.reset(); validate(); renderCalendars(); });
    });
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => setView(tab.dataset.periodTab, true));
      tab.addEventListener("keydown", event => {
        const next = event.key === "ArrowRight" ? (index + 1) % tabs.length
          : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length
          : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
        if (next === null) return;
        event.preventDefault(); setView(tabs[next].dataset.periodTab, true); tabs[next].focus();
      });
    });
    period.querySelectorAll("[data-period-preset]").forEach(item => {
      item.addEventListener("click", () => {
        const bounds = presetBounds(item.dataset.periodPreset, today);
        if (!bounds) return;
        day.value = bounds.mode === "day" ? bounds.start : "";
        from.value = bounds.start; to.value = bounds.end;
        setView(bounds.mode === "all" ? "quick" : bounds.mode);
        form.requestSubmit();
      });
    });
    period.querySelector("[data-period-cancel]").addEventListener("click", () => close(true));
    period.addEventListener("toggle", () => {
      if (period.open) {
        applied = fields.map(input => input.value); submitted = false;
        tabs.find(tab => tab.getAttribute("aria-selected") === "true").focus({preventScroll: true});
        panel.scrollIntoView({block: "nearest"});
      } else if (!submitted) restore();
    });
    period.addEventListener("keydown", event => {
      if (event.key === "Escape" && period.open) { event.preventDefault(); close(true); }
    });
    doc.addEventListener("pointerdown", event => {
      if (period.open && !period.contains(event.target)) close(false);
    }, {signal: lifetime.signal});
    form.addEventListener("quite-admin:filter-open", () => { if (period.open) close(false); });
    form.addEventListener("invalid", event => { if (period.contains(event.target)) period.open = true; }, true);
    form.addEventListener("submit", () => { submitted = true; });
    setView(mode.value === "all" ? "quick" : mode.value);
  }
  const changes = scope.querySelectorAll("[data-history-changes]");
  if (changes.length) {
    scope.querySelectorAll("[data-history-expand], [data-history-controls]").forEach(
      element => { element.hidden = false; }
    );
    scope.querySelectorAll("[data-history-expand]").forEach(button => {
      button.addEventListener("click", () => {
        changes.forEach(detail => { detail.open = button.dataset.historyExpand === "true"; });
      });
    });
  }
  return () => lifetime.abort();
  }
  root.quiteAdminEnhanceHistory = enhance;
  enhance();
})(typeof window !== "undefined" ? window : globalThis);
