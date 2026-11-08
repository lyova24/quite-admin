# Changelog

## 0.8.7 — 2026-11-08

- Start diagrams with more than 100 permitted tables unselected and explain manual selection. Add schema_auto_limit=True and a configurable schema_table_limit; preserve Show all and allow disabling the initial guard without changing table access.

## 0.8.6 — 2026-11-08

- Use table/tables terminology throughout the English/Russian interface, history filters, schema links and browser demo. Preserve collection-named Python identifiers, URLs, history keys and legacy template translation IDs.

## 0.8.5 — 2026-11-08

- Group Overview tables in collapsed, keyboard-accessible sections using the same labels and permissions as the sidebar. Remove field counts from table cards and mirror the grouping in the browser demo.

## 0.8.4 — 2026-11-08

- Collapse sidebar groups by default while remembering explicit choices and revealing the current table. Keep native keyboard and no-storage behavior in the Python interface and browser demo.

## 0.8.3 — 2026-11-08

- Select CI jobs by changed inputs, separating documentation, Python, JavaScript,
  browser, database, compatibility and dependency audits. Keep a required selective
  `CI ready` gate; require full `Release ready` validation for the exact release SHA,
  with manual full CI available before tagging and the same gate for Pages/PyPI.
- Place bulk actions in a compact icon menu on the right of each table's toolbar,
  matching the filter button. Show the selection count on the icon; support keyboard
  dismissal, mobile layouts and confirmation without JavaScript. Bulk deletion remains
  available by default when the collection's delete permission allows it.
- Add per-table `ModelOptions(bulk_actions=(RecordAction(...),))` for list-only commands,
  using the existing per-record handlers, permissions, hooks and history. Preserve
  `actions` and `RecordAction(bulk=True)` compatibility; reject ambiguous action slugs.
- Add a tested product-deactivation action to the FastAPI/Litestar examples and update
  the English/Russian guides with configuration, confirmation and partial-result behavior.

## 0.8.2 — 2026-11-06

- Clarify the README and English/Russian documentation around existing application models.
  Add a standalone three-model FastAPI example and deployment guides;
  organize navigation by user tasks while preserving existing page paths.
  Use absolute README links and check their portability to PyPI during documentation builds.
- Reuse successful master CI for version-tag releases instead of rerunning the test
  matrix. Require the exact tagged commit and a successful latest validation gate;
  deploy its existing documentation artifact to Pages after the GitHub release
  workflow succeeds, and enforce the same CI check for automatic and manual PyPI uploads.

## 0.8.1 — 2026-11-06

- Wrap long relationship-picker labels within the form at enlarged font sizes.

- Keep list text neutral when hovering a row; highlight only its background.
  Apply the accent color to links to related records only while the link is hovered.

- Scale typography, spacing, controls, icons and layout widths together with `rem`.
  Keep the compact layout through 1600 CSS pixels at the default browser font size,
  then increase smoothly to 150% at 2880 pixels. Preserve browser font preferences,
  horizontal table scrolling, mobile layouts and the schema's independent SVG zoom.
- Add `--ui-font-size`, `--sidebar-width`, `--content-max-width` and
  `--form-max-width` CSS tokens for application overrides.
- Keep inline-edit pencils to the right of cell values at every scale, including
  truncated text and empty values.
- Migration: the root now uses a 16px browser-default base instead of 12px; built-in
  dimensions retain their previous size up to 1600px. Multiply existing custom `rem`
  values by 0.75 to retain their size. Set `--ui-font-size: 100%` to disable automatic
  growth, and use `rem` instead of `px` in custom sizing tokens to follow the UI scale.
- Переход: корневая база теперь соответствует браузерным 16px вместо 12px; встроенные
  размеры сохранены до ширины 1600px. Умножьте свои значения в `rem` на 0.75 для
  прежнего размера. `--ui-font-size: 100%` отключает автоматический рост; размеры
  в пользовательских токенах задавайте в `rem`, чтобы они росли вместе с интерфейсом.

## 0.7.4 — 2026-11-05

- Apply `relation_label` to existing form relationship pickers, including selected
  records and labels restored after validation errors. Search the configured visible
  label alongside the target search fields and exact ID without extra search settings.
- Correct PostgreSQL/Tortoise NULL ordering in cursor pages and isolate browser
  pagination checks from records created by other tests.

