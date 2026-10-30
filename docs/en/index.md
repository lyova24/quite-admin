# quite-admin

An embeddable admin for **FastAPI** and **Litestar**, supporting **CPython 3.11–3.15**.
Collections, fields and forms come from your existing SQL tables or ORM models.
No additional Pydantic models, DTOs or `ModelAdmin` classes are required. MIT licensed.

[Русский](../ru/index.md) · [Quick start](quickstart.md) · [Browser demo](browser-demo.md)

[![Record list with active filters](../assets/screenshots/products.png)](../assets/screenshots/products.png)

## Start here

| Task | Guide |
|---|---|
| Connect your application | [Quick start](quickstart.md), then [integration and adapters](integration.md) |
| Try the interface without running Python | [Browser demo](browser-demo.md), `admin` / `admin` |
| Choose columns, fields and permissions | [Collections and fields](configuration.md), [authentication](authentication.md) |
| Adapt colors, density and templates | [Interface customization](styling.md) |
| Check supported databases and limits | [Data access and compatibility](data-safety.md) |

## Work with data

- Browse, create, edit and delete records on one record page.
- Search, sort and paginate lists. [Add typed filters](filters.md) for field values,
  ranges, SQL NULL or a linked record; edit conditions through active chips.
- [Edit relationships](relationships.md) with searchable, paginated selectors. Scalar
  fields and selected relationships save atomically.
- [Detect concurrent edits](configuration.md#concurrent-edits): stale forms return 409,
  preserving entered values for review before reloading.
- Explore the [database schema](database-schema.md): automatic layout, compact key fields,
  expandable cards, labeled relationships and M:N junction tables. Choose visible tables
  in the sidebar; moving any table fixes all visible positions until **Auto layout**.

[![Interactive database schema with an expanded M:N junction](../assets/screenshots/database-schema.png)](../assets/screenshots/database-schema.png)

## Choose a data source

| Mode | Schema source | Use it when |
|---|---|---|
| SQL reflection | Database tables and columns | Your application uses any SQL ORM, or no ORM; model imports are unnecessary |
| ORM adapter | Existing ORM classes | You need Python defaults, model types and ORM persistence hooks |
| Application-service adapter | Your own repository or service contract | Writes must follow application-specific business rules |

Built-in adapters cover SQLAlchemy 2.x / SQLModel, Tortoise ORM, Peewee and
[GINO 1.0.x / PostgreSQL](gino.md). GINO uses the separate `gino-legacy` extra with
SQLAlchemy 1.3. The [adapter protocol](custom-adapters.md) supports other data sources.
An independent core and SQL reflection provide SQL access without assuming an arbitrary
Python ORM API.

## Configure the interface

[Collection and field settings](configuration.md) control labels, visible/read-only
fields and available operations. [Authentication and permissions](authentication.md)
remain enforced on the server, together with CSRF and field validation.

Use English or Russian, configure the [identity and palette](customization.md), or adjust
[typography, density and templates](styling.md). Add [custom pages](custom-pages.md),
[field controls, write hooks and record actions](extensions.md) when the application needs them.

## Compatibility and development

Version **0.2.0** is the current unreleased development version. Check
[compatibility evidence and limits](data-safety.md), [development](development.md) and
[release policy](releases.md) before adopting it.

| Project | Suitable integration |
|---|---|
| quite-admin | Automatic SQL/schema discovery, FastAPI/Litestar, Peewee/GINO or mixed/service adapters; early development with explicit compatibility limits |
| [SQLAdmin](https://github.com/smithyhq/sqladmin) | SQLAlchemy/SQLModel views, sync/async engines and WTForms with FastAPI/Starlette |
| [Starlette Admin](https://github.com/jowilf/starlette-admin) | Contrib model views, MongoDB backends, bulk actions, files and import/export |

These choices follow the documented integration approaches. The
[ORM/database matrix](data-safety.md) distinguishes verified paths from unverified combinations.
