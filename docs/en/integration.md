# Integration and adapters

The admin is an independent ASGI application.
Your host application owns its engines, session factories, startup, shutdown and migrations.

## SQL reflection: no ORM models

```python
import os
from fastapi import FastAPI
from sqlalchemy import create_engine
from quite_admin import Admin, ModelOptions, PasswordAuth
from quite_admin.adapters.sql import SQLAdapter

engine = create_engine(os.environ["DATABASE_URL"])
admin = Admin(
    secret_key=os.environ["ADMIN_SESSION_SECRET"],  # At least 32 random bytes
    auth=PasswordAuth({"admin": os.environ["ADMIN_PASSWORD_HASH"]}),
    adapters=[SQLAdapter(engine, include_tables=("users", "orders"))],
)
admin.configure("users", options=ModelOptions(
    exclude=("password_hash",), readonly_fields=("created_at",),
))

app = FastAPI()
admin.mount_fastapi(app, "/admin")
```

Without `include_tables`, all tables in the selected database schema are discovered.
Use `exclude_tables` to omit internal tables. Every exposed table must have a primary key.
`SQLAdapter` accepts an `Engine` or `AsyncEngine`, and an optional `schema` name.

Reflection runs lazily after authentication and caches metadata.
Call `await adapter.refresh()` after a host-managed migration to replace the cached schema.
The library never creates tables or runs migrations itself.

MySQL [stores `BOOLEAN` as `TINYINT(1)`](https://dev.mysql.com/doc/refman/8.4/en/numeric-type-syntax.html).
Reflection cannot distinguish it from an ordinary `TINYINT(1)`, so integer
columns remain integers by default. Supply the intended SQLAlchemy type for ambiguous
columns when needed; this also controls parsing, typed filters and returned values:

```python
from sqlalchemy import Boolean

adapter = SQLAdapter(engine, column_types={"users": {"active": Boolean()}})
```

Use the full table key, such as `app.users`, when selecting a named schema. Overrides
must reference discovered tables and columns and contain SQLAlchemy type instances.
`refresh()` reapplies them. Native ORM adapters retain their declared Boolean types.

{% note warning %}

Reflection executes SQL directly. Database constraints, server defaults and triggers apply.
Python defaults, ORM events, model validators, service-layer permissions and soft-delete
logic do not run automatically. Use an ORM adapter or an application-service adapter
when those rules are required.

{% endnote %}

## Existing SQLAlchemy / SQLModel classes

```python
from sqlalchemy.orm import sessionmaker
from quite_admin import Admin
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from myapp.database import engine, Base

adapter = SQLAlchemyAdapter(sessionmaker(engine), base=Base)
admin = Admin(auth=auth_backend, secret_key=session_secret, adapters=[adapter])
admin.mount_fastapi(app)
```

All imported models in `Base.registry` are discovered automatically.
For SQLModel, pass `base=SQLModel`. No duplicate admin schemas are required.

For asynchronous sessions:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

adapter = SQLAlchemyAdapter(async_sessionmaker(async_engine), base=Base)
```

For a custom callable returning an `AsyncSession`, set `async_mode=True`.
Supply a factory for fresh sessions, not a shared session or a FastAPI dependency generator.
Each operation owns one session. Synchronous operations run in a worker thread.

## Litestar

```python
from litestar import Litestar

app = Litestar(route_handlers=[admin.litestar_route("/admin")])
# For an existing application: admin.mount_litestar(app, "/admin")
```

Nested routers, mount prefixes and ASGI `root_path` behind a reverse proxy are supported.
The admin's session is isolated from the host application's session.

## Tortoise ORM

```python
from quite_admin.adapters.tortoise import TortoiseAdapter

adapter = TortoiseAdapter(apps=("models",))
```

Call `Tortoise.init()` in the host lifespan.
Discovery runs after startup, on the first authenticated request, when raw foreign-key
fields are initialized. Queries use the model's asynchronous database connection.

## Peewee

```python
from quite_admin.adapters.peewee import PeeweeAdapter

adapter = PeeweeAdapter(base=ProjectBaseModel)
# Or: PeeweeAdapter(models=[User, Order])
```

Use file-backed SQLite or a database server. A regular SQLite `:memory:` database
is not shared between worker threads. Each connection and transaction opens and closes
within the same worker thread.

All adapters share the same [collection configuration](configuration.md).
To support another data source, implement the [Adapter protocol](custom-adapters.md).
