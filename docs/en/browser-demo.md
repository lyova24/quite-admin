# Browser demo

[Open the demo](https://lyova24.github.io/quite-admin/demo/), then use `admin` / `admin`.
The documentation site workflow builds and deploys it at `/demo/`.

Try a table row, change a scalar field and a relationship, and save the same record page.
Customers/profiles demonstrate 1:1, customers/orders 1:N, and products/tags M:N. Search,
sorting, typed list filters, searchable relationship pickers, pagination, creation,
delete confirmation, EN/RU switching, an interactive [database schema](database-schema.md)
and a custom report are available. Changes stay in local browser storage when enabled. Reset restores the
fictional seed; each visitor has their own copy.

This is a standalone JavaScript demonstration of the interface. Its schemas and seed
data are exported from the actual example application's adapter; its CSS is copied
from the Python package. The browser implements a small transactional store for this
fixed demo schema. It does not run FastAPI, Litestar, an ORM or an authentication server,
and is not evidence of server-side authorization/database compatibility. Production
authentication and CSP remain in the Python ASGI app. No real session cookies, passwords,
production secrets or application records are exported.

For the real ASGI application, use the [local example](quickstart.md#run-the-sample-application).
The checked-in static demo is generated without connecting to a host application's DB.
Its builder always creates a disposable SQLite database and random temporary credentials.

## Try the new screens

1. Open **Products**, then **+ Add filter** → **Price**. Choose **Between**, enter
   two bounds and apply. Click the resulting chip to edit the range, or × to remove it.
2. Open a product, choose related tags, search and save. Selected chips persist across
   lookup pages. Two copies of an edit form can demonstrate a stale-edit conflict.
3. Open **Database schema**. Use the sidebar to hide/show tables, expand a table's
   fields and click **N:M** to reveal `product_tags`. Moving any table fixes all visible
   positions until **Auto layout**.
4. Switch to Russian to check the same controls and messages in both languages.

## Build locally

```bash
uv sync --locked
npm ci
npm run docs:build
npm run demo:test
npm run docs:serve
```

Open [localhost:8001/demo/](http://localhost:8001/demo/). The output includes `index.html`,
scripts, JSON data and CSS under `build/docs/demo`. Hash navigation works under a
repository URL prefix and needs no server-side route fallback. Node contract tests cover
both sides of relations, required-link rollback, 1:1 reassignment, creation/deletion,
stale edits, filter conditions, layout and M:N expansion.
The whole output is included in the site's existing deployment artifact.