## 0.7.3 — 2026-11-05

- Enable scalar column sorting, including dates, in built-in cursor pagination.
  Carry the sort value and complete primary key through signed cursors, keep
  deterministic ties and NULL-last ordering, and reset traversal on sort changes.
  Preserve count-free reads and the primary-key contract of existing custom adapters.

## 0.7.2 — 2026-11-05

- Render foreign-key list cells as permission-aware links to related records,
  using raw IDs by default or a visible target field from `FieldOptions(relation_label=...)`.
  Fetch labels in bounded batches without mutating stored, exported or history values.

## 0.7.1 — 2026-11-05

- Open inline field editors only from the pencil button. Keep cell values on the
  record navigation target and preserve immediate boolean switches.

## 0.7.0 — 2026-11-04

- Automatically attach service-storage cleanup to FastAPI and Litestar lifespans;
  expose `Admin.lifespan()` / `Admin.aclose()` for other integrations. Dispose only
  storage-owned engines and preserve application-owned engines and lifespan state.
- Accept SQLAlchemy engine options directly with a storage URL, including bounded
  pools, without requiring application code to create and dispose a separate engine.
- Redirect the bare FastAPI mount path before a later catch-all route, preserving
  query parameters, parent mounts and reverse-proxy prefixes.

- Keep activity history for 90 days by default (`history_retention_days`); support
  another positive period or `None` for indefinite retention. On admin requests,
  clean one bounded batch per five minutes, including details and unused actors.
- Add `Admin.purge_history()`, the optional `HistoryRetentionStore` capability and
  `python -m quite_admin cleanup-history` for explicit batched maintenance.
- Migration / переход: existing history older than 90 days is now deleted when
  the admin is used. Set `history_retention_days=None` / задайте `None` to preserve
  all events or use an application-managed retention policy. Custom stores need the
  optional purge capability for automatic cleanup; their required API is unchanged.

- Add page-local bulk deletion and opt-in `RecordAction(bulk=True)` using existing
  handlers/hooks. Confirm up to 100 signed, session-bound keys, recheck permissions
  and revisions, then show per-record partial results and record individual history.
  `ModelOptions(bulk_delete=False)` disables the built-in bulk delete command.

- Add optional URL/JSON/multiline value displays with escaped output, safe HTTP(S)
  links, clipboard/manual-copy fallback and no-script disclosure. Build short links
  with `FieldOptions(url_template=...)` without changing stored/exported/history values.
  Keep rich cells synchronized after service-driven inline updates.

## 0.6.1 — 2026-11-04

### Changed

- Add `history_level="changes" | "audit" | "all"` to filter activity before recording
  and when reading existing history, including user lookup and pagination. The default
  is now `changes`: only committed record-write operations are recorded. `audit` adds
  authentication, exports and failed writes; `all` retains the previous full activity
  stream. Set `history_level="all"` to retain 0.6.0 recording behavior. Existing events
  are preserved and the service-storage schema is unchanged.

- Refresh the complete English/Russian documentation for the current release: add an
  Admin constructor reference and complete collection options, document supported
  field-control customization, and correct installation, activity-history and deployment
  guidance. Keep release history and migration instructions in this changelog; remove
  comparisons with other admin projects from user documentation.

## 0.6.0 — 2026-11-03

### Added

- Add model-level `input_fields` for form-only values without changing adapter schemas
  or SQL projections. Include a built-in password widget that never echoes credentials;
  input fields are unavailable in lists, search, filters, exports and activity history.
- Attach creation/editing services and optional Pydantic 2 schemas directly to each
  model's options. Preserve native checked writes for validation-only customization,
  pass guards to custom editing services and accept loaded ORM results without a
  custom adapter or record-conversion helper.
- Configure shared per-admin read concurrency and operation deadlines, including the
  queue, asynchronous pool acquisition, discovery, related reads and exports. Leave
  writes unchanged and wait for database cleanup before reusing a slot. Synchronous
  SQL/ORM workers are not abandoned on cancellation. Preserve safe optional cursor
  reads through DelegatingAdapter without bypassing overridden list policies.

## 0.5.2 — 2026-11-02

### Fixed

- Use the same content padding and maximum width on collection listings as on
  Overview, Database schema and Activity history, including narrow screens.
