# Architecture

```text
FastAPI mount ───┐
                ├── Admin ASGI / Starlette ── Jinja2 UI / interactive components
Litestar mount ─┘              │
                    Authentication / CSRF / permissions
                              │
                    ModelSchema / Field / Query
                              │
                       Adapter protocol
                              │
               SQL Core / SQLAlchemy / Tortoise / Peewee / GINO / services
```

## Two access modes

Python ORMs do not share an introspection or persistence API.
SQL reflection discovers physical tables independently of the host ORM, but the database
does not retain Python defaults, Enum classes, model validators or application-service rules.
Reflection and ORM adapters are therefore explicit alternatives.

`SQLAdapter` uses SQLAlchemy as a SQL toolkit. `SQLAlchemyAdapter` uses ORM sessions
and ORM persistence. For soft deletion, tenant isolation and application invariants,
implement an adapter around your application service.

## Contracts

- `ModelSchema`: collection name, scalar fields and one or more primary keys.
- `Field`: type, nullable/default/generated/read-only flags, choices and foreign-key metadata.
- `ModelOptions`: ORM-independent display and write policy.
- `Query`: validated pagination, sorting, text search, typed filters and scalar projection.
- `RelatedFilter`: typed target-key membership; adapter support is optional.
- `Relation`, `Junction`: relationship and junction metadata for editors and the diagram.
- `CheckedAdapter`, `WriteGuard`: optional atomic stale-edit preconditions.
- `RecordPage`: scalar mappings and a total count.
- `Adapter`: discovery, introspection and five CRUD operations.
- `AuthBackend`: credential verification and identity revalidation.

A model descriptor can be an ORM class, SQL table or external repository descriptor.
The core imports no ORM; unused adapters do not add installation requirements.
The required adapter API remains version 1; new capabilities are optional.

## A write request

1. Validate the signed session and revalidate the identity through the authentication backend.
2. Authorize the collection operation.
3. Bound the body size, parse form data, reject duplicates and validate CSRF.
4. Build the server-side writable-field allowlist and reject unknown, hidden or read-only fields.
5. Convert form strings to scalar types and return validation errors to the form.
6. Validate the signed form revision. Call the optional before-write hook, then run the adapter
   operation in its own transaction with atomic record and edited-relationship preconditions.
7. Roll back conflicts and return `409`. After commit, notify the after-write hook and redirect.
   Stale forms retain entered values. See [operations and extensions](extensions.md) and
   [concurrent edits](configuration.md#concurrent-edits).

The session identifies a subject. The backend supplies current roles and account status
for each protected request. Record keys are URL-safe base64-encoded JSON arrays and
are parsed back into typed key values. This supports UUIDs, composite keys and strings
containing slashes. Encoding does not replace authorization.

## Concurrency and lifecycle

Synchronous SQLAlchemy and Peewee operations run entirely in `anyio.to_thread.run_sync`.
Sessions and connections open and close in the same worker thread.
SQLAlchemy `AsyncSession.run_sync` bridges the ORM operation while database I/O stays
asynchronous. Tortoise and GINO use their native asynchronous APIs. GINO 1.x uses a
separate SQLAlchemy 1.3 environment and is not installed alongside SQLAlchemy 2.x adapters.

The host owns engines, pools, migrations and lifespan.
Model discovery runs after startup, which matters for Tortoise raw foreign-key fields.
Reflection caches metadata and replaces it atomically on `refresh()`.
The dashboard does not execute `COUNT(*)` for every collection; record queries start
when opening a list.

## Interactive screens

[List filters](filters.md) build a validated `Query`; adapters apply conditions before
counting and pagination. Relationship selection loads 25 candidates per page and repeats
permission checks on each request. The [database schema](database-schema.md) reads only
metadata for permitted collections and fields; record values never enter the graph.

HTML is rendered on the server. Built-in filters, relationship pickers and the schema use
local scripts with SRI and exact page-specific CSP hashes. Custom pages retain
`script-src 'none'`.

## Extension boundaries

- Data access: implement `Adapter`.
- Identity: implement `AuthBackend`.
- Collections and fields: use `ModelOptions`, `FieldOptions`, `register()` and `configure()`.
- Layout and forms: override Jinja templates in your template directory.
- Additional screens: register `Page` with a context callback and permission.

Current permissions apply to entire collections; row filtering belongs in the adapter.
GET requests never mutate records. Deletion requires POST after a confirmation screen.

## Framework integration

FastAPI uses [ASGI sub-application mounting](https://fastapi.tiangolo.com/advanced/sub-applications/).
Litestar uses [ASGI mount handlers](https://docs.litestar.dev/main/usage/routing/overview.html#mounting-asgi-apps).
The wrapper converts Litestar's relative, normalized paths into Starlette's `path/root_path`.
Tests cover nested routers and reverse-proxy prefixes.

SQLAlchemy provides [runtime inspection](https://docs.sqlalchemy.org/en/20/orm/mapping_api.html)
and [MetaData reflection](https://docs.sqlalchemy.org/en/20/core/reflection.html).
Tortoise exposes [model metadata](https://tortoise.github.io/models.html), and Peewee exposes
[Model._meta](https://docs.peewee-orm.com/en/latest/peewee/models.html).

PostgreSQL/MySQL and the isolated GINO environment are covered in the
[compatibility matrix](data-safety.md).
