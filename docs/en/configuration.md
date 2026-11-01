# Collections and fields

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
The old `/edit` GET URL redirects to the record page; POST remains a compatibility alias.
Click a table row to open that page. Its link also supports keyboard navigation and opening a
new tab. The only separate row action is deletion, which opens a confirmation page.
Users without view/edit permission receive no record link; delete controls follow delete permission.
With discovery enabled, `register()` overrides the settings for an existing model.
For reflection, use `admin.configure("table_name", options=...)` without a model import.

## Field settings

| Option | Behavior |
| --- | --- |
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
These defaults change 0.1.0 behavior; add deliberate exceptions when upgrading.
Excluding a PK does not make its identity secret: record URLs encode the key.

## Custom field controls

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

## Database type controls (0.3.0)

| Database/model type | Built-in control |
|---|---|
| CHAR / VARCHAR, bounded strings | Single-line input with discovered `maxlength` |
| TEXT, Tortoise/Peewee TextField | Full-width multiline textarea |
| DATE | Themed in-page calendar, localized display, ISO value; native input fallback |
| DATETIME / TIMESTAMP | Native date/time picker plus explicit optional UTC offset |
| TIME | Native time picker plus optional UTC offset |
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

Date/time pickers never convert into the browser timezone. `Z` or an explicit `±HH:MM`
offset is retained separately; an empty offset means a naive value. Fractional seconds
use a separate optional input (up to six digits) so browser picker limitations cannot
truncate microseconds. Merely opening a form
does not normalize or truncate its original timestamp. Unsupported ISO shapes/offsets and
invalid submitted values stay in the text input. Without JavaScript, datetime/time remain
ISO text inputs and JSON remains a normal textarea. The no-script native calendar presentation depends
on browser/OS. Server-side parsing, model constraints, field permissions, CSRF and signed
stale-edit revisions remain authoritative. Built-in scripts use the existing per-page CSP hash.

Future widget extension approaches are compared in the [widget design proposal](field-widgets.md).

## Sidebar groups

Set `ModelOptions(group="Sales")` on each collection to group its sidebar links.
For SQL reflection use `admin.configure("orders", options=ModelOptions(group="Sales"))`.
Groups follow first appearance, support keyboard collapse/expand and remember state per
admin mount when browser storage is available. The current collection's group opens
automatically. Ungrouped collections appear under Other collections when grouping is used.
Permissions filter collections before grouping; empty or inaccessible groups are omitted.

Boolean fields use keyboard-operable switches. Nullable booleans have an explicit None
button, preserving the distinction between false and SQL NULL. Read-only values stay
read-only; without JavaScript the original select remains usable.

## Editing list cells

Click the pencil/value of a writable displayed field to edit it without opening a record.
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
exact `COUNT(*)` or a growing OFFSET. It orders by the complete primary key (first part
ascending/descending, remaining parts ascending), including composite keys. Other columns
do not offer sort controls in this mode. The default `pagination="offset"` retains exact
totals, page numbers and arbitrary visible-field sorting.

Cursor links are signed, expire with the configured session age and are bound to the
collection, identity, filters, search, ordering and page size. Changing a filter/search
starts a new traversal. They do not freeze database contents; concurrent inserts/deletes
can change the visible pages. Exports still include all matching records within export
limits, regardless of the current cursor.

Custom adapters can implement `WindowAdapter.list_window(model, query, after=...,
before=...)` from `quite_admin.pagination`. It returns `RecordWindow(records, has_next,
has_previous, next_key, previous_key)`, with typed complete source keys. Use only one
boundary, a zero query offset and primary-key ordering. A projected window must include
all primary-key fields. This method is separate from the required Adapter API.

SQL reflection and SQLAlchemy/SQLModel also accept `query_timeout=2.0` in the adapter
constructor. The positive number of seconds limits reads on SQLite, PostgreSQL and MySQL;
`None` disables it. SQLite uses an operation-scoped progress handler, PostgreSQL a local
statement timeout and MySQL a temporary SELECT timeout. Connection settings are restored
or the connection is invalidated before pool reuse; failed reads return a safe 504.
Writes retain their own transaction behavior. Pool acquisition and Python rendering are
not covered; configure request/pool timeouts in the host application when needed.
