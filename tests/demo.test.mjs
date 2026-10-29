import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { Store } from "../demo/store.mjs";

const seed = JSON.parse(
  await readFile(new URL("../build/docs/demo/seed.json", import.meta.url)),
);

test("many-to-many changes update both sides", () => {
  const store = new Store(seed),
    product = store.collection("products").records[0];
  const tag = store.collection("tags").records.at(-1);
  store.save("products", product.key, {}, { tags: [tag.key] });
  assert.deepEqual(store.record("products", product.key).links.tags, [tag.key]);
  assert.ok(store.record("tags", tag.key).links.products.includes(product.key));
  for (const other of store
    .collection("tags")
    .records.filter((row) => row.key !== tag.key)) {
    assert.ok(!other.links.products.includes(product.key));
  }
});

test("required one-to-many detachment rolls back scalar changes", () => {
  const store = new Store(seed),
    customer = store.collection("customers").records[0];
  const before = structuredClone(store.state);
  assert.throws(
    () =>
      store.save(
        "customers",
        customer.key,
        { name: "must roll back" },
        { orders: [] },
      ),
    /cannot be detached/,
  );
  assert.deepEqual(store.state, before);
});

test("one-to-one replacement detaches the previous owner and synchronizes the FK", () => {
  const store = new Store(seed),
    [first, second] = store.collection("customers").records;
  const profile = second.links.profile[0];
  store.save("customers", first.key, {}, { profile: [profile] });
  assert.deepEqual(store.record("customers", second.key).links.profile, []);
  assert.equal(
    store.record("customer_profiles", profile).values.customer_id,
    first.values.id,
  );
});

test("many-to-one reassignment preserves required relations", () => {
  const store = new Store(seed),
    order = store.collection("orders").records[0];
  const target = store
    .collection("customers")
    .records.find((row) => row.key !== order.links.customer[0]);
  const old = order.links.customer[0];
  store.save("orders", order.key, {}, { customer: [target.key] });
  assert.equal(
    store.record("orders", order.key).values.customer_id,
    target.values.id,
  );
  assert.ok(!store.record("customers", old).links.orders.includes(order.key));
  assert.ok(
    store.record("customers", target.key).links.orders.includes(order.key),
  );
});

test("create, validation failure and deletion keep coherent local data", () => {
  const store = new Store(seed);
  const key = store.save(
    "notes",
    null,
    { title: "A new note", body: null, pinned: "false" },
    {},
  );
  assert.equal(store.record("notes", key).values.title, "A new note");
  const before = structuredClone(store.state);
  assert.throws(
    () => store.save("notes", key, { id: "99" }, {}),
    /not writable/,
  );
  assert.deepEqual(store.state, before);
  store.delete("notes", key);
  assert.throws(() => store.record("notes", key), /not found/);
});


test("stale record and relationship edits preserve the latest data", () => {
  const store = new Store(seed), row = store.collection("products").records[0];
  const revision = store.revision("products", row.key);
  store.save("products", row.key, { name: "New name" }, {}, revision);
  const before = structuredClone(store.state);
  assert.throws(() => store.save("products", row.key, { name: "Stale name" }, {}, revision), /record changed/);
  assert.deepEqual(store.state, before);
  const latest = store.revision("products", row.key);
  store.save("products", row.key, {}, { tags: [] }, latest);
  assert.throws(() => store.save("products", row.key, { name: "Stale relations" }, {}, latest), /record changed/);
});


test("list filters combine scalar ranges and related membership before paging", () => {
  const store = new Store(seed);
  const result = store.filter("products", new URLSearchParams({"f.active.eq":"true", "f.price.gte":"20", "f.price.lte":"30"}));
  assert.ok(result.length > 0);
  assert.ok(result.every((row) => row.values.active === "true" && Number(row.values.price) >= 20 && Number(row.values.price) <= 30));
  const first = store.collection("products").records.find((row) => row.links.tags?.length);
  assert.ok(store.filter("products", new URLSearchParams({"r.tags":first.links.tags[0]})).every((row) => row.links.tags.includes(first.links.tags[0])));
});


test("numeric equality, zero and strict comparisons filter the demo correctly", () => {
  const store = new Store(seed);
  const exact = store.filter("products", new URLSearchParams("f.price.eq=18.00"));
  assert.equal(exact.length, 1);
  assert.equal(exact[0].values.name, "Everyday notebook");
  const zero = store.filter("products", new URLSearchParams("f.stock.eq=0"));
  assert.equal(zero.length, 1);
  assert.equal(zero[0].values.name, "Brass bookmark");
  const rows = store.filter("products", new URLSearchParams("f.price.gt=18&f.price.lt=28"));
  assert.equal(rows.length, 2);
});
