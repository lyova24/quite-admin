# Collections and fields

## Admin settings

All `Admin(...)` arguments are keyword-only. Configure the instance before serving requests.

| Argument | Default and purpose |
|---|---|
| `auth`, `secret_key` | Required authentication backend and persistent random secret of at least 32 bytes; see [authentication](authentication.md) |
| `adapters` | `()`; existing data adapters, with discovery enabled |
| `title`, `description` | `"Quite Admin"`, `""`; application name and optional introduction |
| `language` | `"en"`; `"en"` or `"ru"` for the built-in interface |
| `theme`, `logo` | `None`; default `Theme()` and bundled logo, or a palette and local image path; see [appearance](customization.md) |
| `templates_dir` | `None`; application template directory with precedence over packaged templates |
| `secure_cookies` | `True`; use `False` only for local HTTP |
| `session_cookie` | `"quite_admin_session"`; choose distinct names for separate admins on the same domain |
| `session_max_age` | `28800` seconds (8 hours); positive session, revision and cursor lifetime |
| `logger`, `log_structured` | `None`, `False`; application-owned [logging](logging.md) |
| `hooks` | `None`; optional `OperationHooks` for the [write lifecycle](extensions.md) |
| `storage` | `None`; environment URL or private local SQLite, or an explicit path, URL or `AdminStore`; see [storage](storage.md) |
| `history_enabled` | `True`; record and display activity history |
| `history_level` | `"changes"`; committed writes; `"audit"` adds authentication, exports and failures, `"all"` adds reads |
| `history_retention_days` | `90`; positive days to retain history, or `None` to disable cleanup; [retention](storage.md) |
| `history_permission` | `None`; optional sync/async callback restricting history and user lookup |
| `query_timeout` | `None`; optional positive deadline in seconds for an admin read, including its queue and async pool wait |
| `max_concurrent_reads` | `None`; optional positive integer limiting simultaneous reads across this admin in one process |

Use `add_adapter(adapter, discover=True, namespace=None)` to attach a data source,
`register(model, adapter=..., options=...)` to select/configure a model and
`configure(slug, options=...)` to configure a discovered collection. `ModelOptions` replaces
the collection's options as a whole; include every setting you want to retain.
Mount with `mount_fastapi(app, "/admin")`, `mount_litestar(app, "/admin")` or
`litestar_route("/admin")`; see [integration](integration.md).

## Register collections

Auto-discovery is optional. Register only the existing models you want to expose:

```python
from quite_admin import Admin, FieldOptions, ModelOptions

admin = Admin(auth=auth_backend, secret_key=session_secret)
admin.add_adapter(adapter, discover=False)
admin.register(User, options=ModelOptions(
    label="Users",
    list_fields=("id", "email", "is_active"),
    edit_fields=("email", "is_active", "created_at"),
    create_fields=("email", "is_active"),
    readonly_fields=("created_at",),
    exclude=("password_hash",),
    search_fields=("email",),
    filter_fields=("is_active", "created_at"),
    fields={"email": FieldOptions(label="Email", help_text="Notification address")},
    can_create=False,
    can_delete=False,
))
```

`ModelOptions` works with every adapter.
Each existing record has one page for viewing and editing. Its fields become read-only when
the user cannot edit; the server also rejects direct POST requests. `edit_fields` orders and
selects writable form fields; other visible fields remain on that page as read-only values.
Click a table row to open that page. Its link also supports keyboard navigation and opening a
new tab. The only separate row action is deletion, which opens a confirmation page.
Users without view/edit permission receive no record link; delete controls follow delete permission.
With discovery enabled, `register()` overrides the settings for an existing model.
For reflection, use `admin.configure("table_name", options=...)` without a model import.

## Field settings

