# Development and compatibility

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

The dependency range allows Starlette 0.x and 1.x. The lockfile selects Starlette 1.10.0,
whose `TestClient` uses `anyio.from_thread.BlockingPortal` and `httpx2`.
Both HTTP client packages are development dependencies: synchronous example tests use
Starlette's `TestClient`, while asynchronous integration tests use `httpx.ASGITransport`.
Pytest treats `DeprecationWarning` as an error to catch obsolete API use in the tested dependency set.

## Run checks

```bash
uv sync --locked
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv build
```

Integration tests exercise SQLite CRUD with synchronous and asynchronous SQL reflection,
synchronous and asynchronous SQLAlchemy, Tortoise and Peewee under FastAPI and Litestar.
They also cover CSRF, mass assignment, read-only fields, XSS escaping, permissions,
rollback, templates, host sessions, composite keys and proxy prefixes.

PostgreSQL and MySQL use the adapters' appropriate drivers, but currently have no integration
test matrix in this repository. The lockfile verifies the pinned dependency versions;
it is not a test of every version permitted by the dependency ranges.

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
CI builds both languages and uploads the HTML as an artifact. It does not publish a website.
Configuration lives in `docs/.yfm`; `package-lock.json` pins the CLI and its dependencies.
Add new pages to both language directories and both navigation files, and keep API
examples synchronized between translations.

## Current limitations

This is the first working library release. Relation pickers, a many-to-many editor,
file uploads, bulk actions, an audit log and a row-level permission API are not implemented.
Concurrent edits use last-write-wins; there is no UI-level conflict detection.
Custom pages currently support GET only.

Reflection cannot recover logical types lost in the SQL schema: a SQLite UUID may be
a string, and an enum may be an ordinary VARCHAR. Use an ORM adapter to preserve model types.
Auto-discovery requires imported model classes; it does not import the entire application.
