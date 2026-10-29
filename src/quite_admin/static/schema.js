/* Metadata-only schema viewer. Pure layout/projection functions also run in Node tests. */
(() => {
  "use strict";
  const ROW = 26, HEADER = 56, FOOTER = 30;
  const key = (edge) => [edge.source, edge.target, [...edge.sourceFields].sort().join(","), [...edge.targetFields].sort().join(","), edge.kind].join("|");
  const compactFields = (node) => node.fields.filter((field) => field.pk || field.linked || field.fk);

  function projectGraph(graph, visible, opened) {
    const catalog = new Map([...graph.nodes, ...(graph.junctions || [])].map((node) => [node.id, node]));
    const ordinary = new Set(graph.nodes.map((node) => node.id));
    const edges = new Map();
    const add = (edge) => {
      if (!visible.has(edge.source) || !visible.has(edge.target)) return;
      const signature = key(edge), previous = edges.get(signature);
      if (previous) previous.originals.push(...(edge.originals || []));
      else edges.set(signature, { ...edge, originals: [...(edge.originals || [])] });
    };
    for (const edge of graph.edges) {
      if (edge.junction && visible.has(edge.junction) && (opened.has(edge.id) || !ordinary.has(edge.junction))) {
        add({ id: edge.id + "-left", source: edge.source, target: edge.junction, sourceFields: edge.sourceFields, targetFields: edge.junctionSourceFields, kind: "o2m", label: edge.label, originals: [edge.id] });
        add({ id: edge.id + "-right", source: edge.target, target: edge.junction, sourceFields: edge.targetFields, targetFields: edge.junctionTargetFields, kind: "o2m", label: edge.label, originals: [edge.id] });
      } else add(edge);
    }
    return { nodes: [...visible].filter((id) => catalog.has(id)).map((id) => catalog.get(id)), edges: [...edges.values()] };
  }

  function layoutSchema(inputNodes, edges, expanded = new Set(), aspect = 1.8) {
    const nodes = inputNodes.map((node) => {
      const fields = expanded.has(node.id) ? node.fields : compactFields(node);
      const longest = Math.max(node.name.length, ...node.fields.map((field) => field.name.length));
      return { ...node, shownFields: fields, width: Math.max(240, Math.min(360, longest * 7 + 110)), height: HEADER + Math.max(1, fields.length) * ROW + FOOTER };
    });
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const adjacency = new Map(nodes.map((node) => [node.id, new Set()]));
    for (const edge of edges) if (byId.has(edge.source) && byId.has(edge.target)) {
      adjacency.get(edge.source).add(edge.target); adjacency.get(edge.target).add(edge.source);
    }
    const visited = new Set(), components = [];
    for (const first of [...byId.keys()].sort()) {
      if (visited.has(first)) continue;
      const ids = [], queue = [first]; visited.add(first);
      for (let i = 0; i < queue.length; i++) {
        const id = queue[i]; ids.push(id);
        for (const next of [...adjacency.get(id)].sort()) if (!visited.has(next)) { visited.add(next); queue.push(next); }
      }
      components.push(ids);
    }
    function arrange(ids, verticalPairs) {
      const directed = new Map(ids.map((id) => [id, []]));
      for (const edge of edges) if (directed.has(edge.source) && directed.has(edge.target) && edge.source !== edge.target && !(verticalPairs && edge.kind === "o2o")) directed.get(edge.source).push(edge.target);
      // Condense cycles before assigning layers, so every graph terminates deterministically.
      let counter = 0;
      const indexes = new Map(), low = new Map(), stack = [], onStack = new Set(), groups = [];
      function visit(id) {
        indexes.set(id, counter); low.set(id, counter++); stack.push(id); onStack.add(id);
        for (const next of directed.get(id)) {
          if (!indexes.has(next)) { visit(next); low.set(id, Math.min(low.get(id), low.get(next))); }
          else if (onStack.has(next)) low.set(id, Math.min(low.get(id), indexes.get(next)));
        }
        if (low.get(id) === indexes.get(id)) {
          const group = []; let member;
          do { member = stack.pop(); onStack.delete(member); group.push(member); } while (member !== id);
          groups.push(group.sort());
        }
      }
      for (const id of [...ids].sort()) if (!indexes.has(id)) visit(id);
      const groupOf = new Map(); groups.forEach((group, index) => group.forEach((id) => groupOf.set(id, index)));
      const incoming = groups.map(() => new Set());
      for (const [id, nexts] of directed) for (const next of nexts) if (groupOf.get(id) !== groupOf.get(next)) incoming[groupOf.get(next)].add(groupOf.get(id));
      const ranks = new Map();
      function rank(group) {
        if (!ranks.has(group)) ranks.set(group, Math.max(0, ...[...incoming[group]].map((parent) => rank(parent) + 1)));
        return ranks.get(group);
      }
      const layers = [];
      groups.forEach((group, index) => { const value = rank(index); (layers[value] ||= []).push(...group); });
      layers.forEach((layer) => layer.sort());
      for (let pass = 0; pass < 4; pass++) {
        const positions = new Map(); layers.forEach((layer) => layer.forEach((id, index) => positions.set(id, index)));
        for (const layer of (pass % 2 ? [...layers].reverse() : layers)) layer.sort((a, b) => {
          const score = (id) => { const neighbors = [...adjacency.get(id)].filter((next) => !layer.includes(next)); return neighbors.length ? neighbors.reduce((sum, next) => sum + positions.get(next), 0) / neighbors.length : positions.get(id); };
          return score(a) - score(b) || a.localeCompare(b);
        });
      }
      const heights = layers.map((layer) => layer.reduce((sum, id) => sum + byId.get(id).height, 0) + Math.max(0, layer.length - 1) * 48);
      const height = Math.max(...heights), output = []; let x = 0;
      layers.forEach((layer, index) => {
        let y = (height - heights[index]) / 2;
        for (const id of layer) { const node = byId.get(id); output.push({ ...node, x, y }); y += node.height + 48; }
        x += Math.max(...layer.map((id) => byId.get(id).width)) + 110;
      });
      return { nodes: output, width: x - 110, height, id: ids[0] };
    }
    function pack(verticalPairs) {
      const parts = components.map((ids) => arrange(ids, verticalPairs)).sort((a, b) => b.height * b.width - a.height * a.width || a.id.localeCompare(b.id));
      const area = parts.reduce((sum, part) => sum + part.width * part.height, 0);
      const maxWidth = Math.max(0, ...parts.map((part) => part.width), Math.sqrt(area * aspect) * 1.6);
      const result = []; let x = 32, y = 32, rowHeight = 0;
      for (const part of parts) {
        if (x > 32 && x + part.width > maxWidth + 32) { x = 32; y += rowHeight + 64; rowHeight = 0; }
        for (const node of part.nodes) result.push({ ...node, x: node.x + x, y: node.y + y });
        x += part.width + 64; rowHeight = Math.max(rowHeight, part.height);
      }
      return result;
    }
    const horizontal = pack(false), paired = pack(true);
    const score = (items) => { const box = bounds(items); return Math.max(box.width / aspect, box.height); };
    return score(paired) < score(horizontal) ? paired : horizontal;
  }

  function bounds(nodes) {
    if (!nodes.length) return { x: 0, y: 0, width: 600, height: 360 };
    const x = Math.min(...nodes.map((node) => node.x)) - 32, y = Math.min(...nodes.map((node) => node.y)) - 32;
    return { x, y, width: Math.max(...nodes.map((node) => node.x + node.width)) - x + 32, height: Math.max(...nodes.map((node) => node.y + node.height)) - y + 32 };
  }
  function segmentBlocked(a, b, obstacles) {
    return obstacles.some((r) => a.x === b.x ? a.x > r.x && a.x < r.x + r.width && Math.max(a.y, b.y) > r.y && Math.min(a.y, b.y) < r.y + r.height : a.y > r.y && a.y < r.y + r.height && Math.max(a.x, b.x) > r.x && Math.min(a.x, b.x) < r.x + r.width);
  }
  function routeEdge(source, target, edge, nodes, lane = 0) {
    const port = (node, fields) => {
      const indexes = fields.map((name) => node.shownFields.findIndex((field) => field.name === name)).filter((index) => index >= 0);
      return node.y + HEADER + (indexes.length ? indexes.reduce((a, b) => a + b, 0) / indexes.length + .5 : .5) * ROW;
    };
    const rightward = target.x >= source.x + source.width + 20, leftward = target.x + target.width <= source.x - 20;
    const sourceRight = !leftward, targetRight = !(rightward || leftward) || leftward;
    const start = { x: source.x + (sourceRight ? source.width : 0), y: port(source, edge.sourceFields) };
    const end = { x: target.x + (targetRight ? target.width : 0), y: port(target, edge.targetFields) };
    const a = { x: start.x + (sourceRight ? 24 : -24), y: start.y }, b = { x: end.x + (targetRight ? 24 : -24), y: end.y };
    const obstacles = nodes.map((node) => ({ x: node.x - 10, y: node.y - 10, width: node.width + 20, height: node.height + 20 }));
    const valid = (points) => points.slice(1).every((point, index) => !segmentBlocked(points[index], point, obstacles));
    const middle = rightward || leftward ? (a.x + b.x) / 2 + lane * 12 : Math.max(a.x, b.x) + 24 + lane * 16;
    let route = [a, { x: middle, y: a.y }, { x: middle, y: b.y }, b];
    if (source.id === target.id && a.y === b.y) route = [a, { x: middle, y: a.y }, { x: middle, y: a.y - 42 }, { x: b.x, y: a.y - 42 }, b];
    if (!valid(route)) {
      // Manhattan A* over obstacle boundaries; short routes avoid this allocation entirely.
      const xs = [...new Set([a.x, b.x, ...obstacles.flatMap((r) => [r.x - 8, r.x + r.width + 8])])].sort((x, y) => x - y);
      const ys = [...new Set([a.y, b.y, ...obstacles.flatMap((r) => [r.y - 8, r.y + r.height + 8])])].sort((x, y) => x - y);
      const encode = (x, y) => y * xs.length + x, point = (id) => ({ x: xs[id % xs.length], y: ys[Math.floor(id / xs.length)] });
      const first = encode(xs.indexOf(a.x), ys.indexOf(a.y)), last = encode(xs.indexOf(b.x), ys.indexOf(b.y));
      const cost = new Map([[first, 0]]), previous = new Map(), queue = [[first, 0]], closed = new Set();
      while (queue.length) {
        queue.sort((x, y) => y[1] - x[1]);
        const [id] = queue.pop(); if (closed.has(id)) continue;
        if (id === last) { const result = []; let current = id; while (current != null) { result.push(point(current)); current = previous.get(current); } route = result.reverse(); break; }
        closed.add(id);
        const x = id % xs.length, y = Math.floor(id / xs.length), current = point(id);
        for (const [nx, ny] of [[x - 1, y], [x + 1, y], [x, y - 1], [x, y + 1]]) {
          if (nx < 0 || nx >= xs.length || ny < 0 || ny >= ys.length) continue;
          const next = encode(nx, ny), p = point(next);
          if (closed.has(next) || segmentBlocked(current, p, obstacles)) continue;
          const parent = previous.get(id), before = parent == null ? current : point(parent);
          const bend = parent != null && (before.x === current.x) !== (current.x === p.x) ? 16 : 0;
          const score = cost.get(id) + Math.abs(p.x - current.x) + Math.abs(p.y - current.y) + bend;
          if (!cost.has(next) || score < cost.get(next)) { cost.set(next, score); previous.set(next, id); queue.push([next, score + Math.abs(p.x - b.x) + Math.abs(p.y - b.y)]); }
        }
      }
    }
    const points = [start, ...route, end].filter((point, index, array) => !index || point.x !== array[index - 1].x || point.y !== array[index - 1].y);
    const simplified = points.filter((point, index) => !index || index === points.length - 1 || !((points[index - 1].x === point.x && point.x === points[index + 1].x) || (points[index - 1].y === point.y && point.y === points[index + 1].y)));
    let longest = 0, label = { x: middle, y: (a.y + b.y) / 2 };
    simplified.slice(1).forEach((point, index) => { const before = simplified[index], length = Math.abs(point.x - before.x) + Math.abs(point.y - before.y); if (length > longest) { longest = length; label = { x: (point.x + before.x) / 2, y: (point.y + before.y) / 2 }; } });
    return { points: simplified, label, path: simplified.map((point, index) => `${index ? "L" : "M"}${point.x},${point.y}`).join(" ") };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { layoutSchema, projectGraph, routeEdge, bounds, compactFields };
  if (typeof document === "undefined") return;

  function initSchemas() {
    document.querySelectorAll("[data-schema-workspace]:not([data-schema-ready])").forEach((root) => {
      root.dataset.schemaReady = "true";
      const graph = JSON.parse(root.dataset.graph), messages = JSON.parse(root.dataset.messages);
      const fieldWord = (count) => { const forms = messages.fieldForms || ["field", "fields", "fields"]; return messages.language === "ru" ? forms[count % 100 >= 11 && count % 100 <= 14 ? 2 : count % 10 === 1 ? 0 : count % 10 >= 2 && count % 10 <= 4 ? 1 : 2] : forms[count === 1 ? 0 : 1]; };
      const svg = root.querySelector("[data-schema-canvas]"), choices = root.querySelector("[data-schema-choices]");
      const catalog = new Map([...graph.nodes, ...(graph.junctions || [])].map((node) => [node.id, node]));
      const known = new Map(graph.nodes.map((node) => [node.id, node]));
      const visible = new Set(known.keys()), expanded = new Set(), opened = new Set(), manual = new Map();
      let laidOut = [], selected = null, view = { x: 0, y: 0, width: 600, height: 360 }, zoom = 1, autoFit = true, drag = null, frame = null, suppressClick = false;
      const ns = "http://www.w3.org/2000/svg";
      const el = (tag, attributes = {}, text) => { const node = document.createElementNS(ns, tag); for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value); if (text != null) node.textContent = text; return node; };
      const dimensions = () => { const box = svg.getBoundingClientRect(); return { width: Math.max(1, box.width), height: Math.max(1, box.height) }; };
      function updateView() { svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`); root.querySelector("[data-schema-zoom-label]").textContent = Math.round(zoom * 100) + "%"; }
      function fit(items = laidOut) { const box = bounds(items), size = dimensions(); zoom = Math.min(1, size.width / box.width, size.height / box.height); view = { x: box.x + box.width / 2 - size.width / zoom / 2, y: box.y + box.height / 2 - size.height / zoom / 2, width: size.width / zoom, height: size.height / zoom }; updateView(); }
      function changeZoom(factor, client) { autoFit = false; const size = dimensions(), old = zoom; zoom = Math.max(.1, Math.min(2.5, zoom * factor)); const ratio = zoom / old, fx = client ? client.x / size.width : .5, fy = client ? client.y / size.height : .5; view.x += view.width * fx * (1 - 1 / ratio); view.y += view.height * fy * (1 - 1 / ratio); view.width = size.width / zoom; view.height = size.height / zoom; updateView(); }
      function highlight(id) {
        svg.querySelectorAll("[data-node]").forEach((node) => node.classList.toggle("is-selected", node.dataset.node === id));
        svg.querySelectorAll("[data-edge]").forEach((node) => { const incident = node.dataset.source === id || node.dataset.target === id; node.classList.toggle("is-highlighted", !!id && incident); node.classList.toggle("is-dimmed", !!id && !incident); });
      }
      function select(id, center = false) {
        selected = id;
        const node = catalog.get(id), link = root.querySelector("[data-schema-open]");
        link.hidden = !node?.url; if (node?.url) link.href = node.url;
        highlight(id);
        if (center) {
          const found = laidOut.find((node) => node.id === id);
          if (found) {
            autoFit = false; const size = dimensions(); zoom = Math.min(1, size.width / (found.width + 48));
            view = { x: found.x + found.width / 2 - size.width / zoom / 2,
              y: (found.height + 64) * zoom > size.height ? found.y - 32 : found.y + found.height / 2 - size.height / zoom / 2,
              width: size.width / zoom, height: size.height / zoom }; updateView();
          }
        }
      }
      function renderChoices() {
        const search = root.querySelector("[data-schema-search]").value.toLocaleLowerCase();
        choices.replaceChildren(); let count = 0;
        for (const node of known.values()) {
          if (!(node.label + " " + node.name).toLocaleLowerCase().includes(search)) continue;
          const row = document.createElement("div"); row.className = "schema-table-choice";
          const check = document.createElement("input"); check.type = "checkbox"; check.checked = visible.has(node.id); check.setAttribute("aria-label", (messages.showTable || messages.tables) + ": " + node.label); check.dataset.table = node.id;
          check.addEventListener("change", () => { if (check.checked) visible.add(node.id); else visible.delete(node.id); if (!visible.has(selected)) select(null); autoFit = true; draw(); updateCount(); });
          const name = document.createElement("button"); name.type = "button"; name.className = "link-button schema-table-name"; name.textContent = node.label; const small = document.createElement("small"); small.textContent = node.name; name.append(small);
          name.addEventListener("click", () => { if (!visible.has(node.id)) { visible.add(node.id); check.checked = true; draw(); updateCount(); } select(node.id, true); });
          row.append(check, name); choices.append(row); count++;
        }
        if (!count) { const empty = document.createElement("p"); empty.className = "field-help"; empty.textContent = messages.noTables; choices.append(empty); }
        updateCount();
      }
      function updateCount() { root.querySelector("[data-schema-count]").textContent = `${[...known.keys()].filter((id) => visible.has(id)).length}/${known.size}`; }
      function toggleJunction(id) {
        const edge = graph.edges.find((edge) => edge.id === id); if (!edge?.junction) return;
        if (opened.has(id) && visible.has(edge.junction)) {
          opened.delete(id);
          if (catalog.get(edge.junction).junction && !graph.edges.some((item) => item.junction === edge.junction && opened.has(item.id))) visible.delete(edge.junction);
        } else { opened.add(id); visible.add(edge.junction); known.set(edge.junction, catalog.get(edge.junction)); }
        autoFit = false; renderChoices(); draw(); select(visible.has(edge.junction) ? edge.junction : edge.source);
        fit(laidOut.filter((node) => [edge.source, edge.target, edge.junction].includes(node.id)));
      }
      function fixPositions() { laidOut.forEach((node) => manual.set(node.id, { x: node.x, y: node.y })); }
      function toggleNode(id) {
        const node = catalog.get(id);
        if (compactFields(node).length < node.fields.length) { if (expanded.has(id)) expanded.delete(id); else expanded.add(id); autoFit = false; draw(); }
        select(id, true);
        svg.querySelectorAll("[data-node]").forEach((group) => { if (group.dataset.node === id) group.focus(); });
      }
      function draw() {
        const focused = svg.contains(document.activeElement) ? { ...document.activeElement.dataset } : null;
        const projected = projectGraph(graph, visible, opened), size = dimensions();
        laidOut = layoutSchema(projected.nodes, projected.edges, expanded, size.width / size.height).map((node) => ({ ...node, ...manual.get(node.id) }));
        const positions = new Map(laidOut.map((node) => [node.id, node]));
        svg.replaceChildren();
        const defs = el("defs");
        for (const kind of ["one", "many"]) { const marker = el("marker", { id: "schema-" + kind, viewBox: "-12 -7 14 14", markerWidth: 14, markerHeight: 14, refX: 0, refY: 0, markerUnits: "userSpaceOnUse", orient: "auto-start-reverse" }); marker.append(el("path", { class: "schema-marker", d: kind === "one" ? "M-5,-6 V6" : "M-10,-6 L0,0 L-10,6 M-10,0 H0" })); defs.append(marker); }
        svg.append(defs);
        const edgeLayer = el("g"), nodeLayer = el("g");
        const pairs = new Map();
        for (const edge of projected.edges) {
          const source = positions.get(edge.source), target = positions.get(edge.target); if (!source || !target) continue;
          const pair = [source.id, target.id].sort().join("|"); const lane = pairs.get(pair) || 0; pairs.set(pair, lane + 1);
          const route = routeEdge(source, target, edge, laidOut, lane);
          const action = edge.originals[0] || (edge.junction ? edge.id : null), collapse = edge.originals.length > 0;
          const multiplicity = edge.kind === "o2o" ? "1:1" : edge.kind === "o2m" ? "1:N" : "N:M";
          const caption = `${multiplicity} · ${edge.kind}${action ? collapse ? " −" : " +" : ""}`;
          const accessible = `${source.name} (${edge.sourceFields.join(", ")}) → ${target.name} (${edge.targetFields.join(", ")}): ${multiplicity}, ${messages[edge.kind]}. ${action ? messages[collapse ? "collapseJunction" : "expandJunction"] : edge.label}`;
          const group = el("g", { class: "schema-edge" + (action ? " is-expandable" : ""), "data-edge": edge.id, "data-source": edge.source, "data-target": edge.target, tabindex: 0, role: action ? "button" : "img", "aria-label": accessible });
          if (action) { group.setAttribute("aria-expanded", String(collapse)); group.dataset.junctionAction = action; }
          group.append(el("title", {}, accessible), el("path", { class: "edge-line", d: route.path, "marker-start": `url(#schema-${edge.kind === "m2m" ? "many" : "one"})`, "marker-end": `url(#schema-${edge.kind === "o2o" ? "one" : "many"})` }), el("path", { class: "edge-hit", d: route.path }));
          const width = caption.length * 6 + 12;
          group.append(el("rect", { class: "edge-label-bg", x: route.label.x - width / 2, y: route.label.y - 10, width, height: 20, rx: 4 }), el("text", { x: route.label.x, y: route.label.y + 3.5 }, caption));
          if (action) { group.addEventListener("click", () => toggleJunction(action)); group.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); toggleJunction(action); } }); }
          group.addEventListener("pointerenter", () => highlight(selected || edge.source)); group.addEventListener("pointerleave", () => highlight(selected));
          edgeLayer.append(group);
        }
        for (const node of laidOut) {
          const additional = node.fields.length - compactFields(node).length, full = expanded.has(node.id) || !additional;
          const group = el("g", { class: "schema-node" + (node.junction ? " is-junction" : ""), transform: `translate(${node.x},${node.y})`, "data-node": node.id, tabindex: 0, role: "button", "aria-expanded": String(full), "aria-label": `${node.label} · ${node.name} · ${node.fields.length} ${fieldWord(node.fields.length)}${additional ? ". " + messages[full ? "collapse" : "expand"] : ""}. ${node.shownFields.map((field) => field.name + ": " + field.type).join(", ")}` });
          group.append(el("title", {}, node.name + " · " + node.fields.length + " " + fieldWord(node.fields.length)), el("rect", { class: "node-surface", width: node.width, height: node.height, rx: 7 }), el("path", { class: "node-header", d: `M7,1 H${node.width-7} Q${node.width-1},1 ${node.width-1},7 V${HEADER} H1 V7 Q1,1 7,1` }), el("line", { class: "node-divider", x1: 0, x2: node.width, y1: HEADER, y2: HEADER }));
          const shorten = (text, max) => text.length > max ? text.slice(0, max - 1) + "…" : text;
          group.append(el("text", { class: "node-title", x: 14, y: 23 }, shorten(node.name, Math.floor((node.width - 28) / 8))), el("text", { class: "node-subtitle", x: 14, y: 43 }, shorten(node.label, Math.floor((node.width - 28) / 6))));
          node.shownFields.forEach((field, index) => { const y = HEADER + index * ROW + 18; group.append(el("text", { class: "key-label", x: 12, y }, [field.pk ? "PK" : "", field.fk ? "FK" : ""].filter(Boolean).join("/")), el("text", { class: "field-name", x: 51, y }, shorten(field.name, Math.floor((node.width - 140) / 7))), el("text", { class: "field-type", x: node.width - 12, y, "text-anchor": "end" }, field.type)); });
          if (!node.shownFields.length) group.append(el("text", { class: "field-type", x: 14, y: HEADER + 18 }, node.fields.length ? messages.expand : messages.empty));
          group.append(el("line", { class: "node-divider", x1: 0, x2: node.width, y1: node.height - FOOTER, y2: node.height - FOOTER }), el("text", { class: "node-toggle", x: 14, y: node.height - 11 }, additional ? full ? messages.collapse + " ↑" : `+ ${additional} ${fieldWord(additional)}` : `${node.fields.length} ${fieldWord(node.fields.length)}`));
          group.addEventListener("click", () => { if (!suppressClick) toggleNode(node.id); });
          group.addEventListener("focus", () => select(node.id)); group.addEventListener("pointerenter", () => highlight(selected || node.id)); group.addEventListener("pointerleave", () => highlight(selected));
          group.addEventListener("keydown", (event) => {
            if (["Enter", " "].includes(event.key)) { event.preventDefault(); toggleNode(node.id); }
            const delta = { ArrowLeft: [-1,0], ArrowRight:[1,0], ArrowUp:[0,-1], ArrowDown:[0,1] }[event.key];
            if (delta) { event.preventDefault(); const step = event.shiftKey ? 40 : 10; fixPositions(); manual.set(node.id, { x: node.x + delta[0] * step, y: node.y + delta[1] * step }); autoFit = false; draw(); svg.querySelectorAll("[data-node]").forEach((g) => { if (g.dataset.node === node.id) g.focus(); }); }
          });
          nodeLayer.append(group);
        }
        svg.append(edgeLayer, nodeLayer);
        if (!laidOut.length) svg.append(el("text", { class: "schema-empty", x: 300, y: 180 }, messages.selectTables));
        if (autoFit) fit(); else updateView(); highlight(selected);
        if (focused) {
          const replacement = [...svg.querySelectorAll("[data-node], [data-edge]")].find((node) =>
            focused.node ? node.dataset.node === focused.node : focused.junctionAction ? node.dataset.junctionAction === focused.junctionAction : node.dataset.edge === focused.edge);
          (replacement || svg).focus();
        }
      }
      const world = (event) => { const box = svg.getBoundingClientRect(); return { x: view.x + (event.clientX - box.left) / box.width * view.width, y: view.y + (event.clientY - box.top) / box.height * view.height }; };
      svg.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || event.target.closest("[data-edge]")) return;
        const id = event.target.closest("[data-node]")?.dataset.node, point = world(event), node = laidOut.find((node) => node.id === id);
        drag = { pointer: event.pointerId, id, start: point, view: { ...view }, node, clientX: event.clientX, clientY: event.clientY, moved: false };
        if (id) select(id); svg.setPointerCapture(event.pointerId); event.preventDefault();
      });
      svg.addEventListener("pointermove", (event) => {
        if (!drag || event.pointerId !== drag.pointer) return;
        if (Math.hypot(event.clientX - drag.clientX, event.clientY - drag.clientY) > 3) drag.moved = true;
        if (!drag.moved) return;
        autoFit = false; svg.classList.add("is-dragging");
        const dx = (event.clientX - drag.clientX) / zoom, dy = (event.clientY - drag.clientY) / zoom;
        if (drag.id) { if (!drag.fixed) { fixPositions(); drag.fixed = true; } manual.set(drag.id, { x: drag.node.x + dx, y: drag.node.y + dy }); if (!frame) frame = requestAnimationFrame(() => { frame = null; draw(); }); }
        else { view.x = drag.view.x - dx; view.y = drag.view.y - dy; updateView(); }
      });
      function endDrag(event) {
        if (!drag || event.pointerId !== drag.pointer) return;
        const ended = drag; drag = null; svg.classList.remove("is-dragging");
        suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
        if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
        if (event.type !== "pointercancel" && !ended.moved) { if (ended.id) toggleNode(ended.id); else select(null); }
      }
      svg.addEventListener("pointerup", endDrag); svg.addEventListener("pointercancel", endDrag);
      svg.addEventListener("wheel", (event) => { event.preventDefault(); autoFit = false; if (event.ctrlKey || event.metaKey) { const box = svg.getBoundingClientRect(); changeZoom(Math.exp(-event.deltaY * .008), { x: event.clientX - box.left, y: event.clientY - box.top }); } else { view.x += event.deltaX / zoom; view.y += event.deltaY / zoom; updateView(); } }, { passive: false });
      svg.addEventListener("keydown", (event) => { if (event.target !== svg) return; if (["+", "=", "-", "0"].includes(event.key)) { event.preventDefault(); if (event.key === "0") { autoFit = true; fit(); } else changeZoom(event.key === "-" ? 1/1.2 : 1.2); } });
      root.querySelectorAll("[data-schema-zoom]").forEach((button) => button.addEventListener("click", () => changeZoom(button.dataset.schemaZoom === "in" ? 1.2 : 1/1.2)));
      root.querySelector("[data-schema-fit]").addEventListener("click", () => { autoFit = true; fit(); });
      root.querySelector("[data-schema-layout]").addEventListener("click", () => { manual.clear(); autoFit = true; draw(); });
      root.querySelector("[data-schema-search]").addEventListener("input", renderChoices);
      root.querySelector("[data-schema-show-all]").addEventListener("click", () => { known.forEach((node) => visible.add(node.id)); autoFit = true; renderChoices(); draw(); });
      root.querySelector("[data-schema-hide-all]").addEventListener("click", () => { visible.clear(); select(null); autoFit = true; renderChoices(); draw(); });
      root.querySelector("[data-schema-sidebar-toggle]").addEventListener("click", (event) => { const hidden = root.classList.toggle("is-sidebar-hidden"); event.currentTarget.setAttribute("aria-expanded", String(!hidden)); autoFit = true; requestAnimationFrame(fit); });
      const expandView = root.querySelector("[data-schema-expand-view]");
      const previousRole = root.getAttribute("role"), previousModal = root.getAttribute("aria-modal");
      let background = [];
      function restoreBackground() {
        background.forEach(([node, wasInert]) => { node.inert = wasInert; }); background = [];
        for (const [attribute, value] of [["role", previousRole], ["aria-modal", previousModal]]) {
          if (value == null) root.removeAttribute(attribute); else root.setAttribute(attribute, value);
        }
      }
      function toggleView(active = !root.classList.contains("is-expanded")) {
        root.classList.toggle("is-expanded", active);
        if (active) {
          for (let branch = root; branch.parentElement && branch !== document.body; branch = branch.parentElement) {
            for (const sibling of branch.parentElement.children) if (sibling !== branch) { background.push([sibling, sibling.inert]); sibling.inert = true; }
          }
          root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true");
        } else restoreBackground();
        expandView.setAttribute("aria-pressed", String(active)); expandView.textContent = messages[active ? "exitView" : "expandView"];
        autoFit = true; requestAnimationFrame(draw);
      }
      expandView.addEventListener("click", () => toggleView());
      root.querySelector("[data-schema-open]").addEventListener("click", () => { if (root.classList.contains("is-expanded")) toggleView(false); });
      root.addEventListener("keydown", (event) => {
        if (!root.classList.contains("is-expanded")) return;
        if (event.key === "Escape") { event.preventDefault(); toggleView(false); expandView.focus(); }
        if (event.key === "Tab") {
          const focusable = [...root.querySelectorAll('button, a[href], input, [tabindex="0"]')].filter((node) => !node.disabled && node.getClientRects().length);
          const first = focusable[0], last = focusable.at(-1);
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      });
      if (root.getBoundingClientRect().width < 700) { root.classList.add("is-sidebar-hidden"); root.querySelector("[data-schema-sidebar-toggle]").setAttribute("aria-expanded", "false"); }
      let lastWidth = 0, lastHeight = 0;
      const resize = new ResizeObserver(() => { if (!root.isConnected) { root.schemaCleanup(); return; } const size = dimensions(); if (size.width === lastWidth && size.height === lastHeight) return; lastWidth = size.width; lastHeight = size.height; if (autoFit) draw(); else { view.width = size.width / zoom; view.height = size.height / zoom; updateView(); } });
      root.schemaCleanup = () => { restoreBackground(); resize.disconnect(); if (frame) cancelAnimationFrame(frame); };
      resize.observe(svg); renderChoices(); draw();
    });
  }
  window.QuiteAdmin = { ...window.QuiteAdmin, initSchemas };
  initSchemas();
})();
