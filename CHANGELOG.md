# Changelog

## 0.2.0 — Unreleased

### Added

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
