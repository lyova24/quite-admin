# Your first admin

Run a real FastAPI application with three related SQLAlchemy models:
**Customers → Orders → Order items**. You can sign in, change records, edit relationships
and inspect the saved changes. Everything runs locally with fictional data in SQLite.

Already have an application? [Connect your existing models](quickstart.md) instead.
To explore the interface first, [open the browser demo](https://lyova24.github.io/quite-admin/demo/)
with `admin` / `admin`.

## Download and run

You need CPython **3.11–3.15** and either [uv](https://docs.astral.sh/uv/getting-started/installation/)
or pip. Download the single [quickstart.py file](https://raw.githubusercontent.com/lyova24/quite-admin/master/examples/quickstart.py)
into an empty directory. You do not need to clone the repository or install Node.js.

With uv, the script's dependency header installs quite-admin, FastAPI, SQLAlchemy and Uvicorn
into an isolated environment:

```bash
curl -fsSLo quickstart.py https://raw.githubusercontent.com/lyova24/quite-admin/master/examples/quickstart.py
QUITE_ADMIN_PASSWORD='local-demo-only' uv run --script quickstart.py
```

Alternatively, activate your Python virtual environment and use pip:

```bash
pip install 'quite-admin[sqlalchemy,fastapi]>=0.8.17,<0.9' 'uvicorn>=0.30,<1'
QUITE_ADMIN_PASSWORD='local-demo-only' python quickstart.py
```

Open [localhost:8000/admin/](http://localhost:8000/admin/). Sign in as **admin** with
the password **local-demo-only**. The server listens on `127.0.0.1`.

## Try a complete workflow

1. Open **Orders**, then **Starter order**. Change **Status** from `pending` to `paid` and save.
2. Open the order again. In the **Customer** relationship editor, select **Sam Lee** and save.
3. Open **Order Items → Notebook**. Change **Quantity** from `2` to `3` and save.
4. Open **Activity history**. Expand your changes to see the user and the before/after values.
5. Open **Customers**, create a customer, edit it, then delete it through the confirmation page.
6. Open **Database schema** to see the same three models and their relationships.

Your changes survive a server restart. The initial records are inserted only when the
Customers table is empty. Use disposable customer records for the create/delete exercise;
the seeded customers and orders are linked by database foreign keys.
The example allows orders without a customer, so that relationship is nullable.
The current adapter rejects replacing a non-nullable relationship; choose a nullable
relationship when following the customer reassignment exercise.

## How the models become an admin

The [complete source](https://github.com/lyova24/quite-admin/blob/master/examples/quickstart.py)
contains ordinary SQLAlchemy models and a FastAPI lifespan that initializes the sample database.
This is the admin setup inside `create_app()`:

```python
admin = Admin(
    title="Orders back office",
    auth=PasswordAuth.single_user("admin", password),
    secret_key=os.getenv("QUITE_ADMIN_SECRET", secrets.token_urlsafe(48)),
    adapters=[SQLAlchemyAdapter(sessions, base=Base)],
    storage=data_dir / "history.sqlite3",
    secure_cookies=False,  # This example serves local HTTP only.
)
admin.mount_fastapi(app)
```

`base=Base` discovers all three models. Their column types supply the forms, and
SQLAlchemy relationships supply the related-record editors. No separate admin classes,
DTOs or Pydantic schemas are needed. You can later [configure individual tables
and fields](configuration.md) without replacing your models.

## Local files and sessions

The example writes only to `.quite-admin/quickstart/` beside the downloaded script:

| File | Contents |
| --- | --- |
| `shop.db` | The three model tables and your fictional records |
| `history.sqlite3` | Admin service data and activity history |

Stop the server with Ctrl+C. A new random session secret is generated on each start,
so you will need to sign in again. Set `QUITE_ADMIN_SECRET` to a persistent random value
of at least 32 bytes if you want sessions to survive restarts. To start with fresh data,
stop the server and move the example's `.quite-admin/quickstart/` directory aside.

## Use your own application

[Add quite-admin to your existing app](quickstart.md), using your own base and session factory.
For Litestar, use `admin.mount_litestar(app)`; the models and adapter configuration stay the same.
Other ORMs and SQL reflection are covered in [integrations](integration.md).

This example uses a single local account and HTTP cookies. For a deployed application,
follow the [deployment guide](deployment.md), review [API guarantees](api-stability.md)
and check the [database compatibility matrix](data-safety.md).
