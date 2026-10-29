# Architecture

```text
FastAPI mount ───┐
                ├── Admin ASGI / Starlette ── Jinja2 UI and custom pages
Litestar mount ─┘              │
                    Authentication / CSRF / permissions
                              │
                    ModelSchema / Field / Query
                              │
                       Adapter protocol
                    ┌────┬────┬─────┬────┐
               SQL Core  ORM  Tortoise  Peewee  Custom repositories
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
- `RecordPage`: scalar mappings and a total count.
- `Adapter`: discovery, introspection and five CRUD operations.
- `AuthBackend`: credential verification and identity revalidation.

A model descriptor can be an ORM class, SQL table or external repository descriptor.
The core imports no ORM; unused adapters do not add installation requirements.

## A write request

1. Validate the signed session and revalidate the identity through the authentication backend.
2. Authorize the collection operation.
3. Bound the body size, parse form data, reject duplicates and validate CSRF.
4. Build the server-side writable-field allowlist and reject unknown, hidden or read-only fields.
5. Convert form strings to scalar types and return validation errors to the form.
6. Run the adapter operation in its own transaction.
7. Roll back constraint failures and return `409`; redirect after a successful POST.

The session identifies a subject. The backend supplies current roles and account status
for each protected request. Record keys are URL-safe base64-encoded JSON arrays and
are parsed back into typed key values. This supports UUIDs, composite keys and strings
containing slashes. Encoding does not replace authorization.

## Concurrency and lifecycle

Synchronous SQLAlchemy and Peewee operations run entirely in `anyio.to_thread.run_sync`.
Sessions and connections open and close in the same worker thread.
SQLAlchemy `AsyncSession.run_sync` bridges the ORM operation while database I/O stays
asynchronous. Tortoise uses its native asynchronous API.

The host owns engines, pools, migrations and lifespan.
Model discovery runs after startup, which matters for Tortoise raw foreign-key fields.
Reflection caches metadata and replaces it atomically on `refresh()`.
The dashboard does not execute `COUNT(*)` for every collection; record queries start
when opening a list.

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
