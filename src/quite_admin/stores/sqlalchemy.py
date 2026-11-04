"""SQLite/PostgreSQL/MySQL service storage using an owned URL or a borrowed engine."""

from __future__ import annotations

from anyio import to_thread

try:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError
    from sqlalchemy.pool import NullPool
except ImportError as exc:
    raise ImportError("Install quite-admin[sqlalchemy] for server-backed admin storage.") from exc

from ..storage import _INDEXES, StorageConflict, StorageError, _RelationalStore, _Result


class SQLAlchemyStore(_RelationalStore):
    """Business sessions/transactions are never reused. Borrowed engines remain app-owned.

    Core SQL also works with SQLAlchemy 1.3 in the isolated GINO environment.
    URL-created engines default to NullPool. Mount helpers close owned engines.
    """

    def __init__(self, engine, *, namespace="default", engine_options=None):
        super().__init__(namespace=namespace)
        self._owns_engine = isinstance(engine, str)
        if engine_options is not None and not self._owns_engine:
            raise ValueError("engine_options requires a storage URL, not a borrowed engine.")
        options = {"hide_parameters": True, **(engine_options or {})}
        if not any(name in options for name in ("poolclass", "pool_size", "max_overflow")):
            options["poolclass"] = NullPool
        try:
            self.engine = create_engine(engine, **options) if self._owns_engine else engine
        except (SQLAlchemyError, ImportError) as exc:
            raise StorageError() from exc
        self._async = hasattr(self.engine, "sync_engine")
        dialect = self.engine.dialect.name
        if dialect not in {"sqlite", "postgresql", "mysql"}:
            raise ValueError("Admin storage supports SQLite, PostgreSQL and MySQL.")
        self._dialect = dialect

    async def aclose(self):
        """Dispose only an engine created from this store's URL."""
        if self._owns_engine:
            if self._async:
                await self.engine.dispose()
            else:
                await to_thread.run_sync(self.engine.dispose)

    @staticmethod
    def _executor(connection):
        def execute(statement, params):
            if connection.dialect.name == "mysql" and statement.startswith("CREATE TABLE"):
                statement = statement.replace("payload TEXT", "payload MEDIUMTEXT")
            result = connection.execute(text(statement), params)
            try:
                rows = (
                    [dict(zip(result.keys(), row, strict=True)) for row in result.fetchall()]
                    if result.returns_rows
                    else []
                )
                count = result.rowcount
            finally:
                result.close()
            return _Result(rows, count)

        return execute

    def _initialize(self, connection):
        execute = self._executor(connection)
        if self._dialect == "postgresql":
            execute("SELECT pg_advisory_xact_lock(1837465921)", {})
        elif self._dialect == "mysql":
            rows = execute("SELECT GET_LOCK('quiteadmin_schema', 15) AS acquired", {}).rows
            if rows[0]["acquired"] != 1:
                raise StorageError()
        else:
            execute("BEGIN IMMEDIATE", {})

        def create_indexes():
            inspector = inspect(connection)
            existing = {
                index["name"]
                for table in ("quiteadmin_documents", "quiteadmin_activity", "quiteadmin_actors")
                for index in inspector.get_indexes(table)
            }
            for name, target in _INDEXES.items():
                if name not in existing:
                    execute(f"CREATE INDEX {name} ON {target}", {})

        self._schema(execute, create_indexes)

    def _release(self, connection):
        if self._dialect == "mysql":
            try:
                self._executor(connection)("SELECT RELEASE_LOCK('quiteadmin_schema')", {})
            except SQLAlchemyError:
                connection.invalidate()
                raise

    def _sync(self, operation):
        with self.engine.connect() as connection:
            initialize = not self._ready
            try:
                with connection.begin():
                    if initialize:
                        self._initialize(connection)
                    result = operation(self._executor(connection))
                self._ready = True
                return result
            finally:
                if initialize:
                    self._release(connection)

    async def _run(self, operation, *, write=False):
        try:
            if not self._async:
                return await to_thread.run_sync(self._sync, operation)
            async with self.engine.connect() as connection:
                initialize = not self._ready
                try:
                    async with connection.begin():
                        if initialize:
                            await connection.run_sync(self._initialize)
                        result = await connection.run_sync(
                            lambda sync: operation(self._executor(sync))
                        )
                    self._ready = True
                    return result
                finally:
                    if initialize:
                        await connection.run_sync(self._release)
        except IntegrityError as exc:
            raise StorageConflict() from exc
        except SQLAlchemyError as exc:
            raise StorageError() from exc
