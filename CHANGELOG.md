# Changelog

## 0.2.0 — Unreleased

### Added

- Inline one-to-one, one-to-many and many-to-many editors across SQL reflection,
  SQLAlchemy, Tortoise and Peewee. Scalar and relationship changes save atomically.
- Demo data for each relationship kind.
- Custom local logos and concise dashboard, list and login screens.
- Linked breadcrumbs, including reverse-proxy and nested mount prefixes.
- Clickable record rows with a separate delete confirmation action.

### Changed

- Records use one page for viewing and editing. Read-only users see the same page
  without writable controls. Existing `/edit` URLs redirect to the record URL.
- Template overrides must use `form.html` for the record page; the separate
  `detail.html` template has been removed. See the EN/RU configuration documentation.

### Fixed

- The Litestar queue logging test connects its configured console sink on Python 3.11.
- Documentation deployment publishes generated Diplodoc HTML through GitHub Pages
  Actions instead of passing Jinja examples to Jekyll/Liquid.

## 0.1.0

Initial recorded version: authenticated CRUD, adapter discovery, field policies,
custom pages, English/Russian customization, application-owned logging and
CPython 3.11–3.15 support for FastAPI and Litestar.
