// Browser-only fictional data. This module is not part of the Python library's backend.
export class Store {
  constructor(seed, restored = null) {
    this.state = structuredClone(restored || seed.collections);
  }
  collection(slug, state = this.state) {
    const collection = state[slug];
    if (!collection) throw new Error("Collection not found.");
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
    return (
      row.values.name ||
      row.values.title ||
      row.values.id ||
      this.collection(slug).label
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
                (row.values[name] = target?.values[fields[index].name] ?? null),
            );
          }
      }
  }
  setRelation(state, slug, row, relation, selected) {
    const multiple = ["one_to_many", "many_to_many"].includes(relation.kind);
    if (!multiple && selected.length > 1)
      throw new Error("Choose a single related record.");
    const previous = row.links[relation.name] || [];
    if (
      !relation.canDetach &&
      previous.some((key) => !selected.includes(key)) &&
      (multiple || !selected.length)
    ) {
      throw new Error("This relationship cannot be detached.");
    }
    if (
      !multiple &&
      relation.sourceFields.length &&
      !relation.canDetach &&
      !selected.length
    ) {
      throw new Error("A related record is required.");
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
            if (!field.nullable && !field.generated)
              throw new Error("A value is required.");
            continue;
          }
          if (field.maxLength && value.length > field.maxLength)
            throw new Error("Value is too long.");
          if (
            field.kind === "integer" &&
            (!/^-?\d+$/.test(value) ||
              BigInt(value) < -(2n ** 63n) ||
              BigInt(value) > 2n ** 63n - 1n)
          )
            throw new Error("Enter a valid integer.");
          if (
            field.kind === "number" &&
            (!value.trim() || !Number.isFinite(Number(value)))
          )
            throw new Error("Enter a finite number.");
          if (field.kind === "boolean" && !["true", "false"].includes(value))
            throw new Error("Choose true or false.");
          if (field.kind === "json") JSON.parse(value);
          if (field.choices.length && !field.choices.includes(value))
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
  }
  filter(slug, params) {
    const collection = this.collection(slug);
    return collection.records.filter((row) => [...params].every(([name, raw]) => {
      if (!raw) return true;
      if (name.startsWith("r.")) return (row.links[name.slice(2)] || []).includes(raw);
      if (!name.startsWith("f.")) return true;
      const match = /^f\.(.+)\.(eq|gte|lte|is_null)$/.exec(name);
      if (!match) return false;
      const field = collection.fields.find((item) => item.name === match[1]);
      if (!field) return false;
      const value = row.values[field.name], operator = match[2];
      if (operator === "is_null") return (value == null) === (raw === "true");
      if (value == null) return false;
      const numeric = ["integer", "number"].includes(field.kind);
      const a = numeric ? Number(value) : String(value), b = numeric ? Number(raw) : raw;
      return operator === "gte" ? a >= b : operator === "lte" ? a <= b : a === b;
    }));
  }

  revision(slug, key) {
    const row = this.record(slug, key);
    return JSON.stringify({ values: row.values, links: Object.fromEntries(Object.entries(row.links).sort().map(([name, keys]) => [name, [...keys].sort()])) });
  }
  save(slug, key, values, selections, expectedRevision = null) {
    if (key != null && expectedRevision != null && this.revision(slug, key) !== expectedRevision)
      throw new Error("This record changed after you opened it. Your changes have not been saved. Reload the record and review the latest values.");
    const state = structuredClone(this.state);
    const collection = this.collection(slug, state);
    const creating = key == null;
    const managed = collection.relations.flatMap(
      (relation) => relation.sourceFields,
    );
    const writable = collection.writable[creating ? "create" : "edit"].filter(
      (name) => !managed.includes(name),
    );
    if (Object.keys(values).some((name) => !writable.includes(name)))
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
            : field.hasDefault
              ? ({
                  integer: "0",
                  number: "0",
                  boolean: "true",
                  json: "{}",
                  datetime: new Date().toISOString(),
                }[field.kind] ?? "pending")
              : null;
      }
      row.key = btoa(
        JSON.stringify(
          collection.fields
            .filter((field) => field.primaryKey)
            .map((field) => row.values[field.name]),
        ),
      )
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replaceAll("=", "");
      collection.records.push(row);
    }
    Object.assign(row.values, values);
    for (const [name, selected] of Object.entries(selections)) {
      const relation = collection.relations.find((item) => item.name === name);
      if (!relation) throw new Error("Unknown relationship.");
      this.setRelation(state, slug, row, relation, selected);
    }
    this.syncForeignKeys(state);
    this.validate(state);
    this.state = state;
    return row.key;
  }
  delete(slug, key) {
    const state = structuredClone(this.state);
    const collection = this.collection(slug, state);
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
  }
}
