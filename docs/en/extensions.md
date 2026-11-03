# Operations and extensions

`Field`, `ModelSchema`, `Query` and `Relation` describe data without HTML dependencies.
Configure controls with `FieldOptions`, add [pages and templates](custom-pages.md),
or wrap reads with a [service adapter](custom-adapters.md).

## Write lifecycle

1. Revalidate identity and authorize the collection action.
2. Validate CSRF, writable fields, scalar types and relationship selections.
3. Call `OperationHooks.before_write` with a snapshot of the operation.
4. Execute one atomic adapter/service write; errors roll it back.
5. Call `OperationHooks.after_write` after commit, then log safe metadata and redirect.

```python
from quite_admin import OperationHooks, current_operation
from quite_admin.errors import ValidationError

async def validate(operation):
    if operation.values.get("stock", 0) < 0:
        raise ValidationError({"stock": "Stock cannot be negative."})

async def notify(operation, saved):
    await notifications.admin_change(operation.collection, operation.action)

admin = Admin(
    auth=auth_backend, secret_key=session_secret,
    hooks=OperationHooks(before_write=validate, after_write=notify),
)
```

Hooks may be sync or async. Sync hooks must not perform blocking I/O. They run for
create, edit (including relationships), delete and custom record actions. `Operation`
contains request, current identity, collection, model, action, typed key, values,
relationship keys and the previous record. Mappings are copied snapshots with read-only
top levels; changing nested snapshot values cannot change the pending write.
Hooks do not mutate form values; use a field parser or service for transformations.

`current_operation()` returns this context inside services and native ORM hooks,
including synchronous adapter workers. It returns `None` outside admin writes and is
reset on failure. Do not retain the request or operation beyond its request lifetime.

The before hook runs **outside** the adapter transaction and sees a potentially stale
record. Critical invariants and row authorization must be enforced inside the service's
transaction. After hooks are notifications: failure emits `quite_admin.after_write_failed`
with safe metadata and does not turn a committed write into a failed response. For a
durable audit, write an audit row/outbox inside the adapter/service transaction. There is
no built-in durable audit store. Callback exception messages and record values are not logged.

## Per-model services and form schemas

Keep the native adapter and attach business creation to the model's normal options:

```python
async def create_link(operation, payload):
    user = await users.get(operation.identity.subject)
    return await links.create(payload, user=user)

admin.register(Link, options=ModelOptions(
    create_fields=("long_url", "organization_id"),
    create_schema=LinkCreate,
    create_handler=create_link,
    update_schema=LinkUpdate,
))
```

`create_handler(operation, payload)` replaces creation for this model only. Other
models and unconfigured operations keep native adapter behavior. The payload is an
ordinary dictionary unless `create_schema` is set; then it is the validated Pydantic
model. Handlers can return a scalar mapping or an ORM instance with loaded scalar
attributes. Only fields in the adapter schema reach redirects, history and after hooks.
Return the complete persisted record, including generated/default values and its key.

Install `quite-admin[pydantic]` to opt into Pydantic 2 `create_schema` / `update_schema`.
Existing FastAPI installations already include Pydantic. Schemas validate after CSRF,
permissions and scalar field allowlists, before lifecycle hooks and persistence. Field
errors appear in the form; model-level errors appear at the top. Inputs and error
context are not logged. Form fields are still discovered from the adapter and configured
with `create_fields`, `edit_fields` and [input_fields](configuration.md#form-only-input-fields).
Schemas do not add database columns or implicitly expose additional fields.

Without a custom handler, normalized submitted values go through the native atomic
save, including stale-edit checks. Unsubmitted schema defaults are not written. Use an
update schema whose fields are optional for partial/inline edits; validation sees only
submitted changes, not a merged previous record. A custom handler receives the full
validated payload, including its schema defaults, and owns the persistence policy.

For a service that owns editing, set `update_handler`:

```python
async def update_link(operation, payload, *, guard):
    return await links.update(
        operation.key, payload, actor=operation.identity.subject,
        selections=operation.relations, guard=guard,
    )
```

The service owns one transaction, rollback and error translation. It must apply a
non-null `guard` to freshly locked state **inside that transaction**, as described in
the [checked adapter contract](custom-adapters.md#concurrent-edits). `guard=None` means
the configured adapter has no checked-write capability. Do not check a stale snapshot
before a separate write. Relationship selections in `operation.relations` must also be
saved and checked atomically; a handler replaces the entire write, including relations.
Handlers run within `current_operation()`, between the normal before/after hooks.
Sync handlers must not perform blocking I/O. Raise the public `ValidationError`,
`Conflict` or `NotFound` errors for expected service failures.

## Record actions

```python
from quite_admin import ModelOptions, RecordAction

async def publish(operation):
    return await products.publish(operation.key, actor=operation.identity.subject)

admin.configure("products", options=ModelOptions(
    actions=(RecordAction("publish", "Publish", publish),),
))
```

Buttons appear on the unified record page. Execution requires POST, a valid session,
CSRF and `edit` permission by default. Set `required_permission="delete"` for a destructive
action and/or supply an additional `permission` callback. A handler accepts `Operation`,
owns its transaction and returns a scalar mapping or `None`; the response redirects to
the current record. Actions that remove a record should provide a separate confirmation
flow/custom page and redirect behavior in the application. GET never executes an action.
Handlers can raise the public adapter errors. Keep action labels in the configured UI language.

Adapter compatibility is governed by `ADAPTER_API_VERSION` and the documented
[adapter contract](custom-adapters.md#compatibility-contract). Template changes and safe
field-default changes are listed in `CHANGELOG.md` for the 0.2.0 migration.
