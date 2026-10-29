"""Opt-in disposable server databases; default tests always use isolated SQLite files."""

import os

from sqlalchemy import Boolean, MetaData, create_engine
from sqlalchemy.engine import make_url


def server_url():
    raw = os.environ.get("QUITE_ADMIN_TEST_DATABASE_URL")
    if not raw:
        return None
    url = make_url(raw)
    if (
        url.get_backend_name() not in {"postgresql", "mysql"}
        or url.host not in {"127.0.0.1", "localhost"}
        or url.database != "quite_admin_test"
    ):
        raise ValueError("Server tests require a local disposable database named quite_admin_test.")
    return url


def sqlalchemy_url(sqlite_url, *, asynchronous=False):
    url = server_url()
    if url is None:
        return sqlite_url
    dialect = url.get_backend_name()
    driver = (
        ("asyncpg" if asynchronous else "psycopg")
        if dialect == "postgresql"
        else ("aiomysql" if asynchronous else "pymysql")
    )
    return url.set(drivername=f"{dialect}+{driver}")


def reflected_types():
    # MySQL stores BOOLEAN as TINYINT(1), losing the original application's intent.
    url = server_url()
    return {"items": {"active": Boolean()}} if url and url.get_backend_name() == "mysql" else {}


def peewee_database(sqlite_database):
    url = server_url()
    if url is None:
        return sqlite_database
    from playhouse.db_url import connect

    return connect(url.render_as_string(hide_password=False))


def tortoise_url():
    url = server_url()
    if url is None:
        return "sqlite://:memory:"
    return url.set(
        drivername="postgres" if url.get_backend_name() == "postgresql" else "mysql"
    ).render_as_string(hide_password=False)


def drop_tortoise_tables(models):
    if server_url() is None:
        return
    names = {model._meta.db_table for model in models}
    names.update(
        model._meta.fields_map[name].through for model in models for name in model._meta.m2m_fields
    )
    engine = create_engine(sqlalchemy_url(""))
    try:
        metadata = MetaData()
        metadata.reflect(engine, only=list(names))
        metadata.drop_all(engine)
    finally:
        engine.dispose()
