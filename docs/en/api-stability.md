# Public API guarantees

**0.4.0 is the compatibility baseline for 0.4.x.** Patch releases preserve documented
imports, call signatures, defaults and behavior. The adapter contract is
`ADAPTER_API_VERSION = 1`; the template contract is `TEMPLATE_API_VERSION = 1`.
These guarantees apply to SQL reflection, native ORM adapters and application-service
adapters alike. CSV/XLSX export does not require an ORM.

## Covered interfaces

| Interface | Guaranteed surface |
|---|---|
| Python imports | Names in `quite_admin.__all__`, `__version__`, `Adapter` from `quite_admin.adapters.base`, public errors from `quite_admin.errors`, `StaleRecord` from `quite_admin.concurrency` |
| Integration | `Admin` constructor, ASGI call, registration/configuration, page registration, FastAPI/Litestar mounting and translation methods |
| Configuration and data | Constructor arguments, defaults and documented methods of `Field`, `ModelSchema`, `ModelOptions`, `FieldOptions`, `Theme`, `Query`, filters, record pages, relationships, actions and identities |
| Built-in adapters | Documented constructors, discovery, metadata, CRUD, relationships and checked writes; `SQLAdapter.refresh()` |
| Extension protocols | `Adapter`, `AuthBackend`, `RelationAdapter`, `CheckedAdapter`, `LoggerProtocol`; hooks and `current_operation()` |
| Templates | Template paths, base blocks and context described below |

Names beginning with `_`, ORM-specific implementation helpers, DOM structure, CSS
classes, built-in JavaScript internals and undocumented context entries are implementation
details. The field-widget registry described in [the proposal](field-widgets.md) is
not an implemented API. Use the existing `FieldOptions.template`, parser and formatter.

## Adapter and write behavior

The [adapter contract](custom-adapters.md) defines typed scalar mappings, complete
primary keys, filtering before count/pagination, projection and atomic writes.
Record keys are opaque strings: use `ModelSchema.record_key()` / `parse_key()`;
do not decode their internal encoding in application code. Existing valid keys continue
to round-trip within 0.4.x. `NotFound`, `Conflict` and `ValidationError` remain
`AdminError` subclasses with HTTP statuses 404, 409 and 422. `ValidationError.errors`
maps field names to messages; exact translated wording is not an API.

The seven required adapter methods stay separate from optional relationships, checked
writes, extended operators, related filters and key search. Old structural adapters
need no base class or new capability declaration. New capabilities require explicit
opt-in; the core must not silently pass unsupported queries. Delegation must not bypass
application-service writes. Changing required adapter methods requires a new
`ADAPTER_API_VERSION` and a documented incompatible package release.

Authentication, authorization, CSRF and writable-field checks run before write hooks.
The [hook lifecycle](extensions.md) stays: before hook → atomic adapter/service write →
after hook. Before hooks may veto; after-hook failure cannot undo a committed write.
Operation mappings have read-only top levels; nested snapshot edits cannot change the
pending write. `current_operation()` is reset on success and failure.

## Template API 1

Import `TEMPLATE_API_VERSION` from `quite_admin`; templates receive
`template_api_version` with the same value. Custom templates take precedence over
packaged files. `quite_admin/base.html` keeps the `title`, `head` and `content` blocks.
The built-in paths `quite_admin/login.html`, `dashboard.html`, `list.html`, `form.html`,
`delete.html`, `error.html` and `schema.html` remain overrideable under that directory.

Every render provides these reserved entries. Page callbacks cannot replace them:

| Entries | Value |
|---|---|
| `request`, `admin`, `identity` | Request, Admin instance, Identity or None on unauthenticated screens |
| `csrf`, `url` | CSRF token; `url(path="/")` callable preserving mount/proxy prefixes |
| `title`, `description`, `language`, `theme`, `logo_url` | Instance branding; logo URL or None |
| `t`, `tn` | Translation and pluralization callables |
| `resources`, `resource_groups`, `pages` | Permission-filtered navigation; groups map labels to resource lists |
| `breadcrumbs`, `scripts`, `template_api_version` | Breadcrumb mappings (`label`, `url`); permitted script mappings (`url`, `integrity`); integer contract version |

