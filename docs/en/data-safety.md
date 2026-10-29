# Data access and compatibility

## Query and identity boundaries

Built-in adapters validate sort and search fields against scalar schema metadata before
building a query. SQL values use driver parameters; text search treats `%` and `_` as
literal characters. The browser may sort only visible fields. The current UI has no
arbitrary SQL, filter-expression or column-expression input.

`Query.validate(schema)` requires nonnegative offsets, limits from 1 to 10,000, a boolean
sort direction and at most 4,096 search characters. Search fields must be known strings.
The UI uses smaller limits: 100 records per page and 500 search characters.

Adapters require exactly the complete primary key for get/update/delete, including all
parts of composite keys. Empty keys, null key values, lookup operators such as `id__gt`
and unknown write fields are rejected. Updating a primary key is not supported.
Tables without primary keys fail explicitly instead of using a guessed row identifier.

## Scalar values

Forms preserve `Decimal`, UUID, enum, ISO dates/times, JSON and integer values without
converting them through JavaScript numbers. Signed 64-bit integers round-trip in the
contract suite. The database's column precision, range and timezone rules still apply.
SQLite NUMERIC affinity can lose decimal precision; use an exact NUMERIC/DECIMAL column
in PostgreSQL/MySQL when exact arithmetic matters.

Nullable blank form controls parse as `None`; non-null string fields may contain an empty
string. JSON objects, arrays and scalars are supported when the adapter exposes them.
NaN and Infinity are rejected. A JSON `null` control produces `None`; the ORM/column decides
whether that is SQL NULL or JSON null. The form does not offer a separate switch for both.
Reflection cannot recover Python UUID or enum classes from an ordinary string column.

## Transactions and hooks

Each write owns a transaction and rolls back on any exception. Scalar and relationship
changes share that transaction. Read operations close their connection/session without
committing a write transaction. The host owns engines and pools; adapters own their
operation-scoped sessions. Never pass a shared request session as a session factory.

SQL reflection executes database defaults, constraints, triggers and database cascades.
It cannot execute application validators or Python ORM hooks. Native ORM adapters use
model persistence methods; their normal save hooks and ORM events apply. An explicit
record deletion also applies the ORM's and database's configured cascades. Relationship
detachment never means deleting the target, and destructive delete-orphan detachment is
blocked where detected. Use an application-service adapter for business rules and soft delete.

Tests check rollback after constraint and hook errors, trigger-refreshed values, cascades,
composite primary/foreign keys and continued operation after failures.

## Database contract checks

| Database | Adapters / paths | Evidence |
|---|---|---|
| SQLite | SQL reflection sync/async, SQLAlchemy sync/async, Peewee, Tortoise | Full suite, CPython 3.11–3.15 CI |
| PostgreSQL 17 | The same six paths | 141 CRUD, query-safety and relationship checks passed locally; dedicated CI job |
| MySQL 8.4 | The same six paths | Dedicated CI job configured; local run pending because image downloads timed out |

The server matrix is `.github/workflows/databases.yml`. It uses disposable service
databases, not a developer's application database. To run the same suite locally, create
a **disposable** local database named `quite_admin_test`, then:

```bash
uv sync --locked --group database-check
QUITE_ADMIN_TEST_DATABASE_URL='postgresql://quite_admin:local-test-password@127.0.0.1:55432/quite_admin_test' \
  uv run --group database-check pytest tests/test_adapters.py tests/test_adapter_safety.py tests/test_relations.py -q
```

Use a `mysql://` URL for MySQL. Tests create and drop their tables; run them serially.
The opt-in fixture rejects non-local hosts and other database names. Without the
environment variable, tests keep using isolated SQLite files or in-memory databases.
CI configuration alone is not evidence that a remote job has passed. No claim is made
for every permitted driver, ORM or server version.
