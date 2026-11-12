// Fictional, browser-local activity. Durable auditing is provided by the Python service store.
export const actions = {changes: "Changes only", list: "Browse records", view: "View", create: "Create", edit: "Update", inline_edit: "Inline update", delete: "Delete", export: "Export", login: "Sign in", logout: "Sign out"};
const writes = new Set(["create", "edit", "inline_edit", "delete"]);
export const isWrite = event => writes.has(event.action) || event.action.startsWith('action:');
export function changesFor(collection, before, after) {
  const changes = [];
  for (const field of collection.fields) {
    const a = before?.values[field.name], b = after?.values[field.name];
    if (before && after && a === b) continue;
    changes.push({name: field.name, label: field.label, kind: field.kind, before: a ?? null, after: b ?? null, before_present: !!before, after_present: !!after});
  }
  for (const relation of collection.relations) {
    const a = before?.links[relation.name] || [], b = after?.links[relation.name] || [];
    if (JSON.stringify([...a].sort()) === JSON.stringify([...b].sort())) continue;
    changes.push({name: relation.name, label: relation.label, kind: "relation", before: a.join("\n"), after: b.join("\n"), before_present: !!before, after_present: !!after});
  }
  return changes;
}
export function initialActivity(seed) {
  const product = seed.collections.products.records[0], schedule = seed.collections.schedules.records[0];
  const now = new Date();
  const event = (id, days, subject, collection, action, key, changes = [], outcome = "success", status_code = 200) => {
    const at = new Date(now); at.setUTCDate(at.getUTCDate() - days); at.setUTCHours(10, 10 + id, 0, 0);
    return {id, occurred_at: at.toISOString(), subject, display_name: subject === "admin" ? "Demo Admin" : "Olivia Chen", collection, action, key, changes, outcome, status_code};
  };
  return [
    event(6, 0, "admin", "products", "edit", product.key, [{name:"price",label:"Price",kind:"number",before:"16.00",after:product.values.price,before_present:true,after_present:true}, {name:"stock",label:"Stock",kind:"integer",before:"120",after:product.values.stock,before_present:true,after_present:true}]),
    event(5, 0, "olivia", "schedules", "inline_edit", schedule.key, [{name:"approved",label:"Approved",kind:"boolean",before:"false",after:schedule.values.approved,before_present:true,after_present:true}]),
    event(4, 0, "olivia", "products", "edit", product.key, [], "failure", 409),
    event(3, 0, "admin", "products", "export", null),
    event(2, 1, "olivia", "schedules", "create", schedule.key, changesFor(seed.collections.schedules, null, schedule)),
    event(1, 1, "admin", "", "login", null),
  ];
}
export function filterActivity(events, query) {
  const action = query.get("action") ?? "changes", mode = query.get("date_mode");
  const start = mode === "day" ? query.get("date") : mode === "range" ? query.get("date_from") : "";
  const end = mode === "day" ? query.get("date") : mode === "range" ? query.get("date_to") : "";
  return events.filter(event => {
    if (query.get("subject") && event.subject !== query.get("subject")) return false;
    const collection = query.get("collection");
    if (collection && event.collection !== (collection === "__auth__" ? "" : collection)) return false;
    if (action === "changes" ? !isWrite(event) : action && event.action !== action) return false;
    if (query.get("outcome") && event.outcome !== query.get("outcome")) return false;
    const day = event.occurred_at.slice(0, 10);
    return (!start || day >= start) && (!end || day <= end);
  }).sort((a,b) => b.occurred_at.localeCompare(a.occurred_at) || b.id - a.id);
}
export function activityPage({store, seed, language, t, e, href, query}) {
  const url = updates => {
    const next = new URLSearchParams(query);
    for (const [name,value] of Object.entries(updates)) value == null ? next.delete(name) : next.set(name,value);
    return "#/history?" + next;
  };
  const view = query.get("view") === "table" ? "table" : "journal";
  const page = Math.max(1, Number(query.get("page")) || 1), limit = 10;
  const events = filterActivity(store.activity, query), rows = events.slice((page - 1) * limit, page * limit);
  const actionNames = {...actions};
  for (const collection of Object.values(store.state))
    for (const action of [...(collection.actions || []), ...(collection.bulkActions || [])])
      actionNames['action:' + action.slug] = action.label;
  const users = [...new Map(store.activity.map(event => [event.subject, event.display_name])).entries()];
  const choices = {subject: users, collection: [["__auth__",t("Authentication")],...Object.entries(store.state).map(([slug,c])=>[slug,c.label])], action: Object.entries(actionNames).map(([value,label])=>[value,t(label)]), outcome:[["success",t("Success")],["failure",t("Failure")]]};
  const fields = Object.entries({subject:"User",collection:"Collection",action:"Action",outcome:"Result"}).map(([id,label])=>({id,label:t(label),kind:"relation",operators:["eq"],key_search:id==="subject",choices:choices[id]}));
  const messages = {...seed.filterMessages[language],type_relation:t("Choice"),search:t("Search values"),search_id:t("Search by name or identifier."),search_text:t("Search values")};
  const active = fields.map(field => {
    const value = query.get(field.id) ?? (field.id === "action" ? "changes" : "");
    return value ? {id:field.id,parameters:[field.id],operator:"eq",values:[value],label:field.label+": "+(choices[field.id].find(([key])=>key===value)?.[1]||value)} : null;
  }).filter(Boolean);
  const chips = active.map((item,index)=>`<span class="filter-chip filter-condition"><span class="filter-label">${e(item.label)}</span><button class="filter-edit" type="button" data-filter-edit="${index}" hidden>${e(item.label)}</button><a class="filter-remove" aria-label="${e(t("Remove")+": "+item.label)}" href="${e(url({[item.id]:item.id==='action'?'':null,page:null}))}">×</a></span>`).join("");
  function value(change, side) {
    const text = change[side];
    return !change[side+"_present"] ? `<span class="change-empty">${e(t("Not present"))}</span>` : text == null ? '<span class="change-empty change-null">NULL</span>' : text === "" ? `<span class="change-empty">${e(t("Empty string"))}</span>` : change.kind === "boolean" ? `<span class="change-boolean">${e(t(text==='true'?'True':'False'))}</span>` : `<pre class="change-value">${e(text)}</pre>`;
  }
  function diff(event, open = false) {
    if (!event.changes.length) return isWrite(event) ? `<p class="activity-note">${e(t(event.outcome==='failure'?'Changes were not saved.':'No visible field changes.'))}</p>` : "";
    return `<details class="activity-changes" data-history-changes ${open?'open':''}><summary><span class="activity-change-count">${e(t("Changed fields: {count}",{count:event.changes.length}))}</span><span class="activity-field-preview">${e(event.changes.map(c=>c.label).join(', '))}</span><span class="activity-chevron" aria-hidden="true">⌄</span></summary><div class="activity-diff" role="table" aria-label="${e(t('Field changes'))}"><div class="activity-diff-header" role="row">${['Field','Before','After'].map(label=>`<span role="columnheader">${e(t(label))}</span>`).join('')}</div>${event.changes.map(change=>`<div class="activity-diff-row" role="row"><div class="activity-diff-field" role="rowheader"><strong>${e(change.label)}</strong><code>${e(change.name)}</code></div>${['before','after'].map(side=>`<div class="activity-${side}" role="cell"><span class="change-mobile-label">${e(t(side==='before'?'Before':'After'))}</span>${value(change,side)}</div>`).join('')}</div>`).join('')}</div></details>`;
  }
  const collectionLabel = event => event.collection ? store.collection(event.collection).label : t("Authentication");
  const record = event => {
    if (!event.key) return "";
    const row = store.collection(event.collection).records.find(row=>row.key===event.key);
    return row ? `<a class="activity-record" href="${href(event.collection,event.key)}">${e(row.values.id != null ? '#' + row.values.id : store.label(event.collection,row))} ↗</a>` : "";
  };
  const empty = `<div class="history-empty"><h2>${e(t('No activity found'))}</h2><p>${e(t('Choose another user or collection, or clear the filters.'))}</p></div>`;
  let content;
  if (view === "table") content = `<div class="panel history-table-panel"><div class="table-scroll"><table class="history-table" aria-label="${e(t('Activity history'))}"><thead><tr>${['Time (UTC)','User','Collection','Action','Result','Field changes'].map(label=>`<th scope="col">${e(t(label))}</th>`).join('')}</tr></thead><tbody>${rows.map(event=>`<tr data-activity-id="${event.id}"><td><time>${e(event.occurred_at.slice(0,19).replace('T',' '))}</time></td><td>${e(event.display_name)}<small class="history-subject">${e(event.subject)}</small></td><td>${e(collectionLabel(event))}</td><td>${e(t(actionNames[event.action]||event.action))}${record(event)}</td><td><span class="boolean-badge ${event.outcome==='success'?'yes':'no'}">${e(t(event.outcome==='success'?'Success':'Failure'))}</span> ${event.status_code}</td><td>${diff(event)}</td></tr>`).join('')||`<tr><td colspan="6">${empty}</td></tr>`}</tbody></table></div></div>`;
  else {
    const groups = new Map();
    for (const event of rows) {
      const day = event.occurred_at.slice(0,10);
      if (!groups.has(day)) groups.set(day,[]);
      groups.get(day).push(event);
    }
    content = `<div class="activity-journal" aria-label="${e(t('Activity journal'))}">${[...groups].map(([day,events])=>`<section class="activity-day"><h2 class="activity-day-heading"><span>${e(day===new Date().toISOString().slice(0,10)?t('Today'):day)}</span><time>${e(day.split('-').reverse().join('.'))}</time></h2><ol class="activity-events">${events.map(event=>`<li class="activity-entry"><article class="activity-event ${isWrite(event)?'':'activity-event-compact'}" data-activity-id="${event.id}"><div class="activity-event-heading"><span class="activity-symbol ${event.outcome==='failure'?'activity-symbol-failed':''}" aria-hidden="true">${event.outcome==='failure'?'!':event.action==='create'?'+':'↗'}</span><div class="activity-event-title"><div class="activity-title-line"><h3>${e(t(actionNames[event.action]||event.action))}</h3><span class="activity-collection">${e(collectionLabel(event))}</span>${record(event)}</div><div class="activity-byline"><span class="activity-avatar" aria-hidden="true">${e(event.display_name[0])}</span><strong>${e(event.display_name)}</strong><span class="history-subject">${e(event.subject)}</span><span>·</span><time>${e(event.occurred_at.slice(11,19))}</time></div></div><span class="activity-result ${event.outcome==='failure'?'activity-result-failed':''}" title="HTTP ${event.status_code}">${e(t(event.outcome==='success'?'Success':'Failure'))}${event.outcome==='failure'?' · '+event.status_code:''}</span></div>${diff(event,event===events.find(item=>item.changes.length))}</article></li>`).join('')}</ol></section>`).join('')||empty}</div>`;
  }
  return `<h1 class="sr-only">${e(t("Activity history"))}</h1><section class="record-list history-workspace"><form class="history-filters" data-filter-builder data-demo-history data-fields="${e(JSON.stringify(fields))}" data-conditions="${e(JSON.stringify(active))}" data-messages="${e(JSON.stringify(messages))}"><input type="hidden" name="view" value="${view}"><fieldset data-filter-fallback hidden></fieldset><button class="button secondary filter-add" type="button" data-filter-add hidden>+ ${e(t('Add filter'))}</button><div class="active-filters">${chips}${active.length?`<a class="link-button" href="${e(url({subject:null,collection:null,action:'',outcome:null,page:null}))}">${e(t('Clear all'))}</a>`:''}</div>${seed.historyPeriods[language]}</form><div class="history-journal-tools"><div class="history-view-tools"><nav class="history-view-toggle" aria-label="${e(t('Activity view'))}">${['journal','table'].map(mode=>`<a href="${e(url({view:mode}))}" ${view===mode?'aria-current="page"':''}>${e(t(mode==='journal'?'Journal':'Table'))}</a>`).join('')}</nav><span class="muted">${e(t('{count} on this page',{count:rows.length}))}</span></div><div class="button-group"><button class="link-button" type="button" data-history-expand="true" hidden>${e(t('Expand all changes'))}</button><button class="link-button" type="button" data-history-expand="false" hidden>${e(t('Collapse all changes'))}</button></div></div>${content}<footer class="history-pagination"><span class="muted">${e(t('Time (UTC)'))}</span><div class="button-group">${page>1?`<a class="button secondary" href="${e(url({page:null}))}">${e(t('Latest events'))}</a>`:''}${page*limit<events.length?`<a class="button secondary" href="${e(url({page:page+1}))}">${e(t('Older events'))} →</a>`:''}</div></footer></section>`;
}
