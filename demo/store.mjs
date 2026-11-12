// Browser-only fictional data. This module is not part of the Python library's backend.
import { changesFor, initialActivity } from "./activity.mjs";

export function recordKey(collection, values) {
  const keys = collection.fields.filter(field => field.primaryKey).map(field => values[field.name]);
  if (!keys.length || keys.some(value => value == null || value === ""))
    throw new Error("A complete, non-null primary key is required.");
  const bytes = new TextEncoder().encode(JSON.stringify(keys.map(String)));
  return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(""))
    .replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function fieldDefault(field) {
  if (field.default != null) return field.default;
  if (!field.hasDefault) return null;
  if (field.kind === "uuid") return globalThis.crypto.randomUUID();
  if (field.kind === "datetime") return new Date().toISOString();
  return {integer: "0", number: "0", boolean: "true", json: "{}"}[field.kind]
    ?? field.choices?.[0] ?? null;
}

export class Store {
  constructor(seed, restored = null) {
    // Refresh exported metadata and add new showcase collections without losing local edits.
    const previous = restored?.collections || restored;
    this.state = Object.fromEntries(Object.entries(seed.collections).map(([slug, collection]) => {
      const copy = structuredClone(collection);
      if (previous?.[slug]?.records) copy.records = previous[slug].records.map(row => {
        const current = collection.records.find(item => item.key === row.key);
        return {key: row.key,
          values: Object.fromEntries(collection.fields.map(field => [field.name,
            Object.hasOwn(row.values, field.name) ? row.values[field.name]
              : current?.values[field.name] ?? fieldDefault(field)])),
          links: Object.fromEntries(collection.relations.map(relation => [relation.name,
            structuredClone(row.links?.[relation.name] ?? current?.links[relation.name] ?? [])]))};
      });
      return [slug, copy];
    }));
    this.activity = structuredClone(restored?.activity || initialActivity(seed));
  }
  snapshot() {
    return {collections: this.state, activity: this.activity};
  }
  log(collection, action, key = null, changes = [], outcome = "success", status_code = 200) {
    this.activity.unshift({id: Math.max(0, ...this.activity.map(event => event.id)) + 1,
      occurred_at: new Date().toISOString(), subject: "admin", display_name: "Demo Admin",
      collection, action, key, changes, outcome, status_code});
    this.activity = this.activity.slice(0, 200);
  }
  collection(slug, state = this.state) {
    const collection = state[slug];
    if (!collection) throw new Error("Table not found.");
    return collection;
  }
  record(slug, key, state = this.state) {
    const record = this.collection(slug, state).records.find(
      (row) => row.key === key,
    );
    if (!record) throw new Error("Record not found.");
    return record;
  }
  label(slug, row) {
    const collection = this.collection(slug);
    return (
      (collection.recordLabel && row.values[collection.recordLabel]) ||
      row.values.name ||
      row.values.title ||
      row.values.label ||
      row.values.display_name ||
      row.values.username ||
      row.values.id ||
      collection.fields.filter(field => field.primaryKey).map(field => row.values[field.name]).join(" · ") ||
      collection.label
    );
  }
  syncForeignKeys(state) {
    for (const collection of Object.values(state))
      for (const row of collection.records) {
        for (const relation of collection.relations)
          if (relation.sourceFields.length) {
            const key = row.links[relation.name]?.[0];
            const target = key
              ? this.record(relation.target, key, state)
              : null;
            const fields = this.collection(
              relation.target,
              state,
            ).fields.filter((field) => field.primaryKey);
            relation.sourceFields.forEach(
              (name, index) =>
                (row.values[name] = target?.values[relation.sourceReferences?.[name] ?? fields[index].name] ?? null),
            );
          }
      }
  }
  setRelation(state, slug, row, relation, selected) {
    const source = this.collection(slug, state);
    if (relation.readonly || source.readonlyRelations?.includes(relation.name))
      throw new Error("This relationship is read-only.");
    const multiple = ["one_to_many", "many_to_many"].includes(relation.kind);
    if (!multiple && selected.length > 1)
      throw new Error("Choose a single related record.");
    const previous = row.links[relation.name] || [];
    if (
      !multiple &&
      relation.sourceFields.length &&
      !relation.canDetach &&
      !selected.length
    ) {
      throw new Error("A related record is required.");
    }
    if (
      !relation.canDetach &&
      previous.some((key) => !selected.includes(key)) &&
      (multiple || !selected.length)
    ) {
      throw new Error("This relationship cannot be detached.");
    }
    selected.forEach((key) => this.record(relation.target, key, state));
    const target = this.collection(relation.target, state);
    const inverse = target.relations.find(
      (item) => item.name === relation.inverse,
    );
    if (inverse) {
      for (const key of previous) {
        const other = this.record(relation.target, key, state);
        other.links[inverse.name] = (other.links[inverse.name] || []).filter(
          (item) => item !== row.key,
        );
      }
      for (const key of selected) {
        const other = this.record(relation.target, key, state);
        const previousOwners = other.links[inverse.name] || [];
        if (!["one_to_many", "many_to_many"].includes(inverse.kind)) {
          for (const ownerKey of previousOwners) {
            const owner = this.record(slug, ownerKey, state);
            owner.links[relation.name] = (
              owner.links[relation.name] || []
            ).filter((item) => item !== key);
          }
          other.links[inverse.name] = [row.key];
        } else
          other.links[inverse.name] = [
            ...new Set([...previousOwners, row.key]),
          ];
      }
    }
    row.links[relation.name] = [...new Set(selected)];
  }
  validate(state) {
    for (const collection of Object.values(state))
      for (const row of collection.records) {
        for (const field of collection.fields) {
          const value = row.values[field.name];
          if (value == null) {
            if (!field.nullable && !field.generated && !field.readOnly)
              throw new Error("A value is required.");
            continue;
          }
          if (field.maxLength && value.length > field.maxLength)
            throw new Error("Value is too long.");
          if (
            field.kind === "integer" &&
            (!/^-?\d+$/.test(value) ||
              BigInt(value) < BigInt(field.minimum ?? -(2n ** 63n)) ||
              BigInt(value) > BigInt(field.maximum ?? 2n ** 63n - 1n))
          )
            throw new Error("Enter a valid integer.");
          if (
            field.kind === "number" &&
            (!value.trim() || !Number.isFinite(Number(value)))
          )
            throw new Error("Enter a finite number.");
          if (["integer", "number"].includes(field.kind) && (
            (field.minimum != null && Number(value) < Number(field.minimum)) ||
            (field.maximum != null && Number(value) > Number(field.maximum))))
            throw new Error("The value is outside the allowed range.");
          if (field.kind === "uuid" && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value))
            throw new Error("Enter a valid uuid.");
          if (field.kind === "boolean" && !["true", "false"].includes(value))
            throw new Error("Choose true or false.");
          if (field.kind === "json") { try { JSON.parse(value); } catch { throw new Error("Invalid JSON"); } }
          if (field.choices?.length && !field.choices.includes(value))
            throw new Error("Choose one of the available values.");
        }
        for (const field of collection.unique)
          if (
            row.values[field] != null &&
            collection.records.some(
              (other) =>
                other.key !== row.key &&
                other.values[field] === row.values[field],
            )
          ) {
            throw new Error(
              "The operation conflicts with a database constraint.",
            );
          }
      }
    for (const collection of Object.values(state)) {
      const keys = collection.records.map(row => row.key);
      if (new Set(keys).size !== keys.length)
        throw new Error("The operation conflicts with a database constraint.");
    }
  }
  filter(slug, params) {
    const collection = this.collection(slug);
    return collection.records.filter((row) => [...params].every(([name, raw]) => {
      if (!raw) return true;
      if (name.startsWith("r.")) return (row.links[name.slice(2)] || []).includes(raw);
      if (!name.startsWith("f.")) return true;
      const match = /^f\.(.+)\.(eq|ne|gt|gte|lt|lte|is_null|is_empty|in|on|icontains|not_icontains|istartswith|iendswith)(?:~[1-9][0-9]?)?$/.exec(name);
      if (!match) return false;
      const field = collection.fields.find((item) => item.name === match[1]);
      if (!field) return false;
      const value = row.values[field.name], operator = match[2];
      if (operator === "is_null") return (value == null) === (raw === "true");
      if (value == null) return false;
      if(operator==='is_empty') return (value==='')===(raw==='true');
      if(['icontains','not_icontains','istartswith','iendswith'].includes(operator)){
        const a=String(value).toLowerCase(),b=raw.toLowerCase();
        return operator==='icontains'?a.includes(b):operator==='not_icontains'?!a.includes(b):operator==='istartswith'?a.startsWith(b):a.endsWith(b);
      }
      if(operator==='in'){try {const values=JSON.parse(raw);return values.some(v=>['integer','number'].includes(field.kind)?Number(v)===Number(value):v===value);}catch(_){return false;}}
      if(operator==='on'){
        if(!/[Z+-]\d{2}:?\d{2}$/.test(raw)&&!raw.endsWith('Z'))return String(value).slice(0,10)===raw.slice(0,10);
        const start=Date.parse(raw),actual=Date.parse(value);return actual>=start&&actual<start+86400000;
      }
      const numeric = ["integer", "number"].includes(field.kind);
      const a = numeric ? Number(value) : String(value), b = numeric ? Number(raw) : raw;
      return operator === "ne" ? a !== b : operator === "gt" ? a > b : operator === "gte" ? a >= b : operator === "lt" ? a < b : operator === "lte" ? a <= b : a === b;
    }));
  }

  revision(slug, key) {
    const row = this.record(slug, key);
    return JSON.stringify({ values: row.values, links: Object.fromEntries(Object.entries(row.links).sort().map(([name, keys]) => [name, [...keys].sort()])) });
  }
  save(slug, key, values, selections, expectedRevision = null, action = null) {
    if (key != null && expectedRevision != null && this.revision(slug, key) !== expectedRevision)
      throw new Error("This record changed after you opened it. Your changes have not been saved. Reload the record and review the latest values.");
    const before = key == null ? null : structuredClone(this.record(slug, key));
    const state = structuredClone(this.state);
    const collection = this.collection(slug, state);
    const creating = key == null;
    if (collection.serverOnlyWrites || (creating ? collection.canCreate : collection.canEdit) === false)
      throw new Error("This operation is not permitted.");
    const managed = collection.relations.flatMap(
      (relation) => relation.sourceFields,
    );
    const writable = collection.writable[creating ? "create" : "edit"].filter(
      (name) => !managed.includes(name),
    );
    if (Object.keys(values).some((name) => !writable.includes(name)
      || (!creating && collection.fields.find(field => field.name === name)?.primaryKey)))
      throw new Error("This field is not writable.");
    const row = creating
      ? { values: {}, links: {} }
      : this.record(slug, key, state);
    if (creating) {
      for (const field of collection.fields) {
        row.values[field.name] =
          field.primaryKey && field.generated
            ? String(
                Math.max(
                  0,
                  ...collection.records.map((item) =>
                    Number(item.values[field.name]),
                  ),
                ) + 1,
              )
            : fieldDefault(field);
      }
    }
    Object.assign(row.values, values);
    for (const field of collection.fields) {
      if (field.kind === "uuid" && row.values[field.name] != null)
        row.values[field.name] = String(row.values[field.name]).toLowerCase();
      if (field.control === "ticket" && row.values[field.name] != null)
        row.values[field.name] = String(row.values[field.name]).trim().toUpperCase();
    }
    if (creating) {
      row.key = recordKey(collection, row.values);
      collection.records.push(row);
    }
    for (const [name, selected] of Object.entries(selections)) {
      const relation = collection.relations.find((item) => item.name === name);
      if (!relation) throw new Error("Unknown relationship.");
      this.setRelation(state, slug, row, relation, selected);
    }
    this.syncForeignKeys(state);
    this.validate(state);
    this.state = state;
    this.log(slug, action || (creating ? "create" : "edit"), row.key, changesFor(collection, before, row));
    return row.key;
  }
  delete(slug, key) {
    const state = structuredClone(this.state);
    const collection = this.collection(slug, state);
    if (collection.serverOnlyWrites || collection.canDelete === false)
      throw new Error("This operation is not permitted.");
    const row = this.record(slug, key, state);
    for (const relation of collection.relations) {
      const target = this.collection(relation.target, state);
      const inverse = target.relations.find(
        (item) => item.name === relation.inverse,
      );
      if (!inverse) continue;
      for (const targetKey of row.links[relation.name] || []) {
        const other = this.record(relation.target, targetKey, state);
        if (inverse.sourceFields.length && !inverse.canDetach)
          throw new Error("A related record is required.");
        other.links[inverse.name] = (other.links[inverse.name] || []).filter(
          (item) => item !== key,
        );
      }
    }
    collection.records = collection.records.filter((item) => item.key !== key);
    this.syncForeignKeys(state);
    this.validate(state);
    this.state = state;
    this.log(slug, "delete", key, changesFor(collection, row, null));
  }
}
