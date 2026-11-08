# Admin storage and activity history

quite-admin owns its service storage independently of business models and their ORM.
By default it uses `.quite-admin/state.sqlite3`, resolved against the working directory
when `Admin` is constructed. No storage configuration, models or application migrations
are required. With history enabled, the file is created lazily on the first
authenticated request.

## Default SQLite

The built-in `SQLiteStore` uses Python's standard library. Connections are opened in
worker threads for one operation and closed afterwards. It enables WAL, waits up to
15 seconds for locks, and creates new directories/files with private permissions.
Existing user-owned permissions are preserved.

Use a stable, writable directory. In containers, mount persistent storage at the
directory containing the file. Do not use a temporary directory for durable history.
Several workers on one host may share the file. Separate servers should use server
storage; sharing a WAL file over NFS is unsupported. Back up a live SQLite database
using SQLite's backup API or stop writers before taking a consistent backup.

An optional environment variable requires no Python changes:

```bash
QUITE_ADMIN_STORAGE_URL=sqlite:////var/lib/my-app/admin.sqlite3
```

An explicit `storage` argument takes precedence over the environment:

```python
from quite_admin import Admin, SQLiteStore

admin = Admin(
    auth=auth,
    secret_key=session_secret,
    storage=SQLiteStore("/var/lib/my-app/admin.sqlite3", namespace="backoffice"),
)
```

## Existing SQLite, PostgreSQL or MySQL

Pass a SQLite file path/`Path`, a `sqlite:///...` URL, a server URL, or a store instance.
Relative SQLite URLs use three slashes; absolute paths use four.
PostgreSQL/MySQL URLs require `quite-admin[sqlalchemy]` and the selected driver, for
example `psycopg[binary]` or `PyMySQL`. The normal SQLite backend needs neither.

```python
admin = Admin(
    auth=auth,
    secret_key=session_secret,
    storage="postgresql+psycopg://user:password@localhost/application",
)
# Also accepted via QUITE_ADMIN_STORAGE_URL:
# mysql+pymysql://user:password@localhost/application?charset=utf8mb4
```

Use an existing sync or async SQLAlchemy engine without duplicating credentials:

```python
from quite_admin.stores.sqlalchemy import SQLAlchemyStore

admin = Admin(
    auth=auth,
    secret_key=session_secret,
    storage=SQLAlchemyStore(engine, namespace="backoffice"),
)
```

The application retains ownership of borrowed engines. Service operations always use
their own connections and transactions, never the business session. URL-created
engines default to `NullPool`, closing connections after each operation. To configure
an owned pool directly, pass engine options with the URL:

```python
storage = SQLAlchemyStore(
    database_url,
    namespace="backoffice",
    engine_options={"pool_size": 2, "max_overflow": 0, "pool_timeout": 3,
                    "pool_pre_ping": True},
)
```

`engine_options` accepts SQLAlchemy `create_engine()` keyword arguments and is valid
only with a URL. Without an explicit pool class or sizing options, `NullPool` is used.
Driver-specific timeouts can be supplied through `connect_args`.
FastAPI and Litestar mount helpers automatically dispose URL-created storage engines
on shutdown. `await admin.aclose()` / `async with admin.lifespan():` support other
integrations. Borrowed engines are never disposed; `await storage.aclose()` follows the
same ownership rule. No separate shutdown code is needed for the normal mount flow.
Async drivers require an application-owned `AsyncEngine`; string URLs use sync drivers.
All workers/replicas must point to the same store, namespace and session secret.
Namespaces separate service data for different admins sharing one database.

## Reserved tables and document format

The library automatically creates these tables and their `quiteadmin_` indexes:

| Table | Purpose |
| --- | --- |
| `quiteadmin_meta` | Internal storage schema version |
| `quiteadmin_documents` | Versioned JSON documents for service features |
| `quiteadmin_activity` | Activity event metadata |
| `quiteadmin_activity_details` | Bounded before/after field values |
| `quiteadmin_actors` | Compact user/table index for autocomplete |

Reserve the entire `quiteadmin_` prefix. These tables never appear as ordinary admin
tables, including when SQL discovery uses the same database. Table creation
requires DDL permissions; routine operations require read/write permissions.
Initialization is serialized across workers. Unknown storage schema versions are
rejected rather than overwritten. The physical schema version is 2; the library manages
service-schema initialization and upgrades independently of application migrations.
Existing documents and events are preserved. Metadata-only events have no field
comparisons; values that were never recorded cannot be recovered.

