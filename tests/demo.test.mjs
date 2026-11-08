import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { Store } from "../demo/store.mjs";

const seed = JSON.parse(
  await readFile(new URL("../build/docs/demo/seed.json", import.meta.url)),
);

test("demo listings use the shared localized table pin controls", () => {
  const slugs = Object.keys(seed.collections).sort();
  for (const language of ["en", "ru"]) {
    assert.deepEqual(Object.keys(seed.tablePins[language]).sort(), slugs);
    for (const slug of slugs) {
      const control = seed.tablePins[language][slug];
      assert.ok(control.includes(`data-table-pin="${slug}"`));
      assert.match(control, /<button[^>]* hidden>/);
      assert.match(control, /aria-pressed="false"/);
      assert.match(control, /data-table-pin-icon/);
      assert.match(control, /data-table-pin-notice/);
      assert.ok(control.includes(language === "ru" ? "Закрепить таблицу:" : "Pin table:"));
    }
  }
});

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


test("text fragments, repeated conditions, membership and NULL work in the demo", () => {
  const store = new Store(seed);
  store.save("notes", null, {title:"Second note",body:null,pinned:"false"}, {});
  const collection = store.collection("notes");
  collection.records[0].values.title = "Alex Smith%_!";
  collection.records[0].values.body = "";
  collection.records[1].values.title = "alex Brown";
  collection.records[1].values.body = null;
  const partial = store.filter("notes", new URLSearchParams({"f.title.icontains":"ALEX"}));
  assert.equal(partial.length, 2);
  const repeated = store.filter("notes", new URLSearchParams({"f.title.icontains":"Alex", "f.title.icontains~1":"Smith"}));
  assert.equal(repeated.length, 1);
  assert.equal(store.filter("notes", new URLSearchParams({"f.title.iendswith":"%_!"})).length, 1);
  assert.equal(store.filter("notes", new URLSearchParams({"f.body.is_empty":"true"})).length, 1);
  assert.equal(store.filter("notes", new URLSearchParams({"f.body.is_empty":"false"})).some(row=>row.values.body==null), false);
  assert.equal(store.filter("notes", new URLSearchParams({"f.title.in":JSON.stringify(["alex Brown"])})).length, 1);
});

test("new showcase metadata survives restoring an older demo without losing records", () => {
  const old = structuredClone(seed.collections);
  delete old.schedules;
  old.products.fields = [];
  old.products.records[0].values.price = "21.75";
  const store = new Store(seed, old);
  assert.equal(store.collection("products").records[0].values.price, "21.75");
  assert.ok(store.collection("products").fields.length);
  assert.equal(store.collection("schedules").records.length, 6);
  assert.ok(store.collection("schedules").fields.find(field=>field.name==='description').multiline);
  assert.equal(store.collection("schedules").fields.find(field=>field.name==='reminder_at').kind, 'time');
  assert.equal(store.collection("orders").pagination, 'cursor');
});

test("saved changes and history restore together, with NULL, false and absent distinguished", () => {
  const store = new Store(seed), row = store.collection('schedules').records[0];
  store.save('schedules',row.key,{approved:'false',title:'<changed>'},{},store.revision('schedules',row.key),'inline_edit');
  const event = store.activity[0], approved = event.changes.find(change=>change.name==='approved');
  assert.equal(event.action, 'inline_edit');
  assert.equal(approved.before, null);
  assert.equal(approved.after, 'false');
  assert.equal(approved.before_present, true);
  const restored = new Store(seed, JSON.parse(JSON.stringify(store.snapshot())));
  assert.deepEqual(restored.activity, store.activity);
  assert.equal(restored.record('schedules',row.key).values.title, '<changed>');
  restored.delete('schedules',row.key);
  assert.equal(restored.activity[0].action, 'delete');
  assert.ok(restored.activity[0].changes.every(change=>!change.after_present));
});

test("failed writes do not emit successful field comparisons and history remains bounded", () => {
  const store = new Store(seed), row = store.collection('customers').records[0];
  const before = structuredClone(store.activity);
  assert.throws(()=>store.save('customers',row.key,{name:'unsaved'},{orders:[]}), /cannot be detached/);
  assert.deepEqual(store.activity,before);
  for(let i=0;i<210;i++)store.log('products','list');
  assert.equal(store.activity.length,200);
  assert.ok(store.activity.every(event=>event.changes.length===0));
});

test("explicit false defaults are exported and applied on creation", () => {
  const store = new Store(seed);
  const key = store.save('notes',null,{title:'Default note',body:null},{});
  assert.equal(store.record('notes',key).values.pinned,'false');
});
