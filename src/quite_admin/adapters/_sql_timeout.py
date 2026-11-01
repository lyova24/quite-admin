"""Operation-scoped read deadlines; restore pooled-connection settings on exit."""

import math
from contextlib import contextmanager
from time import monotonic

from sqlalchemy.exc import DBAPIError

from quite_admin.errors import QueryTimeout


def validate_timeout(seconds):
    if seconds is not None and (
        type(seconds) not in {int, float}
        or not math.isfinite(seconds)
        or not 0 < seconds <= 2147483
    ):
        raise ValueError(
            "query_timeout must be a positive finite number of seconds, at most 2147483."
        )
    return seconds


@contextmanager
def read_timeout(connection, seconds):
    if seconds is None:
        yield
        return
    dialect = connection.dialect.name
    expired = False
    restore = None
    if dialect == "sqlite":
        deadline = monotonic() + seconds

        def progress():
            nonlocal expired
            expired = monotonic() >= deadline
            return int(expired)

        raw = connection.connection.dbapi_connection

        def set_handler(callback):
            if hasattr(raw, "run_async"):
                raw.run_async(lambda driver: driver.set_progress_handler(callback, 1000))
            else:
                raw.set_progress_handler(callback, 1000)

        set_handler(progress)

        def restore_sqlite():
            set_handler(None)

        restore = restore_sqlite
    elif dialect == "postgresql":
        milliseconds = max(1, math.ceil(seconds * 1000))
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = {milliseconds}")
    elif dialect == "mysql":
        previous = int(
            connection.exec_driver_sql("SELECT @@SESSION.max_execution_time").scalar_one()
        )
        milliseconds = max(1, math.ceil(seconds * 1000))
        connection.exec_driver_sql(f"SET SESSION max_execution_time = {milliseconds}")

        def restore_mysql():
            connection.exec_driver_sql(f"SET SESSION max_execution_time = {previous}")

        restore = restore_mysql
    else:
        raise ValueError("query_timeout supports SQLite, PostgreSQL and MySQL.")
    try:
        yield
    except DBAPIError as exc:
        original = exc.orig
        state = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
        code = original.args[0] if getattr(original, "args", ()) else None
        if expired or state == "57014" or code == 3024:
            raise QueryTimeout() from exc
        raise
    finally:
        if restore is not None:
            try:
                restore()
            except DBAPIError:
                connection.invalidate()
