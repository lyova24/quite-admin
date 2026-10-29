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