`admin.storage` exposes the `AdminStore` protocol. Documents contain a key, kind,
owner, JSON payload, format version and revision. `save_document()` creates with
`expected_revision=0`; updates/deletes require the previously read revision and raise
`StorageConflict` on concurrent changes. Document payloads are limited to 1 MiB.
`documents()` returns bounded pages, with the last document key passed as `after`.
The store is a foundation for future dashboard features; a dashboard editor is not
included in this release.

## Activity history

Follow the [interface tour](interface-tour.md) to filter a user's actions, inspect a field
comparison and switch between Journal/Table. The [browser demo](browser-demo.md) shows
fictional sample events and your local edits; the ASGI example exercises the durable store.

[![Activity journal with persisted field comparisons](../assets/screenshots/activity-history.png)](../assets/screenshots/activity-history.png)


Open **Activity history** in the sidebar. The toolbar reuses the table listing
filter editor: **Add filter** selects a user, table, action or success/failure
result. Search values, edit active chips or remove an individual condition with ×.
**Clear all** removes these conditions while preserving the separate period control
in the same toolbar. Users are discovered from
recorded activity, including accounts that have since been removed. The lookup
searches recorded subjects and display names with a bounded result set; selecting
a result applies the exact subject. Events are ordered newest first in UTC, with signed pagination
and no extra total-count query. The journal groups events by day and shows changes
by default; **All actions** includes other events allowed by `history_level`.
Exports and authentication require `audit` or `all`; views require `all`.
Expand an event to compare **Field / Before / After**, follow its record link, or use
**Expand all changes** to review the whole page.
Use the **Journal / Table** toggle above the events to switch to the compact table.
The journal is the default. Both views retain field comparisons and preserve filters
and the current page when switching. The selected view stays in the URL when applying
or clearing filters, reloading, or following pagination links; JavaScript is not required.

The compact period control shows the applied dates and UTC. Open it for **Quick select**
(Today, Yesterday, Last 7/30 days, This month, Any date), **Specific day** with one
calendar, or **Date range** with two calendars and editable endpoints. Quick presets
apply immediately; custom dates use **Apply period**. **Cancel**, Escape or clicking
outside discard unapplied edits. Calendar days and tabs support keyboard navigation.
Days and both range
endpoints are inclusive, from midnight to the final microsecond in UTC. Leave either
range bound empty for an open range. Inactive date fields do not affect the filter.
Reversed ranges and invalid dates are rejected.
The database applies the date bounds before pagination using timestamp indexes;
switching views, clearing condition chips and following pagination links preserve the
period. Select **Any date** in the period picker to remove the date restriction.

### Recording level

Set one optional constructor argument to choose how much activity to retain:

```python
admin = Admin(auth=auth, secret_key=session_secret, history_level="changes")
```

| Level | Events recorded and visible |
| --- | --- |
| `changes` (default) | Committed create, edit, inline edit, delete and custom record actions, including relationship writes inside saves. |
| `audit` | Everything in `changes`, plus failed writes/custom actions, login/logout and exports. |
| `all` | Everything in `audit`, plus table listings and record/form views, including failed reads. |

The level is enforced **before creating/appending an activity event**, not just in
templates. Excluded requests write no activity, field-details or actor-index rows.
The same level filters old events and user autocomplete before paging. Changing the
level preserves existing data; switching to `all` can show previously stored events,
but cannot recover events that were never recorded. Constructor configuration is
authoritative: URL filters and **All actions** cannot increase the level.

Direct `admin.storage` calls are a raw storage API and default to all events;
they do not inherit an admin instance's recording/display policy.

Authenticated failed requests at an enabled level retain their HTTP status. Anonymous
requests and failed login names are not attributed to a trusted user. History browsing
and user autocomplete do not record themselves. Diagnostic/application logging is
independent of this activity setting. Operations performed outside quite-admin are
not captured; a committed operation can still have no visible field differences.

Built-in SQLite and SQLAlchemy stores advertise `supports_history_levels=True` and
accept the optional `history_level` keyword on `activities()` / `actors()`, defaulting
to `all`. Filtering happens in SQL before limits/cursors. The required `AdminStore`
protocol is unchanged: older custom stores use its existing filters and paged reads,
with a filtered fallback for audit pages and user lookup. Implement the optional
capability for efficient filtering on large custom histories.