- Align the sign-in logo beside the title in one row, for both the default mark
  and custom logos. Apply the same layout to the standalone browser demo.

### Changed

- Show the social preview and live GitHub release, CI and PyPI badges in README.
  Give Diplodoc matching dark/light palettes and dark mode on the first visit,
  while retaining its theme switcher and the current tab's selected mode.
- Refresh all documentation screenshots from the 0.5.2 Python example, including
  sign-in, overview, filters, forms, relationships, calendars, history and schema.
  Update the English/Russian interface tour and replace links to the old light-theme
  video with the current tour.
- Use a neutral charcoal dark palette with near-white text and vivid blue accents.
  Replace the default q mark and favicon. Retain the compact controls and sign-in
  card. Add a separate 1280×640 GitHub social
  preview in `.github/social-preview.png` with a clean background and the
  “Fast to set up. Simple to use.” tagline; do not display it in the admin.
- Change the `Theme()` color defaults; existing explicit palettes remain supported.
  To retain the previous appearance, set all previous colors explicitly using the
  migration recipe below. Preserve template API 1 and the original API
  baselines; the API check accepts only the documented old/new color default pairs.

- Build the static demo before browser-server readiness checks. Allow cold CI
  fixtures up to 120 seconds to start, with named, unbuffered server logs and
  HTTP readiness diagnostics; keep the 30-second local limit and all browser tests.

### Migration: retain the 0.5.0 light palette

Pass every color explicitly; custom palettes remain supported:

```python
from quite_admin import Theme

theme = Theme(
    primary="#3e6656",
    background="#f5f6f8",
    surface="#ffffff",
    text="#20252b",
    muted="#626b76",
    border="#dce0e5",
    danger="#b43e3e",
    on_primary="#ffffff",
    on_danger="#ffffff",
)
```

## 0.5.0 — 2026-11-02

### Added

- Library-owned service storage: private, file-backed SQLite by default, optional
  SQLite/PostgreSQL/MySQL URLs and borrowed sync/async SQLAlchemy engines. Automatically
  initialize reserved `quiteadmin_` tables with cross-worker locking, schema-version
  checks, namespace isolation and optimistic revisions for bounded JSON documents.
- Activity history with searchable authenticated users, collection/action/result
  filters, a compact calendar popover with quick UTC presets, single-day/range selection,
  keyboard navigation, cancellation and inclusive UTC boundaries. Reuse the listing
  filter editor and shared chips for history conditions, with the period alongside them,
  and signed count-free pagination. Capture views, writes,
  exports, custom actions and login/logout. Show a dated activity journal with expandable
  field comparisons, persisted before/after values and record links. Add a Journal/Table
  toggle that preserves filters and pagination, with the journal as default. Exclude secrets
  and reapply current field/collection permissions when reading history. Enable history
  by default; `Admin(history_enabled=False, ...)` disables capture and hides the section.
- Upgrade service storage automatically to schema 2, preserving legacy events and
  batching bounded change details. Keep diagnostic logs free of record values.

- Count-free bidirectional keyset pagination on every native adapter and opt-in cursor
  collection lists with signed user/filter-bound cursors. Keep ordinary offset lists
  available for arbitrary sorting and exact totals.
- Configurable read query deadlines for SQL reflection and SQLAlchemy/SQLModel on
  SQLite, PostgreSQL and MySQL, with sanitized 504 responses and connection cleanup.

- Bounded BatchRelationAdapter reads enabled by default on all native adapters. Related exports
  use one joined query per relationship instead of per-record count/load queries;
  related exports require batch support. Remove the per-record fallback; retain all
  permission checks and scalar-only export for adapters without batch support.

### Changed

- Expand the standalone browser demo with editable DATE/DATETIME/TIME, TEXT, JSON and
  nullable booleans, shared inline-edit controls, grouped navigation, cursor-style paging,
  scalar CSV downloads and local activity comparisons with user/date filters and both views.
  Preserve existing local records when adding new demo collections. Add a bilingual 0.5
  interface tour, current screenshots and explicit browser/server coverage documentation.

- Reuse presentation macros across built-in templates and one browser field factory
  for inline edits and the demo. Make switch/JSON enhancement idempotent, share calendar
  lifecycle/precision handling, cache calendar labels and schema ordering scores, and
  synchronize relationship options with a single indexed pass. Preserve backend and
  template API contracts, CSP, form values and no-script controls.

