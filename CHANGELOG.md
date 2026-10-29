# Changelog

## 0.2.0 — Unreleased

### Added

- Interactive metadata-only database schema with automatic layout, field-level links,
  expandable table cards, labeled 1:1 / 1:N / M:N relationships, junction expansion,
  table-selection sidebar (all registered tables selected initially), pan/zoom and keyboard
  controls. Respects collection/field permissions, includes physical SQLAlchemy foreign
  keys and ships in the EN/RU browser demo. Optional relation/junction metadata preserves
  adapter API version 1.

- Compact condition-based list filters: searchable field menu, editable chips and a
  single popover for operator/value selection and related-record search. Numeric/date
  filters default to exact equality, with explicit comparisons and inclusive ranges.
  Filter values retain Decimal precision; existing URLs and no-script forms remain supported.

- Dedicated EN/RU interface customization guide covering theme colors, stylesheet loading,
  density tokens, template overrides, accessibility and security boundaries.

- List filters for booleans/enums, exact text, inclusive numeric/date ranges and SQL NULL.
  Active filter chips survive search, sorting and pagination. `ModelOptions.filter_fields`
  controls scalar filters; hidden fields are rejected. Related-record filters support 1:1,
  1:N and M:N with permission-checked search and database-side counts before pagination.
- Optional `Query.related` / `RelatedFilter` with explicit adapter capability advertisement;
  built-in adapters support it without changing required adapter API version 1.

- Searchable relationship pickers with server-side pagination, independent selected chips,
  accessible checkbox choices and no candidate limit. Selected membership remains bounded
  to 1000 per form. A narrow per-page CSP hash allows only the integrity-checked built-in
  script; other pages retain `script-src 'none'`.

- Atomic stale-edit detection for built-in adapters. Forms carry a signed revision;
  competing saves return HTTP 409 with the entered values preserved and a reload link.
  Optional `CheckedAdapter` / `WriteGuard` lets application services enforce the same rule.

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

- Custom edit-form overrides and HTTP clients must echo the hidden `__revision` value
  when using built-in adapters. Create, delete and action requests are unchanged.
  See the EN/RU configuration and adapter guides for migration and optional support.

- Shared neutral interface tokens, clearer typography and borders, compact numeric-aligned
  tables, explicit active search/sort states and quieter row delete links. Selecting a new
  sort column starts ascending; clearing search preserves sorting and page size.
- Record forms group writable, JSON, read-only and relationship fields, keep save/cancel
  visible while scrolling and connect built-in hints/errors to controls for assistive technology.
  Overview, login, confirmation, reports and the standalone demo use the same visual system.
  Custom form overrides can adopt `.form-section`; see EN/RU appearance documentation.

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
