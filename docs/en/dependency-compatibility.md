# Dependency compatibility

Compatibility checks cover the locked development environment and separately resolved
runtime endpoints. The supported floors in `pyproject.toml` target one coherent stack
for the advertised CPython 3.11–3.15 range. Dependencies are installed in isolated
virtual environments; endpoint runs do not rewrite `uv.lock`.

## Declared ranges

| Dependency | Supported range | Endpoint role |
|---|---|---|
| Starlette | `>=0.52.1,<2.0` | Minimum 0.x, latest 0.x and latest allowed 1.x |
| Jinja2 | `>=3.1.6,<4` | Core |
| itsdangerous | `>=2.2,<3` | Signed sessions and revisions |
| python-multipart | `>=0.0.20,<1` | Form parsing |
| AnyIO | `>=4.15.1,<5` | Async/worker execution across supported Python versions |
| SQLAlchemy | `>=2.0.52,<2.1` | Native ORM and SQL reflection; includes Python 3.15 support |
| SQLModel | `>=0.0.27,<0.1` | Explicit `sqlmodel` extra, also included in `all` |
| Tortoise ORM | `>=0.25.4,<1.0` | Includes compatibility with current aiosqlite |
| Peewee | `>=3.17,<4` | Native synchronous adapter |
| FastAPI | `>=0.162,<1` | Verified framework floor with the current Starlette ranges |
| Litestar | `>=2.20,<3` | Verified framework floor across the Python range |
| GINO | `>=1.0.1,<1.1` | Separate `gino-legacy` extra |
| SQLAlchemy for GINO | `>=1.3.24,<1.4` | Isolated from SQLAlchemy 2.x / SQLModel |
| asyncpg for GINO | `>=0.32,<1` | Verified driver floor for the supported Python range |

SQLAlchemy 2.1, Tortoise 1.x and Peewee 4.x are outside these ranges. **Latest** means
the newest mutually compatible stable versions within the declared ranges. Transitive
requirements follow their owners' metadata; each report records the actual resolved versions.
The jobs test coherent environments rather than every Cartesian combination of package versions.

## Automated profiles

[Dependency compatibility workflow](https://github.com/lyova24/quite-admin/actions/workflows/compatibility.yml)
runs on pushes, pull requests and manual dispatch:

| Profile | Python | Checks |
|---|---|---|
| `minimum` | 3.11 and 3.15 | Every declared modern runtime dependency pinned to its exact lower bound; full Python suite |
| `latest` | 3.11 and 3.15 | Fresh resolution with `--upgrade`; full Python suite |
| `starlette-0` | 3.12 | Fresh resolution constrained to Starlette `<1`; full Python suite |
| `minimum --legacy` | 3.11 and 3.15 | Exact core/GINO/framework floors and real PostgreSQL 17 contracts |
| `latest --legacy` | 3.11 and 3.15 | Fresh legacy resolution and the same PostgreSQL contracts |

The ordinary locked CI matrix still runs on every Python version from 3.11 to 3.15.
Endpoint jobs use `uv pip check`, retain deprecation warnings as errors and upload
resolved-version JSON and JUnit XML as artifacts. A missing GINO database URL fails
the runner instead of producing a successful run containing skipped contracts.
Workflow configuration alone is not evidence that a remote run passed; inspect the
run status and artifacts. Local verification is recorded in [the compatibility matrix](data-safety.md).

The latest profiles verified locally on **2026-10-30** resolved Starlette 1.10.0,
SQLAlchemy 2.0.55, SQLModel 0.0.48, Tortoise 0.25.4, Peewee 3.19.0, FastAPI 0.162.0,
Litestar 2.25.0 and Pydantic 2.14.2. The separate 0.x profile resolved Starlette 0.52.1.
These are dated results; later resolutions may select newer versions within the ranges.

## Reproduce an endpoint

From the repository root with Python 3.11+ and uv 0.13.6+ available:

```bash
python scripts/test_compatibility.py --profile minimum --python 3.11 \
  --report build/compatibility/minimum-3.11.json
python scripts/test_compatibility.py --profile latest --python 3.15 \
  --report build/compatibility/latest-3.15.json
python scripts/test_compatibility.py --profile starlette-0 --python 3.12 \
  --report build/compatibility/starlette-0.json
```

The runner removes its temporary environment after completion. `--environment PATH`
keeps it at a new disposable path for diagnosis. The ordinary project environment
and lockfile are unchanged. Test/build tools resolve separately from runtime floors.

For GINO, create a **disposable** local PostgreSQL database named `quite_admin_gino_test`, then:

```bash
QUITE_ADMIN_GINO_TEST_DATABASE_URL='postgresql://quite_admin:local-test-password@127.0.0.1:55432/quite_admin_gino_test' \
  python scripts/test_compatibility.py --legacy --profile minimum --python 3.15 \
  --report build/compatibility/gino-minimum-3.15.json
```

See [GINO setup](gino.md) and [database contracts](data-safety.md) for database safeguards.

## SQLModel evidence

`tests/sqlmodel` defines actual `SQLModel` table classes, DTO inheritance, isolated
registries and `Relationship` / link models. Both sync and async SQLAlchemy sessions
run the shared adapter contracts: CRUD and rollback, filters/projections, permissions,
FastAPI/Litestar forms, paginated relationship lookups, atomic relationship saves,
stale edits and diagram metadata. Model-specific tests cover Python defaults, UUID,
Decimal, enums, JSON, native `AutoString` fields and unmapped Pydantic schemas.

The suite runs in the locked and modern endpoint jobs, and in the PostgreSQL/MySQL
contract jobs. Its JSON/SQLModel tests use Pydantic 2. SQLModel support uses the native
SQLAlchemy adapter; it does not automatically run application-level Pydantic validation
for admin writes. Application invariants still belong in parsers, hooks or a service adapter.

## Upgrading from the earlier 0.2.0 development checkout

Update the application environment to the ranges above and regenerate its lockfile.
The earlier broad floors included combinations that failed on modern Python or with
current transitive dependencies. Old SQLAlchemy releases failed to import on Python 3.15;
SQLModel 0.0.22 did not construct table models there; Tortoise 0.25.0 used an aiosqlite API
removed in newer aiosqlite. Older Starlette/Litestar paths also used deprecated asyncio APIs.

Install `quite-admin[sqlmodel,fastapi]` (from this source checkout until publication) for
SQLModel, or use `all` for the modern adapter bundle. Keep GINO in its separate legacy
environment. Adapter API version 1 and record data formats remain unchanged.