- Reuse one themed calendar across forms, inline edits, filters, the browser demo and
  activity history. Use direct date/time inputs and a compact, one-click day calendar
  in record forms and inline edits, with optional precision/offset controls collapsed.
  Retain draft Apply/Cancel for filter ranges. Preserve exact microseconds and optional
  UTC offsets verbatim.
- Reserve and hide the `quiteadmin_` prefix in admin collections and SQL discovery.
  The default store needs a persistent writable directory (`.quite-admin` by default);
  application models/migrations remain unchanged. See the EN/RU storage documentation
  for container deployment, shared stores and audit failure/transaction boundaries.

### Fixed

- Keep invalid time precision fields focusable when reopening collapsed options in
  WebKit, and clear date/time filter drafts without validating discarded values.

- Push scalar projections into native database queries, relationship reads and batches.
  Lists, pickers and exports request only their fields plus necessary keys/labels,
  avoiding unselected hidden/large values and preserving native scalar types.

- Validate declared integer ranges before writes and filters, including MySQL unsigned
  integers, and translate expected SQL data/overflow errors into safe validation errors.

- Keep explicitly registered SQL tables and their options attached to fresh reflected
  descriptors after refresh(), with and without automatic discovery.

- Skip reflected tables without primary keys during auto-discovery, with an explicit
  warning, so unsupported tables cannot break other admin collections. Explicit
  descriptions still reject tables that cannot be addressed safely.

## 0.4.1 — 2026-11-01

### Added

- Publish one universal wheel and sdist to PyPI after a successful GitHub release,
  using a dedicated Trusted Publishing workflow and no long-lived API token.
  Support manual retries for published tags whose commits have passed full CI.
- Validate distribution metadata, install both artifacts in clean environments and
  verify installation from the public index after publishing. GitHub release downloads
  remain source-code ZIP/tar.gz archives; Python test matrices do not build packages.

### Fixed

- Explicitly use core metadata 2.4 for wheel and sdist, avoiding the Twine failure on
  unsupported metadata 2.5 while retaining package extras and bundled UI resources.

## 0.4.0 — 2026-11-01

### Added

- Explicit public API guarantees for the 0.4.x line, documented deprecation rules and
  migration notes in English/Russian. Required adapter API stays at version 1; optional
  capabilities remain opt-in. Template API 1 covers base blocks and documented contexts.
- Committed Python API baselines and a CI compatibility guard for exports, signatures,
  defaults, protocol methods, data fields, mutability, adapter capabilities, error statuses
  and template extension blocks. Modern and isolated GINO endpoint checks enforce it.

### Migration from 0.3.x

- Field, ModelSchema, RecordAction and Theme are mutable, unhashable configuration
  objects with explicit constructors. Stop relying on FrozenInstanceError or using them
  as dictionary/set keys; configure metadata before requests. Constructor calls,
  validation, equality and dataclasses.replace stay compatible. No database migration
  or new mandatory custom-adapter method is needed.
- Custom page callbacks cannot override renderer arguments (request, template, page,
  status, trusted_scripts) or reserved shared context. Keep application values under
  their own names. Template API version is exposed as template_api_version.

### Changed

- GitHub releases contain only the automatic source-code ZIP/tar.gz archives. Remove
  package builds from the Python matrix and release workflow, distribution uploads,
  Twine validation and PyPI publication. Pushing a version tag creates/updates and
  publishes the GitHub release automatically, marks it Latest and copies that version's
  changelog section into its description, including when a draft already exists.

- Replace hidden post-initialization and frozen-object mutation in Field, ModelSchema,
  RecordAction and Theme with explicit constructors and ordinary assignments. Constructor
  arguments, validation, derived defaults, equality and dataclasses.replace remain available.
  These four objects are now mutable configuration data; configure them before serving
  requests and use Admin.configure() for collection options. Operation snapshots stay protected.
- Use ordinary loops for composed SQL search conditions and explicit Peewee transaction
  selection instead of reduce() and nested conditional context managers.

### Fixed

- Ignore reserved renderer arguments in custom page data, preventing duplicate-argument
  errors, accidental status overrides and extra built-in script permissions.

- Patch the Diplodoc dependency chain and refresh its lockfile; npm audit reports zero
  vulnerabilities, with strict EN/RU builds and a scoped CommonJS/ESM compatibility shim.