| Option | Behavior |
| --- | --- |
| `slug`, `label` | Collection URL name and display name; defaults come from the adapter schema |
| `list_fields` | Columns in the list; the default is the first six visible fields |
| `edit_fields` | Field order and selection for edit forms |
| `create_fields` | Field order and selection for create forms |
| `readonly_fields` | Show values but reject writes |
| `exclude` | Hide fields and reject writes and searches against them |
| `search_fields` | Text fields used by search |
| `filter_fields` | Visible scalar filters; `None` discovers supported fields, `()` disables them |
| `relations`, `readonly_relations` | Available relationship editors and read-only links |
| `record_label` | Field used to label records in relationship selectors |
| `fields` | Labels, help text and per-field read-only settings |
| `can_create`, `can_edit`, `can_delete` | Enable or disable operations |
| `permission` | Sync/async `(request, identity, action)` callback; see [permissions](authentication.md) |
| `expose_sensitive_fields` | Explicit exceptions to automatic secret-name hiding; `exclude` still wins |
| `writable_protected_fields` | Explicit exceptions to automatic service/privilege-field protection |
| `group` | Optional nonempty sidebar group label |
| `list_editable` | `None` enables eligible displayed fields, a tuple selects fields, `()` disables inline edits |
| `pagination` | `"offset"` for totals/page numbers or `"cursor"` for count-free sorted traversal |
| `input_fields` | Tuple of form-only `Field` definitions consumed by a handler/service |
| `create_schema`, `update_schema` | Optional Pydantic 2 models validating submitted values |
| `create_handler`, `update_handler` | Per-model services replacing native creation/editing; see [services and schemas](extensions.md) |
| `actions` | Tuple of permission-checked `RecordAction` buttons on the record page |
| `bulk_actions` | `()`; per-collection `RecordAction` commands available only in the list's right-hand icon menu; [bulk actions](extensions.md#bulk-actions) |
| `bulk_delete` | `True`; allow page-local bulk delete subject to ordinary delete permission; [bulk actions](extensions.md) |

`FieldOptions(read_only=True)` also makes a field read-only.
Unknown configuration fields raise a configuration error.

Names containing `password`, common secret names (`secret`, `token`, `credentials`,
`authorization`, `api_key`, `private_key`, `session_key`) and names ending in `_token`
or `_secret` are hidden by default. Explicit `exclude` always wins. This naming heuristic
does not identify every secret; review discovered metadata before exposing a database.
Use `expose_sensitive_fields=("api_key",)` only for a deliberate exception.

`created_at`, `updated_at`, `deleted_at`, `created_by`, `updated_by`, `is_admin`,
`is_superuser`, `is_staff`, `roles` and `permissions` are read-only by default.
Opt in with `writable_protected_fields=("is_admin",)` when the application allows it.
This never overrides explicit, generated or adapter-provided read-only restrictions.
Excluding a PK does not make its identity secret: record URLs encode the key.

## Custom field controls

`FieldOptions(display="url")`, `display="json"` and `display="multiline"` add built-in value controls.
`url_template="https://short.example/{value}"` builds a display-only link from a scalar
without a formatter. See [value displays](field-widgets.md) for URL safety, copying,
read-only behavior and unchanged persistence/export semantics.

`FieldOptions` accepts `kind`, `parser`, `formatter` and `template` in addition to labels
and help text. For example, a counter formatted as `#7`:

```python
FieldOptions(
    kind="string",
    parser=lambda raw: int(raw.removeprefix("#")),
    formatter=lambda value: "#" + str(value),
    template="counter.html",
)
```

The parser returns the native value or raises `ValueError`. The formatter returns text,
which templates escape. The optional template receives `field`, `values`, `errors` and
the normal shared context. Render a control named `{{ field.name }}` with its value from
`values[field.name]`. It is included only for writable fields; standard labels/errors and
server-side allowlists remain active. Unsupported adapter types remain read-only unless
a custom adapter explicitly describes a supported field type/codec. See [extensions](extensions.md).

Primary keys are immutable after creation. Generated and computed fields cannot be edited.
Binary and unknown field types are displayed read-only. A non-generated primary key
can be provided when creating a record.

POST requests containing unknown, hidden or read-only fields fail with `422`.
The server enforces the allowlist independently of the browser form.

## Defaults, nulls and types

Fields with defaults offer **Use model / database default** in the create form.
Clear that checkbox to supply an explicit value.
A blank nullable field means `NULL`; a blank non-null string means `""`.

