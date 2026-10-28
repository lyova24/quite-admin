# Quick start

Supported interpreters are CPython 3.11, 3.12, 3.13, 3.14 and 3.15.
Use uv to run the examples from a source checkout.

## Run the FastAPI demo

From the repository directory:

```bash
cd quite-admin
uv sync --locked
QUITE_ADMIN_PASSWORD='local-demo-only' uv run uvicorn examples.fastapi_app:app --reload
```

Open [localhost:8000/admin/](http://localhost:8000/admin/).
Sign in as `admin` with the password `local-demo-only`.

The demo creates a local SQLite database with sample data and permits cookies over HTTP.
Its session secret changes on restart unless `QUITE_ADMIN_SECRET` is set.
Use a persistent random secret and HTTPS when embedding the admin in a deployed application.

## Run the Litestar demo

```bash
QUITE_ADMIN_PASSWORD='local-demo-only' uv run uvicorn examples.litestar_app:app --reload
```

Both examples use the same models, field settings and custom report page.
The application owns database startup and shutdown.

## Install for your application

Install from the source checkout with the extras you need:

```bash
pip install -e '.[sqlalchemy,fastapi]'
# Or: pip install -e '.[tortoise,litestar]'
```

Then choose [SQL reflection or an ORM adapter](integration.md).
Install the appropriate database driver if your ORM does not already depend on it.
The Python package does not require Node.js; Node.js is only needed to build this documentation.

## Python 3.14 and 3.15

```bash
uv sync --locked --python 3.14
uv sync --locked --python 3.15
```

Use uv 0.13.6 or newer for an up-to-date stable Python download catalog.
The complete test suite runs on regular CPython builds; free-threaded builds are not tested separately.