Navigation resources expose `slug`, `label`, `schema`, `options` and `record_label(record)`;
their concrete implementation class is internal. Custom pages additionally receive
their `Page` as `page` and application context returned by their callback.

The list exposes `resource`, `columns` (Field sequence), `result` (RecordPage),
`page_number`, `limit`, `query` (Query), `query_url(**updates)` and `permissions`
(`view`, `create`, `edit`, `delete` booleans).
The record form exposes `resource`, `fields`, `values` (formatted strings by field name),
`errors` (messages by field name, optional `__all__`), `defaults` (field-name set),
`creating`, `writable` (name → Field), `record`, `form_action`, `revision_token`,
`stale`, `editable`, `can_delete` and `record_actions`.

A `FieldOptions.template` include additionally receives `field`, `help` (FieldOptions)
and `editable` for that field. Read the current string from `values[field.name]` and
the error from `errors.get(field.name)`. Submit under `field.name`; keep autoescaping.
The include is called only for writable fields. The surrounding form owns CSRF and
revision tokens. Replacing the entire form must retain those tokens and writable-field
policies. Custom templates do not grant extra script permissions or bypass CSP.

## Change and deprecation rules

Compatible additions use MINOR; compatible fixes use PATCH. In 0.x, an incompatible
change requires MINOR, EN/RU migration notes and a changelog entry. Deprecations must
name the replacement and planned removal version, emit `DeprecationWarning` when the
deprecated Python entry point is used, and remain available for at least one subsequent
compatible MINOR release before removal. Template deprecations are announced in the
same documents. After 1.0, incompatible changes require MAJOR. Security fixes may reject
previously accepted unsafe input; they must explain the tightened validation.

The supported Python/framework/ORM matrix is documented in
[dependency compatibility](dependency-compatibility.md); support is not silently dropped
in PATCH. Stable API does not promise unlimited export size, latency targets, durable
audit storage or arbitrary dependency versions.

## Enforced checks

The repository commits `api/*-0.4.json`: imports, signatures, defaults, data fields,
mutability, required protocol members, error statuses, contract versions and base blocks.
`python scripts/check_api.py --profile modern` runs in CI on CPython 3.11–3.15;
the isolated GINO endpoints run `--profile gino`. Optional keyword arguments are accepted;
removed arguments, new required arguments and changed defaults fail the check.
Annotation changes conservatively require review even when they might widen accepted types.

Keep existing baseline entries when extending the API. A planned incompatible release
must explicitly review/update the baseline and migration notes; regenerating it merely
to silence a failure is not an API review. Structural checks cannot prove semantics:
adapter, security, hook, template and browser integration tests remain required.

## Migrating from 0.3.x

Existing constructor calls, adapters and field includes continue to work. `Field`,
`ModelSchema`, `RecordAction` and `Theme` now use explicit constructors and ordinary
assignments. They are mutable and unhashable; stop relying on `FrozenInstanceError`
or using them as dictionary/set keys. Constructor validation, equality and
`dataclasses.replace()` remain. Configure metadata before requests; later assignment
does not rerun validation. Use `Admin.configure()` for collection options, not mutation
of shared metadata during a request. Operation snapshots and write guards retain
their protections. No database migration or new mandatory adapter method is required.

The optional cursor list mode supplies `result` as `RecordWindow` instead of
`RecordPage`: use `result.records` and the `cursor_mode`, `cursor_previous_url`,
`cursor_next_url` context entries. A window has no exact total. Templates opting into
this collection mode must avoid `result.total`; default offset lists retain their
existing context and Template API 1.
