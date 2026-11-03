# quite-admin

[![GitHub release](https://img.shields.io/github/v/release/lyova24/quite-admin?style=for-the-badge&label=release&labelColor=202020&color=3395fd)](https://github.com/lyova24/quite-admin/releases/latest)
[![Tests](https://img.shields.io/github/actions/workflow/status/lyova24/quite-admin/ci.yml?branch=master&event=push&style=for-the-badge&label=tests&labelColor=202020)](https://github.com/lyova24/quite-admin/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/quite-admin?style=for-the-badge&label=PyPI&labelColor=202020&color=3395fd)](https://pypi.org/project/quite-admin/)

![quite-admin — Fast to set up. Simple to use.](https://raw.githubusercontent.com/lyova24/quite-admin/master/.github/social-preview.png)

**Version: 0.6.1** (unreleased) · [Changelog](CHANGELOG.md)

An embeddable admin for **FastAPI** and **Litestar** with native **SQLAlchemy 2.x, SQLModel, Tortoise ORM, Peewee and GINO 1.x** adapters, SQL reflection and a custom adapter API.
Supports **CPython 3.11–3.15**. MIT licensed.

[English documentation](docs/en/index.md) · [Документация на русском](docs/ru/index.md)

[Browser demo](https://lyova24.github.io/quite-admin/demo/) — `admin` / `admin`.
Its fictional records stay in browser storage; **Reset demo** restores the examples.
Try inline edits in **Products**, date/time/JSON controls in **Schedules**, and the
**Activity history** journal. [Interface tour: 0.5.2](docs/en/interface-tour.md).
The site workflow publishes this standalone demo alongside the documentation.

[Add to an existing app in two minutes](docs/en/quickstart.md) · [Public API guarantees](docs/en/api-stability.md)

![quite-admin record list](https://raw.githubusercontent.com/lyova24/quite-admin/master/docs/assets/screenshots/products.png)

[See the current sign-in, forms, calendars and activity journal](docs/en/interface-tour.md).

Collections, fields and forms are discovered from existing SQL tables or ORM models.
No additional Pydantic schemas, DTOs or `ModelAdmin` classes are required.

- CSV/XLSX export with column selection, filters and related-table data.
- Authenticated CRUD, automatic search, sorting and pagination; typed filters for text
  fragments, ranges, sets, dates, NULL and related records with name/exact-ID lookup.
- Count-free cursor pagination for large collections and configurable SQL read deadlines.
- Automatic SQLite service storage, optional SQLite/PostgreSQL/MySQL storage and
  permission-aware [activity history](docs/en/storage.md) with before/after field
  comparisons by user and collection. Recording levels: `changes` (default), `audit`
  and `all`; disable it with `history_enabled=False`.
- Interactive database schema and atomic stale-edit detection.
- Inline one-to-one, one-to-many and many-to-many relationship editing with atomic saves.
- Inline cell editing, nullable boolean switches and grouped collection navigation.
- Editable, read-only and hidden fields, with server-side enforcement.
- SQL reflection without model imports.
- SQLAlchemy / SQLModel, Tortoise, Peewee and GINO 1.x (`gino-legacy` extra) adapters;
  an adapter protocol for other data sources.
- Typed adapter filters/projections and delegation to application services for writes.
- Type-aware forms: TEXT textareas, date/time pickers and JSON/JSONB syntax highlighting.
- Custom pages and Jinja2 template overrides.
- Write lifecycle hooks, custom field controls and permission-checked record actions.
- Form-only inputs, safe password controls and per-model service handlers with optional
  Pydantic form validation; ordinary ORM discovery needs no schemas or handlers.
- English/Russian UI, configurable colors, admin name and description.
- Application-owned logging with stdlib, structlog, Loguru and Litestar backends.
- FastAPI and Litestar mounting, including nested paths and reverse-proxy prefixes.

## Install

```bash
pip install 'quite-admin[sqlalchemy,fastapi]'
# Or: uv add 'quite-admin[sqlalchemy,litestar]'
```

Choose `sqlmodel`, `tortoise`, `peewee` or `gino-legacy` for another adapter.
Use `pip install quite-admin` for the ORM-independent core. Native GINO requires a
separate environment from SQLAlchemy 2.x. [PyPI package](https://pypi.org/project/quite-admin/).

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
| quite-admin | Automatic SQL table/model discovery, FastAPI/Litestar mounts, Peewee/Tortoise/SQLAlchemy or application-service adapters. Version 0.6.1 (unreleased); see the public API guarantees and compatibility evidence. |
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
[GINO 1.x / PostgreSQL](docs/en/gino.md),
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
```

GitHub releases provide source-code ZIP/tar.gz archives. A version tag publishes the
validated GitHub release with its changelog. The separate PyPI workflow builds one
wheel/sdist pair and publishes it through Trusted Publishing; Python test matrix jobs
do not build distributions.

CI tests CPython 3.11, 3.12, 3.13, 3.14 and 3.15 with the pinned dependencies.
The full test suite uses SQLite; PostgreSQL 17 and MySQL 8.4 have dedicated contract jobs.
Separate minimum/latest dependency jobs resolve fresh isolated environments and include
real SQLModel sync/async contracts. PostgreSQL/MySQL jobs run the SQLModel suite too.
See the [compatibility matrix](docs/en/data-safety.md) and
[dependency endpoints](docs/en/dependency-compatibility.md) for evidence, ranges and limits.
SQL reflection executes database rules and triggers;
Python ORM hooks require an ORM or application-service adapter.
See [current limitations](docs/en/development.md#current-limitations) before choosing an integration mode.