Supported scalar types include strings, integers, booleans, float, Decimal, UUID,
ISO date/time/datetime, JSON and enums.
Foreign keys appear as scalar fields with a hint identifying the referenced table,
unless an available [relationship editor](relationships.md) replaces them.

If an excluded or read-only required field has no default, disable creation or use
an adapter that fills the field through your application service.

## Multiple data sources

```python
admin.add_adapter(sqlalchemy_adapter, namespace="billing")
admin.add_adapter(tortoise_adapter, namespace="catalog")
# /admin/models/billing-orders/ and /admin/models/catalog-products/
```

When several adapters are configured, pass `adapter=adapter` to `register()`.
Conflicting collection names require a namespace or `ModelOptions(slug=...)`.

## Concurrent edits

Built-in adapters reject stale edit forms atomically: if a record or an edited
relationship changed after opening the page, saving returns **409**. Entered values
remain on the form. Use **Reload record** to load the latest version before editing
again. No database migration or extra version column is required. Revision tokens
expire with the configured session lifetime and are bound to the user, collection
and complete primary key. They contain keyed fingerprints, not field values.

The standard template includes the token automatically. When upgrading a custom
`form.html`, include this inside the edit form alongside the CSRF input:

```jinja
{% if revision_token %}
<input type="hidden" name="__revision" value="{{ revision_token }}">
{% endif %}
```

