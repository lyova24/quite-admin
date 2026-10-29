# quite-admin

**Version: 0.2.0** · [Changelog](CHANGELOG.md)

An embeddable, ORM-independent admin for **FastAPI** and **Litestar**.
Supports **CPython 3.11–3.15**. MIT licensed.

[English documentation](docs/en/index.md) · [Документация на русском](docs/ru/index.md)

Collections, fields and forms are discovered from existing SQL tables or ORM models.
No additional Pydantic schemas, DTOs or `ModelAdmin` classes are required.

- Authenticated CRUD, search, sorting and pagination.
- Inline one-to-one, one-to-many and many-to-many relationship editing with atomic saves.
- Editable, read-only and hidden fields, with server-side enforcement.
- SQL reflection without model imports.
- SQLAlchemy / SQLModel, Tortoise and Peewee adapters; an adapter protocol for other data sources.
- Custom pages and Jinja2 template overrides.
- English/Russian UI, configurable colors, admin name and description.
- Application-owned logging with stdlib, structlog, Loguru and Litestar backends.
- FastAPI and Litestar mounting, including nested paths and reverse-proxy prefixes.

## Run the demo

From this source checkout:

```bash
uv sync --locked --python 3.15
QUITE_ADMIN_PASSWORD='local-demo-only' uv run uvicorn examples.fastapi_app:app --reload
```

Open [localhost:8000/admin/](http://localhost:8000/admin/) and sign in with
`admin` / `local-demo-only`. For Litestar, use `examples.litestar_app:app` instead.
The demo seeds a local SQLite database. Its HTTP cookie settings are intended for local development.
Use uv 0.13.6 or newer to download a stable Python 3.15 interpreter.

## Documentation

The documentation uses [Diplodoc](https://diplodoc.com/), with **English as the default**
and a complete **Russian** translation. Source pages and navigation live in `docs/en`
and `docs/ru`; configuration lives in `docs/.yfm`.

```bash
npm ci
npm run docs:build
npm run docs:serve
```

Requires Node.js 24+ and npm 11.5.1+. Open [localhost:8001](http://localhost:8001/)
for English or [localhost:8001/ru/](http://localhost:8001/ru/) for Russian.
The static HTML output is written to `build/docs`.
CI checks both translations, builds the site and uploads it as an artifact.

See [integration](docs/en/integration.md), [field configuration](docs/en/configuration.md),
[relationships](docs/en/relationships.md),
[language and appearance](docs/en/customization.md),
[authentication](docs/en/authentication.md), [custom pages](docs/en/custom-pages.md),
[logging](docs/en/logging.md),
[architecture](docs/en/architecture.md) and [development](docs/en/development.md).

## Checks

```bash
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv build
```

CI tests CPython 3.11, 3.12, 3.13, 3.14 and 3.15 with the pinned dependencies.
Integration tests currently use SQLite. SQL reflection executes database rules and triggers;
Python ORM hooks require an ORM or application-service adapter.
See [current limitations](docs/en/development.md#current-limitations) before choosing an integration mode.
