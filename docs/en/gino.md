# GINO

`GinoAdapter` supports existing **GINO 1.0.x** models on PostgreSQL with asyncpg.
No extra admin models or SQLAlchemy ORM mappings are required. Both FastAPI and
Litestar use the same adapter.

## Install

The package is not published yet; install the source checkout as in the [quick start](quickstart.md).

```bash
pip install '/path/to/quite-admin[gino-legacy,fastapi]'
# Or: pip install '/path/to/quite-admin[gino-legacy,litestar]'
```

GINO 1.x requires SQLAlchemy 1.3, while the SQL reflection and SQLAlchemy adapters
require SQLAlchemy 2.x. Use the `gino-legacy` extra instead of `sqlalchemy` or `all` in a
GINO application. The existing `all` extra retains the modern adapter dependency set
and does not include GINO. See the upstream [GINO compatibility notes](https://python-gino.org/docs/en/1.0/how-to/faq.html).

The unreleased `quite-admin[gino]` installation name has been replaced by
`quite-admin[gino-legacy]`; the Python import `quite_admin.adapters.gino.GinoAdapter`
is unchanged. Released GINO requires the legacy SQLAlchemy stack. Modern SQLAlchemy
models use the [SQLAlchemy adapter](integration.md), not this GINO adapter.

## Connect existing models

```python
import os
from quite_admin import Admin, ModelOptions, PasswordAuth
from quite_admin.adapters.gino import GinoAdapter
from myapp.database import db
from myapp.models import User, Order  # Import models before discovery.

adapter = GinoAdapter(db)
# To restrict exposure: GinoAdapter(db, models=[User, Order])
admin = Admin(
    auth=PasswordAuth({"admin": os.environ["ADMIN_PASSWORD_HASH"]}),
    secret_key=os.environ["ADMIN_SESSION_SECRET"],
    adapters=[adapter],
)
admin.configure("users", options=ModelOptions(exclude=("password_hash",)))
admin.mount_fastapi(app)
# Or: admin.mount_litestar(app)
```

`db` is the application's existing `gino.Gino` instance. Discovery includes imported
concrete subclasses of its `db.Model`, including subclasses of abstract project bases.
It never scans models belonging to another instance. Omit `models` for automatic
discovery; `models=[]` explicitly exposes nothing. Every exposed model needs a primary key.
Model attribute names, including attributes mapped to differently named database columns,
are used in field configuration and record dictionaries.

The host must open and close its pool in its own lifespan. Keep an existing lifespan;
for a new FastAPI application, the pattern is:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def database_lifespan(app):
    async with db.with_bind(os.environ["DATABASE_URL"]):
        yield

app = FastAPI(lifespan=database_lifespan)
admin.mount_fastapi(app)
```

For Litestar, use `Litestar(lifespan=[database_lifespan])` and mount the admin on it.
Import `quite_admin.adapters.gino` before opening the pool. It registers GINO's own
asyncpg dialect through SQLAlchemy's public registry, avoiding SQLAlchemy 1.3's legacy
entry-point loader dependency on `pkg_resources`. The adapter never opens a pool,
creates tables, runs migrations or closes the application's engine.

## Queries, writes and relationships

CRUD, literal text search, stable pagination, sorting, typed filters and scalar projections
share the [adapter contract](custom-adapters.md). Complete composite keys, UUID, Decimal,
enum, date/time, JSON/JSONB and 64-bit integers are supported. Computed columns are read-only.

Foreign-key metadata discovers forward/reverse 1:N and unique-FK 1:1 relationships.
Pure junction tables with two foreign-key constraints and a unique combined identity
also expose M:N editors. Composite foreign keys are supported. Relationship names follow
the SQL reflection convention; inspect `adapter.relations(Model)` for generated names.
Only discovered model targets are exposed. Junctions with extra payload columns do not
become M:N editors; edit the junction model explicitly instead. Loader properties and
Python-only relationships cannot be inferred without database foreign keys.

Every write owns an independent transaction and rolls back on any error. Scalar and
relationship changes save atomically; required links cannot be detached, target rows
are never deleted by detachment, and constraint failures become `Conflict`. Reads acquire
and release a connection without committing a write transaction. A host's surrounding
transaction is neither reused nor committed by the adapter.

Record create/update/delete calls native GINO persistence methods. Python column defaults,
database constraints, triggers and database cascades apply. GINO has no SQLAlchemy ORM
session, so SQLAlchemy ORM events do not run. M:N junction changes execute SQL directly.
Application services, custom loaders, JSON properties and soft-delete policies are not
automatically discovered. Use [DelegatingAdapter and lifecycle hooks](extensions.md) for
service-owned writes; implement an atomic `save_relations` explicitly when needed.

GINO 1.0.1 expects PostgreSQL UUID columns declared with `UUID()` (the default
`as_uuid=False`). asyncpg already returns Python UUID values. Declaring
`UUID(as_uuid=True)` triggers an upstream SQLAlchemy 1.3 double-conversion error;
the adapter does not patch the host's column types or driver codecs.

The adapter also supports [related-record filters](filters.md),
[atomic stale-edit detection](configuration.md#concurrent-edits) and
[database schema metadata](database-schema.md).

## Run the PostgreSQL checks

GINO has a separate locked environment and PostgreSQL CI job for CPython 3.11–3.15.
The normal SQLite suite does not install GINO alongside SQLAlchemy 2.x.

```bash
UV_PROJECT_ENVIRONMENT=.venv-gino-legacy uv sync --locked --no-dev --extra gino-legacy --group gino-check
QUITE_ADMIN_GINO_TEST_DATABASE_URL='postgresql://quite_admin:local-test-password@127.0.0.1:55432/quite_admin_gino_test' \
  UV_PROJECT_ENVIRONMENT=.venv-gino-legacy uv run --no-sync pytest --confcutdir=tests/gino tests/gino -q
```

Use a **disposable** local database named `quite_admin_gino_test` (or `quite_admin_test`).
Each test creates and drops an isolated schema. The fixture rejects other database names
and non-local hosts. Contract tests are shared with the modern adapters; additional checks
cover PostgreSQL types, composite links, native hooks, cascades and host-transaction isolation.
