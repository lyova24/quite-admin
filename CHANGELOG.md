# Changelog

## 0.2.0 — Unreleased

### Added

- A native GINO 1.0.x / PostgreSQL adapter with automatic model discovery, CRUD,
  typed queries, composite keys and atomic 1:1, 1:N and pure-junction M:N editing.
  The isolated `gino-legacy` extra preserves SQLAlchemy 1.3 compatibility; `all` keeps
  its existing SQLAlchemy 2.x dependencies. Includes shared contracts and EN/RU setup guides.
  The initial unreleased `gino` extra is replaced by `gino-legacy`; the adapter import is unchanged.
- Optional SQL reflection type overrides for ambiguous physical types such as MySQL
  `TINYINT(1)` booleans; ordinary integer columns retain their full numeric values.
- A standalone EN/RU browser demo, exported from fictional example metadata, with
  local CRUD/relationship changes and a reset button in the documentation-site artifact.
- Dependency vulnerability checks, validated draft releases with changelog, and tokenless PyPI publishing after maintainer publication.
- Existing-application quick starts, screenshots, a short interface video and compatibility evidence.
- Public write lifecycle hooks and request-scoped operation context for application services.
- Custom field parsers/formatters/templates and permission-checked POST record actions.
- Typed adapter filters, scalar projections and a shared relationship-query contract.
- `ADAPTER_API_VERSION` and `DelegatingAdapter` for application-service write policies.
- Inline one-to-one, one-to-many and many-to-many editors across SQL reflection,
  SQLAlchemy, Tortoise and Peewee. Scalar and relationship changes save atomically.
- Demo data for each relationship kind.
- Custom local logos and concise dashboard, list and login screens.
- Linked breadcrumbs, including reverse-proxy and nested mount prefixes.
- Clickable record rows with a separate delete confirmation action.

### Changed

- Common credential fields are hidden and service/privilege fields are read-only by default.
  Use explicit `expose_sensitive_fields` / `writable_protected_fields` exceptions when required.
- Records use one page for viewing and editing. Read-only users see the same page
  without writable controls. Existing `/edit` URLs redirect to the record URL.
- Template overrides must use `form.html` for the record page; the separate
  `detail.html` template has been removed. See the EN/RU configuration documentation.

### Fixed

- Peewee's MySQL contract fixtures use current PyMySQL connection parameter names
  instead of deprecated `db` / `passwd` aliases; deprecation warnings remain errors.
- SQL relationship discovery recognizes full unique indexes, including MySQL's
  reflected one-to-one foreign keys, without treating partial indexes as globally unique.
- High-severity documentation-tool dependency advisories, with a tested Node 24
  compatibility adapter for patched markdown-it. Remaining moderate findings stay visible.
- Adapter queries validate scalar field names and pagination, writes reject unknown attributes,
  and record operations require complete primary keys. Reads do not commit write transactions.
- Finite Decimal values retain precision without a float conversion.
- Hidden primary-key values are omitted from generated record labels.
- The Litestar queue logging test connects its configured console sink on Python 3.11.
- Documentation deployment publishes generated Diplodoc HTML through GitHub Pages
  Actions instead of passing Jinja examples to Jekyll/Liquid.

## 0.1.0

Initial recorded version: authenticated CRUD, adapter discovery, field policies,
custom pages, English/Russian customization, application-owned logging and
CPython 3.11–3.15 support for FastAPI and Litestar.