Events contain time, authenticated subject/display name, table slug, action,
outcome and HTTP status. Successful writes also store changed field names, labels,
previous/persisted values and a record key when its fields are visible. Creation
shows absent → value; deletion shows value → absent. NULL, empty strings and false
remain distinguishable. Custom actions reread the source record after execution.
Explicit relationship selections are compared by related primary keys in the same
parent save event. Failed writes have no saved-value comparison.

Hidden fields, binary values and recognized password/token/secret fields are excluded,
even when sensitive fields are explicitly exposed in the UI. Nested JSON credentials
are redacted. Current field visibility and relationship permissions are reapplied
when viewing historical values. Values are limited to 4 KiB each, 200 field changes
and 512 KiB per event, with visible truncation notices. Form bodies, search terms
and SQL text are not stored. Ordinary diagnostic logs contain no field values.
Backups of service storage contain historical business values; apply the same
access controls as to the source data.

By default every authenticated admin can open history. The history page and user
search both apply the viewer's current `list` **and** `view` table permissions.
Events for removed/unregistered tables are hidden. Authentication events are
separate. An optional callback further restricts access to the entire section:

```python
admin = Admin(
    auth=auth,
    secret_key=session_secret,
    history_permission=lambda request, identity, action: "admin" in identity.roles,
)
```

The callback supports sync/async functions and receives `action="view"`.

History is enabled by default (`history_enabled=True`). Disable the entire feature:

```python
admin = Admin(auth=auth, secret_key=session_secret, history_enabled=False)
```

This hides the section, returns 404 for both history URLs and skips event recording,
field capture and automatic history-storage initialization. Existing history is
preserved. `admin.storage` remains available independently for other service features.

## History retention

`Admin(history_retention_days=90)` keeps 90 days by default. Set another positive
integer (up to 365000), or `None` to retain history indefinitely. The setting applies
to activity events and their before/after details, independently of `history_level`.
It does not delete business records or saved service documents.

With history enabled, the first request that initializes the store also performs
one cleanup batch (at most 1000 expired events). Later requests trigger at most one
batch every five minutes per Admin/process. No scheduler or background worker is
required. Cleanup is eventually applied: an inactive admin performs no cleanup,
and a large existing backlog needs several batches. Multi-worker cleanup is safe;
each transaction is scoped to the configured namespace. Unreferenced actor entries
are removed with the events. Cleanup errors emit a sanitized warning and preserve
the request; they never undo a business write. `history_enabled=False` disables
automatic cleanup as well as recording.

To drain a backlog immediately, use the command below. It defaults to 90 days and
1000 events per transaction, repeating batches until finished. Use the same storage
and namespace as the application. `QUITE_ADMIN_STORAGE_URL` is used when `--storage`
is omitted; avoid putting credential-bearing URLs in shell history.

```bash
python -m quite_admin cleanup-history --storage /var/lib/my-app/admin.sqlite3 --namespace backoffice
python -m quite_admin cleanup-history --days 30 --batch-size 500
```

Application code can run one batch with `await admin.purge_history(limit=1000)`.
The store-level capability `HistoryRetentionStore.purge_activities(before=..., limit=1000)`
accepts a timezone-aware datetime and returns the number removed. Built-in SQLite
and SQLAlchemy stores implement it. Custom stores remain compatible with `AdminStore`;
to support automatic retention, implement this optional capability atomically, including
details/actor cleanup. Without it, cleanup logs a warning; explicit `purge_history()`
raises `NotImplementedError`. Set `history_retention_days=None` for stores with an
application-managed retention policy. Raw store methods perform no automatic cleanup.

## Failure and durability semantics

With history enabled, storage initialization failures return a safe 503 before login or a protected
operation proceeds. Activity appends are awaited before the response is sent. A
later activity-storage failure cannot undo an already committed business write:
the response is preserved and a sanitized `quite_admin.activity_failed` warning
contains only the exception type. There is no in-memory fallback or background
queue pretending to provide durable history.

The business database and service store do not participate in one atomic transaction,
even when they use the same engine. A process/storage failure can leave a gap in
history. Strict atomic auditing requires an application-owned transactional outbox
or another integration at the business transaction boundary. Changes performed
outside quite-admin are not captured. Events expire according to the configured retention policy; plan
disk space and backups for that period.
