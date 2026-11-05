# Browser demo

[Open the demo](https://lyova24.github.io/quite-admin/demo/), then use `admin` / `admin`.
The documentation site workflow builds and deploys it at `/demo/`.
The overview's **Explore the interface** links take you directly to the new examples.
Follow the [interface tour](interface-tour.md) for screenshots and a complete walkthrough.

## What to try

| Screen | Working example |
| --- | --- |
| Products | Edit a price/stock cell, save or cancel the inline dialog; switch Active directly in the list |
| Schedules | DATE, DATETIME with microseconds, nullable TIME, three-state boolean, multiline TEXT and highlighted JSON |
| Activity history | Sample events for two fictional users plus your own local actions, before/after comparisons, Journal/Table, common filters and a UTC day/range picker |
| List filters | Text fragments, repeated conditions, numeric/date ranges, sets, SQL NULL, empty text and related records; edit active chips |
| Orders | Cursor-style Next/Previous navigation and column sorting, without an exact-total badge |
| Export data | Select scalar columns and download CSV for all matching records, including other pages |
| Customers / Customer Profiles / Orders | Searchable 1:1 and 1:N relationship editors with atomic local saves |
| Products / Tags | Searchable M:N editors; concurrent form changes produce a stale-edit conflict |
| Sidebar / Database schema | Collapsible remembered groups, table visibility, expanded fields, M:N junctions, drag and Auto layout |
| Store report | Custom page populated from the local demo data |

Switch **Language** to see the same controls in English and Russian. Changes and the
latest 200 local activity events stay in this browser's storage when enabled. **Reset demo**
restores the fictional records and sample events. Each visitor has their own copy.
Existing saved demos gain new collections and current field metadata without losing local records.

## Browser and server coverage

This is a standalone JavaScript demonstration. Schemas, fictional seed data, field policies
and period markup are exported from the actual example application's adapter/templates.
CSS and the date, form, JSON, boolean, inline-edit, filter, relationship and schema runtimes
come from the Python package. Only the fixed demo store and its request transport run in JavaScript.

| Available in the browser demo | Requires the real ASGI application |
| --- | --- |
| Local before/after history, user/date filters and both views | Durable SQLite/PostgreSQL/MySQL storage, `quiteadmin_` tables, automatic initialization, history permissions/redaction and `history_enabled` |
| Cursor-style navigation over fictional records | Database keyset queries without COUNT/OFFSET and signed, expiring cursors |
| Scalar CSV with column selection, current filters and sorting | XLSX, related export columns, batched relation queries and server export limits |
| Local validation, relation rollback and stale-edit checks | Authentication, CSRF, authorization, atomic database writes, hooks/actions and SQL read deadlines |

The browser does not run FastAPI, Litestar, an ORM or an authentication server. The
`admin` / `admin` login is an interface fixture. It is not evidence of server security,
durable auditing or database compatibility. No real session cookies, passwords,
production secrets or application records are exported.

For those features, run the [local ASGI example](quickstart.md#run-the-sample-application).
It includes the same Schedules fields, grouped sidebar and cursor-mode Orders, plus real
activity storage and CSV/XLSX exports. See [storage](storage.md), [configuration](configuration.md)
and [exports](exports.md) for setup and guarantees. Raw SQL editing and a dashboard builder
are not implemented features.

## Build locally

```bash
uv sync --locked
npm ci
npm run docs:build
npm run demo:test
npm run docs:serve
```

Open [localhost:8001/demo/](http://localhost:8001/demo/). The builder always creates a
disposable SQLite database and random temporary credentials; it never connects to the
host application's DB. Output lives in `build/docs/demo`; hash navigation works under a
repository URL prefix without server-side route fallback. Rebuild the demo after rebuilding
documentation, which replaces the output directory.

Node contract tests cover relations and rollback, stale saves, persisted activity and
inclusive dates, seed upgrades, cursor windows, CSV escaping, filters and schema layout.
The site's existing deployment artifact includes the complete output.
