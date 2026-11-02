# Development and compatibility

## Readable implementation

Use explicit constructors for validation and derived defaults. `Field`, `ModelSchema`,
`RecordAction` and `Theme` use ordinary assignments; there are no post-init callbacks or
frozen-object mutations. They remain dataclasses for equality, representation and
`dataclasses.replace()`. They are mutable configuration objects: finish constructing them
before serving requests. Do not mutate registered metadata during requests; use
`Admin.configure()` to replace collection options. Constructor validation does not run on
later attribute assignments. Code that relied on these four objects being hashable or
raising `FrozenInstanceError` must stop doing so. Request operation snapshots, identities,
query objects and write guards keep their existing protections.

Use explicit branches and loops for transaction selection and compound query conditions.
Keep ORM reflection and async boundaries where their contracts require them; avoid
introducing an abstraction solely to save a few lines.

The finalized baseline is **0.5.2** (2026-11-02); subsequent work targets a higher version.
See `CHANGELOG.md` and [public API guarantees](api-stability.md) for migration and
compatibility rules. Run `python scripts/check_api.py --profile modern` before committing;
GINO checks run separately with `--profile gino`. Version updates do not publish a release.

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

The documentation opens in dark mode by default. Settings → Dark theme switches between
dark and light; Diplodoc preserves that choice in the current browser tab's session.
Both palettes are defined in `docs/theme.yaml`: charcoal surfaces and a vivid blue accent
in dark mode, pale neutral surfaces and a darker blue for readable links in light mode.
The native themizer also styles tables, code, notices and article navigation.
`docs/_assets/script/quite-admin-theme.js` supplies the initial mode;
`scripts/prepare-pages.mjs` places it before the content and viewer bundles to avoid a light flash.
The admin application and browser demo keep their own theme configuration.
The build clears `build/docs` first so pages removed from the source do not remain in the published site.

The build checks translation page coverage, internal links and Diplodoc warnings.
CI builds both languages and uploads the HTML as an artifact.
Run `npm run demo:test` after changing the browser demo or shared scripts; it rebuilds
the fictional seed and checks relationship writes, stale edits, filter conditions,
schema layout, junction expansion and form control precision.

The separate `pages` workflow publishes the generated `build/docs` directory from `master`
using GitHub Pages Actions. In repository Settings → Pages, select **GitHub Actions** as the source.
Do not select the repository root or source `docs` folder for a Jekyll build: Liquid treats Jinja
examples such as `{% extends %}` as its own tags. The generated artifact contains `.nojekyll`
and retains Diplodoc's `_bundle` assets.
Configuration lives in `docs/.yfm`; `package-lock.json` pins the CLI and its dependencies.
Add new pages to both language directories and both navigation files, and keep API
examples synchronized between translations.

## Browser and installed-package checks

`npm run browser:test` builds the static demo, starts disposable local servers and
runs the browser suite. Demo preparation finishes before the server-readiness timers
start. CI allows up to 120 seconds for each server to become ready and logs their
startup output and HTTP readiness probes; local runs retain a 30-second limit.
Install the pinned browsers first with `npx playwright install --with-deps`.
The fixture uses only fictional data in a temporary SQLite database. Browser jobs run
Chromium, Firefox and WebKit in CI and retain failure screenshots/traces.

Python matrix jobs test the source checkout without building distributions.
The dedicated `pypi.yml` workflow builds one wheel/sdist pair after a validated GitHub
release, checks Twine and installs both into clean environments. For local packaging
checks, run `uv build`, then `uvx --from 'twine>=6,<7' twine check --strict dist/*` and
`uv run python scripts/check_distributions.py`. Package metadata must remain 2.4.
GitHub release downloads remain source-code archives; see [publishing](releases.md).

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

## Frontend components

The interface uses Jinja templates, plain JavaScript and CSS without a frontend build.
Shared markup lives in `templates/quite_admin/_ui.html` (navigation, branding, CSRF
inputs, empty states and pagination), `_controls.html` (options and accessibility
attributes) and `_fields.html` (record fields). Import these macros with context so
translations, mount-aware URLs, field restrictions and custom field templates keep
working. These partials are internal; the existing template entry points and template
API version remain unchanged.

`forms.js` owns field enhancement and the control factory reused by inline edits and
the browser demo. Repeated enhancement of a live scope keeps one switch/JSON editor
per native control. Keep the cleanup callback when removing a scope: date pickers
release document/window listeners through it. `datetime.js` supplies the common
calendar, precision validation and popover lifecycle for forms and filter drafts.
Do not add dynamic script imports: built-in scripts keep the server's existing CSP
hashes and integrity attributes.

After frontend changes, run `npm run demo:test`, `npm run browser:test` and the Python
integration suite. Browser coverage includes repeated enhancement, exact submitted
JSON values, listener cleanup, hidden draft validation, keyboard operation and
JavaScript-disabled fallbacks.
