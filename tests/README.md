# Test matrix

Use `backend` / `admin` for adapter contracts and behavior that depends on database
metadata, queries, transactions or returned values. They exercise SQLAlchemy ORM
and reflected SQL in sync/async modes, Peewee and Tortoise. SQLModel reuses the
contracts with its own sync/async models; GINO runs in its separate legacy environment.

Use `web_backend` / `web_admin` for shared HTTP behavior such as navigation,
localization, templates, history presentation and logging. These use a fresh
SQLAlchemy backend for each test. Keep FastAPI and Litestar parameterization.
`test_full_browser_flow` explicitly runs on all six backends with FastAPI, Litestar
and Litestar's body-reading logging middleware, preserving 18 complete CRUD flows.

Independent read-only queries against the same seed data can share one test's
database. Include the input in assertion messages. Keep separate fixtures for
mutating scenarios, and keep function-scoped database isolation. Do not shorten
password hashing, suppress warnings or replace database operations with mocks to
improve timings.

## Audit: 2026-11-02

Reviewed all 35 Python test files, five Node test files, three Playwright specs,
their fixtures and CI matrices, starting from `caf40f9`.

### Changes

- Removed the backend multiplier from shared web scenarios. Adapter-specific
  filtering, exports, relationships, metadata, hooks and concurrent writes retain
  their full matrices.
- Run all 11 typed-filter cases, eight text-filter cases, nine unsafe-query cases,
  seven invalid filter/projection cases and four invalid-key cases against one
  fixture per contract/backend, preserving the original inputs and assertions.
  SQLModel and GINO reuse these same contract functions.
- Check NULL exclusion once per backend instead of once per text-filter case.
- Fold the scalar-key round trip into the CRUD contract; schema tests already
  reject schemas without primary keys. Remove those two standalone tests.
- Remove the duplicate detail-page GET immediately before fetching the edit form
  in the CRUD flow; retain its status and content assertions.

| Changed test module | Cases before | Cases after |
| --- | ---: | ---: |
| `test_adapters.py` | 198 | 54 |
| `test_adapter_safety.py` | 101 | 34 |
| `sqlmodel/test_contracts.py` | 156 | 86 |
| `test_web.py` | 144 | 39 |
| `test_history.py` | 179 | 34 |
| `test_customization.py` | 32 | 22 |
| `test_integration.py` | 18 | 8 |
| `test_listing_interface.py` | 19 | 4 |
| `test_logging.py` (including optional skip) | 32 | 17 |
| `test_public_api.py` | 24 | 14 |

### Retained checks

| Test files / family | Reason to retain |
| --- | --- |
| `test_relations.py`, `test_batch_relations.py`, `test_diagram.py` | ORM-specific relation discovery, composite/self-referencing keys, rollback, permissions and bounded query counts. |
| `test_filters.py`, `test_exports.py`, `test_inline_edit.py`, `test_extensions.py` | Database values cross HTTP parsing, projection, serialization, field policy and write hooks. |
| `test_concurrency.py`, `test_pagination.py`, `test_query_timeout.py` | Native transactions, simultaneous writes, signed cursors and pooled-connection recovery. |
| `test_database_features.py`, `test_sql_reflection.py`, `test_numeric_limits.py`, `test_form_controls.py`, `test_projection.py` | Distinct metadata/type mappings, refresh, overflows and prevention of loading excluded values. |
| `test_storage.py`, `test_activity.py` | Independent native/sync/async storage implementations, migrations, exact types, redaction and cross-process writes. |
| `test_schema.py`, `test_public_api.py`, `test_release_checks.py`, `test_dependency_profiles.py` | Constructor/coercion boundaries and regression tests for compatibility/release guards. |
| `test_web.py`, `test_history.py`, `test_customization.py`, `test_integration.py`, `test_listing_interface.py`, `test_logging.py` | Shared HTTP behavior retains every scenario and framework; full CRUD still crosses all backends. |
| `test_examples.py` | Real example application lifespans and custom reports. |
| `sqlmodel/*.py`, `gino/*.py` | Actual SQLModel/Pydantic mappings and legacy GINO APIs require their own environments. |
| `demo.test.mjs`, `schema.test.cjs`, `filters.test.cjs`, `forms.test.cjs`, `history.test.cjs` | Fast checks of separate JavaScript implementations; 26 tests complete in about 0.06 seconds locally. |
| `browser/*.spec.mjs` | Real browser focus, keyboard, downloads, layout and native validation are not covered by ASGI/Node checks. Retain all 17 scenarios and three browser projects. |

### Validation

On local Python 3.12.14, ordinary pytest runs changed from **1373 passed, 2 skipped
in 63.58 s** to **782 passed, 2 skipped in 41.39 s**: 591 fewer cases (43%) and
35% less elapsed time. These are individual local runs, not a CI timing guarantee.

An additional before/after run with Python's `sys.monitoring` recorded exactly the
same **9185 executed source lines and 4619 branch transitions** in
`src/quite_admin`, with no lost or added entries. This compares execution in the
pytest process, excludes subprocess coverage, and does not measure assertion quality.

Ruff lint/format, the modern public API baseline, the release guard, demo build,
JavaScript syntax and all 26 Node tests passed. The two pytest skips are the
uninstalled GINO and picologging dependencies. PostgreSQL/MySQL, the isolated GINO
suite, Chromium and Firefox were not run locally; their CI jobs remain intact.

WebKit: **15 passed, 2 failed**. Both failures reproduced on an untouched archive of
`caf40f9`:

- `datetime.spec.mjs`: `incomplete form timestamps are validated and clearing a date
  clears the whole value` fails to focus the fractional-seconds input (line 80).
- `datetime.spec.mjs`: `Escape closes the picker before its enclosing dialog, and
  clear discards invalid drafts` leaves the panel visible after Clear (line 137).

These browser regressions remain visible; no browser assertions were removed or
weakened. Production code, dependency declarations and CI matrices are unchanged.