- Require the complete reusable CI gate before publishing a source-only GitHub release;
  deploy Pages only from a successful CI run for the current master commit.
- Run Chromium/Firefox/WebKit regression scenarios and FastAPI/Litestar integration tests.

## 0.3.0 — 2026-11-01

### Changed

- Type-aware filter dialog with case-insensitive text fragments, exclusions, prefixes/
  suffixes, multi-value selection, whole-day datetime bounds and explicit empty text.
  Multiple conditions on one scalar field remain independently editable and exportable.
- Related-record lookup searches exact visible numeric/UUID/composite keys alongside
  text, and filter results show searchable descriptions and IDs with permission checks.

- Boolean list switches with immediate guarded saves, disabled read-only state and explicit NULL.

- Proportional compact listing gutters and full available table width.

- Create record shares the listing toolbar with search, filter and export controls.

- Boolean form switches with explicit nullable state and select fallback.

- Export options now open from a square download icon instead of occupying the list.

- Compact square funnel controls for listing filters.

- Automatic listing search after a 900 ms typing pause, with IME and Enter support.

- Theme-derived JSON colors, native control color scheme and in-page date calendars.

- Compact default interface density, approximately the previous UI at 80% zoom.

### Added

- Configurable inline list-cell editing through field policies, write hooks, CSRF and
  atomic stale-edit guards, with reusable typed controls and preserved validation errors.

- Configurable collapsible sidebar collection groups with per-mount browser state.

- Type-aware record forms: multiline TEXT fields across SQL reflection and ORM adapters,
  native date/time pickers with explicit optional UTC offsets, and a local JSON/JSONB
  syntax editor with precision-preserving formatting and no-script fallbacks.
- EN/RU design proposal comparing field widget extension APIs; no new widget API implemented.

- Permission-checked CSV/XLSX exports from collection lists with selected columns, current
  search/filters/sorting and optional one-hop related columns. Collection relationships
  stay on separate lines within a cell. Bounded exports fail rather than truncate,
  CSV neutralizes spreadsheet formulas and XLSX preserves values as literal text.

## 0.2.0 — 2026-11-01

### Added

- Independent minimum/latest dependency profiles on Python 3.11 and 3.15, a current
  Starlette 0.x profile, and separate GINO/PostgreSQL endpoints. CI retains resolved
  versions and JUnit artifacts without changing the project lockfile.
- Explicit `sqlmodel` extra and dedicated real SQLModel sync/async contracts in the
  ordinary, endpoint and PostgreSQL/MySQL suites, including relationships and web behavior.

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

- Supported dependency floors now target verified Python 3.11–3.15 combinations:
  Starlette 0.52.1, AnyIO 4.15.1, SQLAlchemy 2.0.52, SQLModel 0.0.27, Tortoise 0.25.4,
  FastAPI 0.162, Litestar 2.20 and legacy asyncpg 0.32. Upgrade application locks to
  these ranges; EN/RU migration and verification instructions explain the narrowed support.
- Example HTTP tests use ASGITransport with the real framework lifespan, preserving
  lifecycle coverage across Starlette branches without TestClient-specific HTTP dependencies.

- Diplodoc EN/RU navigation groups guides by task. Overview, configuration, architecture,
  compatibility instructions and browser-demo walkthroughs reflect the current filters,
  concurrency protection, relationship search and database schema, with fresh screenshots.

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

- SQLModel `AutoString` fields are recognized as editable/searchable strings without
  assuming arbitrary custom SQLAlchemy TypeDecorator codecs are safe strings.

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

### Migration from the earlier 0.2.0 development checkout

Regenerate the application's lockfile within the supported ranges. The earlier broad
floors included SQLAlchemy releases that failed to import on Python 3.15, SQLModel
0.0.22 that could not construct table models there, Tortoise 0.25.0 using a removed
aiosqlite API and Starlette/Litestar paths using deprecated asyncio APIs. Install the
`sqlmodel` extra or `all` for modern adapters; isolate `gino-legacy` from SQLAlchemy 2.x.
Adapter API 1 and record data formats are unchanged.

## 0.1.0

Initial recorded version: authenticated CRUD, adapter discovery, field policies,
custom pages, English/Russian customization, application-owned logging and
CPython 3.11–3.15 support for FastAPI and Litestar.
