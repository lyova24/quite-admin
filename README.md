# quite-admin

**Version: 0.2.0** · [Changelog](CHANGELOG.md)

An embeddable, ORM-independent admin for **FastAPI** and **Litestar**.
Supports **CPython 3.11–3.15**. MIT licensed.

[English documentation](docs/en/index.md) · [Документация на русском](docs/ru/index.md)

[Add to an existing app in two minutes](docs/en/quickstart.md)

![quite-admin record list](docs/assets/screenshots/products.png)

[12-second walkthrough (MP4)](docs/assets/walkthrough.mp4)

Collections, fields and forms are discovered from existing SQL tables or ORM models.
No additional Pydantic schemas, DTOs or `ModelAdmin` classes are required.

- Authenticated CRUD, search, sorting and pagination.
- Inline one-to-one, one-to-many and many-to-many relationship editing with atomic saves.
- Editable, read-only and hidden fields, with server-side enforcement.
- SQL reflection without model imports.
- SQLAlchemy / SQLModel, Tortoise and Peewee adapters; an adapter protocol for other data sources.
- Typed adapter filters/projections and delegation to application services for writes.
- Custom pages and Jinja2 template overrides.
- Write lifecycle hooks, custom field controls and permission-checked record actions.
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

## Choosing an admin

| Project | When its documented approach fits |
|---|---|
| quite-admin | Automatic SQL table/model discovery, FastAPI/Litestar mounts, Peewee/Tortoise/SQLAlchemy or application-service adapters. Early 0.2.0 development; check the compatibility evidence and limits. |
| [SQLAdmin](https://github.com/smithyhq/sqladmin) | A SQLAlchemy/SQLModel application using its model views, sync/async engines and WTForms controls with FastAPI/Starlette. |
| [Starlette Admin](https://github.com/jowilf/starlette-admin) | Its contrib backend/model-view approach, MongoDB integrations, bulk actions, file handling or import/export fit the application. |

The choices follow each project's documented integration boundaries. SQL reflection
does not execute Python ORM hooks; select a native/service adapter when those rules matter.

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
The full test suite uses SQLite; PostgreSQL 17 and MySQL 8.4 have dedicated contract jobs.
PostgreSQL also passed locally; the local MySQL run is pending image availability.
See the [compatibility matrix](docs/en/data-safety.md) for evidence and limits.
SQL reflection executes database rules and triggers;
Python ORM hooks require an ORM or application-service adapter.
See [current limitations](docs/en/development.md#current-limitations) before choosing an integration mode.