HTTP clients must GET the form and echo its `__revision` on each edit. A missing,
invalid or expired revision also returns 409. Do not replace the old revision with
a new one after a conflict without reviewing the latest record. This applies to
form edits, not delete requests or custom actions. Custom adapters opt in through
[`CheckedAdapter`](custom-adapters.md#concurrent-edits); others retain their own write policy.

See [list filters](filters.md) for `filter_fields` and related-record filtering.

## Database type controls

| Database/model type | Built-in control |
|---|---|
| CHAR / VARCHAR, bounded strings | Single-line input with discovered `maxlength` |
| TEXT, Tortoise/Peewee TextField | Full-width multiline textarea |
| DATE | Themed in-page calendar, localized display, ISO value; native input fallback |
| DATETIME / TIMESTAMP | Shared calendar with time, optional fractional seconds and UTC offset |
| TIME | Time-only version of the same picker, with optional fractional seconds and UTC offset |
| JSON / JSONB | Monospace editor, syntax highlighting, syntax status and Format JSON |
| Integer / Decimal / float | Numeric input with integer or arbitrary step |
| Boolean | Toggle with explicit nullable state; select fallback |
| Enum | Select with allowed values; nullable fields include an empty choice |
| UUID | Text input with server-side UUID validation |
| Binary / unknown | Read-only, unless an existing explicit parser/template policy handles it |

Text metadata works with SQL reflection as well as ORM adapters; no ORM is required.
`Field.multiline` is optional metadata for custom adapters, defaulting to `False`.
Logical kinds remain `string`, so search, filtering and parsing keep their existing behavior.
`String()` without a length remains a single-line control; only an actual TEXT type
(or TextField) implies multiline. `FieldOptions.template` still takes precedence.

JSON highlighting is local and uses text nodes, without loading an external editor.
**Format JSON** preserves numeric lexemes, duplicate keys and string escapes; it never
rewrites numbers through JavaScript floating point. Syntax status does not replace
server-side type/nullable checks. Highlighting is disabled above 200,000 characters,
formatting beyond 40 levels of nesting; the ordinary textarea continues to work.

Try editable DATE, DATETIME, TIME, nullable boolean, TEXT and JSON in **Schedules** in the
[browser demo](browser-demo.md). The [interface tour](interface-tour.md) shows the form and inline editor.

Forms, listing filters, inline edits and activity history reuse one themed calendar.
Record forms and inline edits keep date and time directly editable: DATE has one date
input, DATETIME has a date and time alongside each other, and TIME has a time input.
The compact calendar has no duplicate date input or extra Apply step: selecting a day,
**Today** or **Clear** updates the form field and closes it. Save the record with the
form's **Create record** / **Save changes** button. Escape or clicking outside closes
calendar navigation without changing the field. The calendar does not scroll the page.

Filters retain **Apply** / **Cancel** for draft selection. A **Between** filter opens
one panel with two endpoints, including time when required. **Clear** empties both
range endpoints. Day-based history filtering retains full inclusive UTC days.
Calendar days support arrow keys, Home/End and Page Up/Down; Alt+Down opens a form calendar.

Date/time pickers never convert into the browser timezone. `Z` or an explicit `±HH:MM`
offset is retained separately; an empty offset means a naive value. **More options**
in forms (**Precision and timezone** in filters) expands optional offset and
fractional-second inputs (up to six digits),
so browser picker limitations cannot truncate microseconds. Merely opening a form
does not normalize or truncate its original timestamp. Unsupported ISO shapes/offsets and
invalid submitted values stay in the text input. Without JavaScript, datetime/time remain
ISO text inputs and JSON remains a normal textarea. The no-script native calendar presentation depends
on browser/OS. Server-side parsing, model constraints, field permissions, CSRF and signed
stale-edit revisions remain authoritative. Built-in scripts use the existing per-page CSP hash.

See [field controls and custom widgets](field-widgets.md) for a complete template/parser example.

## Sidebar groups

Set `ModelOptions(group="Sales")` on each collection to group its sidebar links.
For SQL reflection use `admin.configure("orders", options=ModelOptions(group="Sales"))`.
Groups start collapsed, follow first appearance, support keyboard collapse/expand and remember state per
admin mount when browser storage is available. The current collection's group opens
automatically without saving that automatic opening as a preference. Explicitly opened
groups remain open on later visits. Without browser storage or JavaScript, other groups
still start collapsed. Ungrouped collections appear under Other collections when grouping is used.
Permissions filter collections before grouping; empty or inaccessible groups are omitted.

Boolean fields use keyboard-operable switches. Nullable booleans have an explicit None
button, preserving the distinction between false and SQL NULL. Read-only values stay
read-only; without JavaScript the original select remains usable.

## Editing list cells

Click the pencil of a writable displayed field to edit it without opening a record.
Clicking the value or another part of the row opens the record page. Boolean switches save immediately.
`ModelOptions(list_editable=None)` (default) enables all eligible displayed fields;
`list_editable=("name", "active")` selects a subset; `list_editable=()` disables it.
Only list columns also allowed by `edit_fields` and field policies are eligible. Hidden,
read-only, generated and primary-key fields cannot be edited. Foreign keys and fields
with custom templates use the full record page instead. Built-in scalar/JSON controls
are reused. Save is explicit; Cancel/Escape discards the local edit.

The endpoint requires list/edit permissions, validates exactly one field, enforces CSRF,
uses write hooks and preserves atomic stale-edit checks. A stale revision returns 409;
invalid values return 422 without clearing the editor. Reload the list after a conflict
before retrying. Custom adapters need `CheckedAdapter` for atomic stale-edit detection,
as for full record forms. No JavaScript is required to use the full record page.

Boolean listing cells also use switches. Editable switches save immediately through
the guarded inline endpoint; read-only switches are disabled. Nullable cells expose an
explicit ∅ button and None state. Failed/conflicting writes leave the displayed state
unchanged and show an error; rapid repeated clicks are disabled during saving.

## Large collections and query deadlines

For a large collection, use `ModelOptions(pagination="cursor")`. Every built-in adapter
supports this mode. It reads at most one extra record to show Next/Previous, without an
exact `COUNT(*)` or a growing OFFSET. Click any scalar column header, including dates,
to sort ascending or descending without additional configuration. The complete primary
key breaks ties in ascending order, including composite keys. NULL values come last in
both directions. With no chosen column, the primary key determines the order.
JSON, binary and unsupported types have no cursor sort control. The default
`pagination="offset"` retains exact totals and page numbers.

Cursor links are signed, expire with the configured session age and are bound to the
collection, identity, filters, search, ordering and page size. Changing a filter, search or sort
starts a new traversal. They do not freeze database contents; concurrent inserts/deletes
can change the visible pages. Exports still include all matching records within export
limits, regardless of the current cursor.

Custom adapters can implement `WindowAdapter.list_window(model, query, after=...,
before=...)` from `quite_admin.pagination`. It returns `RecordWindow(records, has_next,
has_previous, next_key, previous_key)`, with typed complete source keys. Use one boundary
and a zero query offset. Set the optional `supports_window_sorting = True` capability
when the implementation accepts `query.order_by`: boundaries and projections must include
the sort field as well as every primary-key field. Preserve ascending primary-key ties
and NULL-last ordering. Existing custom adapters without this capability retain
primary-key sorting. This method is separate from the required Adapter API.

SQL reflection and SQLAlchemy/SQLModel also accept `query_timeout=2.0` in the adapter
constructor. The positive number of seconds limits reads on SQLite, PostgreSQL and MySQL;
`None` disables it. SQLite uses an operation-scoped progress handler, PostgreSQL a local
statement timeout and MySQL a temporary SELECT timeout. Connection settings are restored
or the connection is invalidated before pool reuse; failed reads return a safe 504.
Writes retain their own transaction behavior. Pool acquisition and Python rendering are
not covered; configure request/pool timeouts in the host application when needed.

## Shared read limits

Configure a shared queue and an operation deadline directly on the admin, with any adapter:

```python
admin = Admin(
    auth=auth_backend, secret_key=session_secret, adapters=[adapter],
    query_timeout=3.0,
    max_concurrent_reads=2,
)
```

Both options default to `None`, preserving existing behavior. The positive timeout
includes waiting for the shared read slot, asynchronous pool acquisition and the read
itself. Expiry returns a safe 504. The positive integer concurrency limit is shared
across all models/adapters of this `Admin` in one process; it is not a cross-worker limit.
Choose it below the business pool capacity when sharing a pool, leaving room for the
host's ordinary traffic. Each worker has its own queue.

The policy covers asynchronous discovery, lists, cursor pages, record lookup,
relationship reads/pickers and exports, including batches. It applies only to reads
performed by the admin: direct adapter calls, authentication services, service-handler
I/O and service storage retain their own policies. Writes and commits are never timed
out by this setting. Failure of a post-commit history reread preserves the successful
write response and emits the existing safe history warning.

Cancellation releases the slot after adapter cleanup. Synchronous database workers
finish before releasing their connection/slot, so a synchronous query can delay the
504 beyond the deadline. Also configure the native SQL/SQLAlchemy `query_timeout`
above to interrupt database execution itself. Async adapters such as GINO receive
cancellation during pool acquisition or query execution; a second adapter wrapper,
semaphore or timeout exception handler is unnecessary.

## Form-only input fields

Declare extra form inputs without adding fictitious columns to your adapter:

```python
from quite_admin import Field, ModelOptions

admin.register(User, options=ModelOptions(
    input_fields=(
        Field("password1", kind="password", label="Password"),
        Field("password2", kind="password", label="Confirm password"),
    ),
    create_fields=("username", "password1", "password2"),
    edit_fields=("username",),
))
```

Input fields participate in scalar parsing, required-value checks and the create/edit
field allowlists. Their names must be unique and must not shadow model fields. Use
`fields={...}` for labels, help and custom controls as usual. Explicitly declaring an
input permits entering a sensitive name without `expose_sensitive_fields`.

The adapter schema stays unchanged. Inputs are unavailable in lists, sorting, search,
filters, exports, record labels, schema diagrams, revision fingerprints and activity
details. An input is not prefilled from a stored record and is hidden on read-only
record pages. Use `create_fields` / `edit_fields` to select its forms.

`kind="password"` renders an accessible password input with `autocomplete="new-password"`.
It is never prefilled or echoed after validation/conflict errors, including in custom
template context. Required passwords reject empty strings on the server. Model fields
explicitly configured with this kind are also excluded from scalar read displays and
exports. Password inputs take precedence over custom field templates.

A [model handler](extensions.md#per-model-services-and-form-schemas) or service adapter
must consume input values before calling a native adapter: hash a
password, validate its confirmation and persist only actual model columns. A native
adapter cannot persist form-only values. See [application services](custom-adapters.md).
