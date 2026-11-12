# Browser demo

[Open the demo](https://lyova24.github.io/quite-admin/demo/), then use `admin` / `admin`.
The demo uses the ordinary admin Home, table lists and record forms. After sign-in,
an optional walkthrough invitation offers **Start tour** or **Not now**. Navigation and
highlighting begin only after you choose Start tour. Declining or closing the invitation
is remembered; choose **Start tour** in the profile menu to reopen it when wanted.
The walkthrough only visits real pages and explains controls; it does not save records.
Use **Back**, **Next**, **Skip tour** and **Finish** to control it. Closing or skipping
is remembered too. Progress continues across its own navigation and reloads in the
same tab; a new tab does not start it automatically.

For an English or Russian demo, open with `?lang=en` or `?lang=ru`. Otherwise it uses
the saved language or browser language.

For editable dates, choose **Table list → Schedules → Create record**, or find Schedules
with **Find a table**. The form contains **Date**, **Date and time** and optional **Time**.
Click the calendar icon next to Date or the date part of Date and time to open the
existing in-page calendar. Enter a title, fill the required values and choose
**Create record** to save your own fictional record.

The documentation site workflow builds and deploys the demo at `/demo/`.
Follow the [interface tour](interface-tour.md) for screenshots and a complete walkthrough.

## What to try

| Screen | Working example |
| --- | --- |
| Schedules | Open Create record to edit Date, Date and time or Time and use the calendar icon; existing records also demonstrate microseconds, nullable boolean, multiline TEXT and JSON |
| Products | Edit a price/stock cell, save or cancel the inline dialog; switch Active directly in the list |
| Field samples | Enum choices, UUID, numbers, URL/issue links, multiline and JSON previews, model defaults, read-only timestamps/binary values and an issue-key control with suggestions |
| Field sample actions | Open a sample and run Publish sample or Archive sample; inspect the changed status and local activity history |
| Folders | Search 36 candidates across pages; select a parent or children in a self-referencing 1:N tree, detach nullable links, and inspect read-only Samples |
| Customers / Customer Profiles / Orders | Searchable 1:1 and N:1 selectors; a customer's orders use multiple 1:N selection |
| Products / Tags | Searchable M:N editors; concurrent form changes produce a stale-edit conflict |
| Regional prices | Composite Region + SKU record keys, numeric validation and read-only key fields after creation |
| Price alerts | Select a Regional Price through one required relationship backed by Region + SKU; search by its complete JSON key |
| Reference rates | A view-only table without create, save or delete controls |
| Demo accounts | View fictional accounts; create/edit services and password handling require the Python example |
| Bulk actions | Select products, open Bulk actions, choose Deactivate products or Delete selected records, review confirmation and per-record results |
| Export data | Select scalar or related columns and download CSV for all matching records, including other pages |
| Activity history | Sample events for two fictional users plus your own local actions, before/after comparisons, Journal/Table, common filters and a UTC day/range picker |
| List filters | Text fragments, repeated conditions, numeric/date ranges, sets, SQL NULL, empty text and related records; edit active chips |
| Orders | Cursor-style Next/Previous navigation and column sorting, without an exact-total badge |
| Home / Navigation | Cards and grouped Table list views, pinned/recent tables, global table search and the fixed icon rail |
| Database schema | Table visibility, expanded fields, M:N junctions, drag and Auto layout |

Single relationships use radio buttons and multiple relationships use checkboxes.
Selected records remain visible outside the search results; search, pagination and
clearing/removing selections use the same picker as the Python application.
Changes are saved with **Save changes**, together with the record's scalar fields.

In Price alerts, **Regional Price** fills both foreign-key columns from one selection.
For an exact composite-key search, enter `{"region":"US","sku":"NOTE-001"}`.
Regional prices shows the reverse Alerts relationship; required alerts cannot be detached.

Changes and the latest 200 local activity events stay in this browser's storage when
enabled. Each visitor has their own copy. Within the same demo version, refreshed
tables and field metadata preserve local records. A new demo version starts with its
own browser copy of the fictional data.

## Browser and server coverage

This is a standalone JavaScript demonstration. Schemas, fictional seed data, field policies,
action metadata and period markup are exported from the actual example application's
adapter/templates. CSS and the date, form, JSON, boolean, value-display, inline-edit,
filter, relationship, bulk-selection and schema runtimes come from the Python package.
The fixed demo store and its request transport run in JavaScript.

| Available in the browser demo | Requires the real ASGI application |
| --- | --- |
| Local before/after history, user/date filters and both views, including local record/bulk actions | Durable SQLite/PostgreSQL/MySQL storage, `quiteadmin_` tables, initialization and permissions/redaction; the Python example uses `history_level="audit"` to include authentication, exports and failed writes |
| Cursor-style navigation over fictional records | Database keyset queries without COUNT/OFFSET and signed, expiring cursors |
| Scalar/related CSV with column selection, current filters and sorting | XLSX, batched database relation queries and server export limits |
| Local checks for required values, choices, UUIDs, numeric bounds and relationship constraints; local rollback and stale-edit checks | Python parsers, Pydantic schemas, OperationHooks and atomic database writes |
| View-only metadata, record action effects and bulk confirmation/results over local records | Server authorization on every request, Python action handlers and database transactions |
| Read-only Demo accounts | Form-only password input, Pydantic validation, create/update application services and password hashing |

The browser does not run FastAPI, Litestar, an ORM or an authentication server. The
`admin` / `admin` login is an interface fixture. It does not verify authentication,
CSRF, server authorization, durable auditing or database compatibility. No real session
cookies, passwords, production secrets or application records are exported. The browser's
Demo accounts cannot be created, edited or deleted; use the Python application for those services.

For those features, run the [local ASGI example](quickstart.md#run-the-sample-application)
and open its tables through Home or Find a table. It includes the same fields and
relationships, real record/bulk actions, application-service forms, hooks, activity storage
and CSV/XLSX exports. The Demo accounts are sample data, separate from admin sign-in.
See [storage](storage.md), [configuration](configuration.md), [application services](extensions.md)
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
inclusive dates, seed upgrades, composite keys, local permissions/actions, cursor windows,
CSV escaping, filters and schema layout. Python integration tests exercise the example's
custom controls, hooks and account services. The site's existing deployment artifact
includes the complete browser output.
