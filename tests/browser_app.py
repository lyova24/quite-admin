"""Fictional, disposable browser-test application; never connects to an application DB."""

from datetime import date, datetime, time
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Time,
    create_engine,
)

from quite_admin import Admin, FieldOptions, ModelOptions, PasswordAuth, RecordAction, Theme
from quite_admin.adapters.sql import SQLAdapter

_storage = TemporaryDirectory(prefix="quite-admin-browser-")
engine = create_engine(f"sqlite:///{_storage.name}/browser.db")
metadata = MetaData()
customers = Table(
    "customers", metadata, Column("id", Integer, primary_key=True), Column("caption", String(100))
)
entries = Table(
    "entries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("active", Boolean),
    Column("note", Text),
    Column("status", Enum("pending", "paid", "cancelled", native_enum=False)),
    Column("count", Integer),
    Column("day", Date),
    Column("moment", DateTime),
    Column("clock", Time),
    Column("customer_id", ForeignKey("customers.id")),
)
metadata.create_all(engine)
with engine.begin() as connection:
    connection.execute(
        customers.insert(),
        [{"id": 51, "caption": "Alex Johnson"}, {"id": 52, "caption": "Maria Jones"}],
    )
    for index, name in enumerate(["Alex Smith", "alex Brown", "Alex%_! Literal", "Other Person"]):
        connection.execute(
            entries.insert(),
            {
                "name": name,
                "active": index % 2 == 0,
                "note": "" if index == 0 else None if index == 1 else "Text",
                "status": ["pending", "paid", "cancelled", "pending"][index],
                "count": 10 + index * 5,
                "day": date(2026, 11, 1),
                "moment": datetime(2026, 11, 1, 23, 59, 59) if index < 3 else datetime(2026, 11, 2),
                "clock": time(12, 34, 56, 123456),
                "customer_id": 51 if index < 2 else 52,
            },
        )
app = FastAPI()


async def reset_counter(operation):
    return await SQLAdapter(engine).update(operation.model, operation.key, {"count": 0})


@app.get("/health")
async def health():
    return {"ok": True}


for mount, theme in (
    ("/admin", None),
    (
        "/dark",
        Theme(
            primary="#79c6a5",
            background="#0f172a",
            surface="#172033",
            text="#e2e8f0",
            muted="#94a3b8",
            border="#334155",
        ),
    ),
):
    admin = Admin(
        auth=PasswordAuth.single_user("admin", "browser-test-password"),
        secret_key="browser-fixture-only-" * 3,
        secure_cookies=False,
        session_cookie=mount[1:] + "_session",
        storage=f"{_storage.name}/admin-state.sqlite3",
        adapters=[
            SQLAdapter(
                engine,
                column_types={
                    "entries": {"status": Enum("pending", "paid", "cancelled", native_enum=False)}
                },
            )
        ],
        **({"theme": theme} if theme else {}),
    )
    admin.configure(
        "entries",
        options=ModelOptions(
            group="Data",
            filter_fields=("name", "active", "status", "count", "note", "day", "moment", "clock"),
            list_fields=("id", "name", "status", "active", "count", "day"),
            list_editable=("note", "active", "day"),
            fields={"name": FieldOptions(label="Name")},
            actions=(RecordAction("reset", "Reset counters", reset_counter, bulk=True),),
        ),
    )
    admin.configure(
        "customers", options=ModelOptions(record_label="id", search_fields=("caption",))
    )
    admin.mount_fastapi(app, mount)
