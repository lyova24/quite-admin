# Development and compatibility

The planned library version is **0.2.0**. See the repository's `CHANGELOG.md` for changes
since 0.1.0. The minor bump includes relationship editors, list filters, stale-edit
protection, the database schema and interface customization. A version update does not
create or publish a release.

## Python support

The supported range is **CPython 3.11–3.15**.
CI runs the complete SQLite test suite for each version, without `continue-on-error`.
Python 3.14.7 and 3.15.2 have also been verified locally.
Free-threaded builds and alternative Python implementations do not have a separate test matrix.

To select an interpreter:

```bash
uv sync --locked --python 3.14
uv run pytest -q

uv sync --locked --python 3.15
uv run pytest -q
```

Use uv 0.13.6 or newer if an older uv installation only offers a Python 3.15 prerelease.
The package keeps Python 3.11 as its minimum supported version.

The [dependency endpoint matrix](dependency-compatibility.md) checks supported lower
bounds and newly resolved versions in addition to the ordinary lockfile. Tests use
`httpx.ASGITransport` and each example's real framework lifespan context. This keeps the
same HTTP/lifecycle coverage across Starlette 0.x and 1.x without depending on different
TestClient HTTP libraries. Pytest treats `DeprecationWarning` as an error; dependency
warnings are not suppressed.

## Run checks

```bash
uv sync --locked
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv build
```

Integration tests exercise SQLite CRUD with synchronous and asynchronous SQL reflection,
synchronous and asynchronous SQLAlchemy/SQLModel, Tortoise and Peewee under FastAPI and Litestar.
They also cover CSRF, mass assignment, read-only fields, XSS escaping, permissions,
rollback, templates, host sessions, composite keys, proxy prefixes, stale edits,
relationship lookups, list filters and permission-filtered diagram metadata.

PostgreSQL 17 and MySQL 8.4 have dedicated [contract jobs](data-safety.md).
Both databases have passed local contract runs.
The lockfile verifies pinned versions; the separate endpoint workflow tests exact runtime
floors and fresh resolutions. See [dependency compatibility](dependency-compatibility.md)
for commands, ranges and artifact interpretation.

## Build the Diplodoc documentation

English in `docs/en` is the primary source; Russian in `docs/ru` is its translation.
Both languages use the same page paths and matching `toc.yaml` navigation.

Requirements: Node.js 24+ and npm 11.5.1+. From the repository root:

```bash
npm ci
npm run docs:build
npm run docs:serve
```

The output is written to `build/docs`.
Open [localhost:8001](http://localhost:8001/): the root URL opens the English version.
Russian is available under `/ru/`.

The build checks translation page coverage, internal links and Diplodoc warnings.
CI builds both languages and uploads the HTML as an artifact.
Run `npm run demo:test` after changing the browser demo or shared scripts; it rebuilds
the fictional seed and checks relationship writes, stale edits, filter conditions,
schema layout and junction expansion.

The separate `pages` workflow publishes the generated `build/docs` directory from `master`
using GitHub Pages Actions. In repository Settings → Pages, select **GitHub Actions** as the source.
Do not select the repository root or source `docs` folder for a Jekyll build: Liquid treats Jinja
examples such as `{% extends %}` as its own tags. The generated artifact contains `.nojekyll`
and retains Diplodoc's `_bundle` assets.
Configuration lives in `docs/.yfm`; `package-lock.json` pins the CLI and its dependencies.
Add new pages to both language directories and both navigation files, and keep API
examples synchronized between translations.

## Current limitations

This is the first working library release. File uploads, bulk actions, an audit log
and a row-level permission API are not implemented. See [relationships](relationships.md)
for supported editors and their limits.
Built-in edit forms detect stale records atomically; custom adapters opt in through
`CheckedAdapter`. See [concurrent edits](configuration.md#concurrent-edits).
Custom pages currently support GET only.

Reflection cannot recover logical types lost in the SQL schema: a SQLite UUID may be
a string, and an enum may be an ordinary VARCHAR. Use an ORM adapter to preserve model types.
Auto-discovery requires imported model classes; it does not import the entire application.
