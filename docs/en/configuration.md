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
Foreign keys appear as scalar fields with a hint identifying the referenced table.

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
