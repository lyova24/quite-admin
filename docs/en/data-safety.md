# Data access and compatibility

## Query and identity boundaries

Built-in adapters validate sort and search fields against scalar schema metadata before
building a query. SQL values use driver parameters; text search treats `%` and `_` as
literal characters. The browser may sort only visible fields. The current UI has no
arbitrary SQL, filter-expression or column-expression input.

`Query.validate(schema)` requires nonnegative offsets, limits from 1 to 10,000, a boolean
sort direction and at most 4,096 search characters. Search fields must be known strings.
The UI uses smaller limits: 100 records per page and 500 search characters.
[Scalar and relationship filters](filters.md) run before counts and pagination.
`Query.related` requires explicit adapter support and typed complete target keys;
ordinary `Query.validate(schema)` rejects it without related schema metadata.

Adapters require exactly the complete primary key for get/update/delete, including all
parts of composite keys. Empty keys, null key values, lookup operators such as `id__gt`
and unknown write fields are rejected. Updating a primary key is not supported.
CRUD collections without primary keys fail explicitly instead of using a guessed row identifier.
A [diagram-only junction](database-schema.md) may still describe a table without a primary key;
it does not gain record operations.

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

Built-in form edits use [signed revisions](configuration.md#concurrent-edits) and atomic
precondition checks, including selected relationship membership. Stale writes roll
back with 409; application adapters opt in explicitly. This is edit conflict detection,
not a persistent audit/version history.

## Database contract checks

| ORM / integration | Automatic checks | Limits |
|---|---|---|
| SQL reflection | Sync/async CRUD, query filters/projection, composite PK/FK, relationship writes | Physical schema only; no Python hooks; pure M:N junctions only |
| SQLAlchemy 2.x | Sync/async CRUD, query contract, native hooks, relationship writes | Imported mapped classes; dynamic/write-only/view-only relations are read-only |
| SQLModel | Uses the SQLAlchemy adapter and registry | No separate SQLModel model suite yet; SQLAlchemy compatibility is not independent SQLModel verification |
| Peewee | Worker-thread CRUD, composite keys, raw FK, M:N and 1:N/1:1 | No async Peewee API; host-owned database |
| Tortoise | Native async CRUD, raw FK, UUID, JSON and relationships | Must initialize in host lifespan; no composite PK contract |
| GINO 1.0.x | Native async CRUD, shared query/relationship contracts, composite PK/FK, PostgreSQL types | PostgreSQL/asyncpg only; separate SQLAlchemy 1.3 environment; pure M:N junctions |
| Custom adapters | A dependency-free example and structural protocol checks | Application author verifies storage, transactions and optional capabilities |

FastAPI and Litestar integration suites exercise authentication, CRUD, relationships,
field restrictions and proxy prefixes. The lockfile is the tested dependency set,
not a guarantee for every version in the permitted ranges.

| Database | Adapters / paths | Evidence |
|---|---|---|
| SQLite | SQL reflection sync/async, SQLAlchemy sync/async, Peewee, Tortoise | Full suite, CPython 3.11–3.15 CI |
| PostgreSQL 17 | The same six paths | Locally verified shared CRUD, query-safety, filters, relationships, concurrency and diagram contracts; dedicated CI job |
| MySQL 8.4 | The same six paths | The same contracts verified locally; dedicated CI job |

MySQL reflection cannot distinguish `BOOLEAN` from ordinary `TINYINT(1)` columns.
The contract fixture explicitly declares the intended Boolean type through
[`column_types`](integration.md); ordinary tiny integers remain numeric.
Peewee 3.19 passes deprecated `db` / `passwd` arguments to PyMySQL 1.2. The test database
subclass passes `database` / `password` instead, without suppressing warnings or changing
the application's database objects. Its real queries and transactions still use
Peewee and PyMySQL; this is the connection configuration tested by the server matrix.

The server matrix is `.github/workflows/databases.yml`. It uses disposable service
databases, not a developer's application database. To run the same suite locally, create
a **disposable** local database named `quite_admin_test`, then:

```bash
uv sync --locked --group database-check
QUITE_ADMIN_TEST_DATABASE_URL='postgresql://quite_admin:local-test-password@127.0.0.1:55432/quite_admin_test' \
  uv run --group database-check pytest tests/test_adapters.py tests/test_adapter_safety.py tests/test_relations.py tests/test_sql_reflection.py tests/test_concurrency.py tests/test_filters.py tests/test_diagram.py -q
```

Use a `mysql://` URL for MySQL. Tests create and drop their tables; run them serially.
The opt-in fixture rejects non-local hosts and other database names. Without the
environment variable, tests keep using isolated SQLite files or in-memory databases.
CI configuration alone is not evidence that a remote job has passed. No claim is made
for every permitted driver, ORM or server version.

GINO runs in a [separate environment and CI matrix](gino.md), preserving the existing
SQLAlchemy 2.x paths. Local verification includes GINO 1.0.1, SQLAlchemy 1.3.24 and
asyncpg 0.32.0 with PostgreSQL 16, plus the extended concurrency/filter/diagram contracts
on PostgreSQL 17. The dedicated CI service uses PostgreSQL 17; configuration alone
does not establish a passed remote run. Test counts change as contracts grow; the
commands above and the workflow specify which suites are included.
