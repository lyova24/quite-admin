# quite-admin

An embeddable admin for **FastAPI** and **Litestar**, supporting **CPython 3.11–3.15**.
Collections, fields, forms and CRUD screens come from your existing schema.
No additional Pydantic models, DTOs or `ModelAdmin` classes are required. MIT licensed.

[Русский](../ru/index.md) · [Quick start](quickstart.md)

## Choose a data source

| Mode | Schema source | Use it when |
| --- | --- | --- |
| SQL reflection | Database tables and columns | Your application uses any SQL ORM, or no ORM; model imports are unnecessary |
| ORM adapter | Existing ORM classes | You need Python defaults, model types and ORM persistence hooks |

Built-in adapters cover SQLAlchemy 2.x / SQLModel, Tortoise ORM and Peewee.
The `Adapter` protocol supports other ORMs, document databases and application repositories.
Universal support means an independent core plus reflection for SQL databases;
an arbitrary Python ORM API still needs an adapter.

## Features

- Browse, create, edit and delete records.
- Search, sorting and pagination.
- Hidden fields, read-only fields and operation permissions.
- Authentication, CSRF protection and server-side field validation.
- Custom pages and Jinja2 template overrides.
- English/Russian UI, configurable colors, admin name and description.
- Synchronous and asynchronous SQL access, composite keys, UUID and JSON.

Start with the [demo](quickstart.md) or [integration guide](integration.md).
Configure [language and appearance](customization.md) for your application.
See [development and compatibility](development.md) for the test matrix and current limitations.
