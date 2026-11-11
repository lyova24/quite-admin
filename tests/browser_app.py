"""Fictional, disposable browser-test application; never connects to an application DB."""

from datetime import date, datetime, time
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from sqlalchemy import (
    JSON,
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
previews = Table(
    "previews",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(100)),
    Column("url", Text),
    Column("code", String(100)),
    Column("payload", JSON),
    Column("body", Text),
)
metadata.create_all(engine)
with engine.begin() as connection:
    connection.execute(
        previews.insert(),
        [
            {
                "title": "Value controls",
                "url": "https://example.test/page?q=hello&next=world",
                "code": "abc/123",
                "payload": {"hello": "Привет", "nested": [1, 2]},
                "body": "First line\nSecond line " + "long text " * 20,
            },
            {
                "title": "Unsafe URL",
                "url": "javascript:alert(1)",
                "code": None,
                "payload": {"text": "<img src=x onerror=alert(1)>"},
                "body": "<script>alert(1)</script>",
            },
        ],
    )
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
        history_level="all",
        secure_cookies=False,
        session_cookie=mount[1:] + "_session",
        storage=f"{_storage.name}/admin-state.sqlite3",
        adapters=[
            SQLAdapter(
                engine,
                include_tables=("customers", "entries"),
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
            list_fields=("id", "name", "status", "active", "count", "day", "customer_id"),
            list_editable=("note", "active", "day"),
            fields={
                "name": FieldOptions(label="Name"),
                "customer_id": FieldOptions(relation_label="caption"),
            },
            bulk_actions=(RecordAction("reset", "Reset counters", reset_counter),),
        ),
    )
    admin.configure(
        "customers", options=ModelOptions(record_label="id", search_fields=("caption",))
    )
    admin.mount_fastapi(app, mount)

cursor_admin = Admin(
    auth=PasswordAuth.single_user("admin", "browser-test-password"),
    secret_key="browser-cursor-fixture-" * 3,
    secure_cookies=False,
    session_cookie="cursor_session",
    storage=f"{_storage.name}/cursor-state.sqlite3",
    adapters=[SQLAdapter(engine, include_tables=("entries", "customers"))],
)
cursor_admin.configure(
    "entries",
    options=ModelOptions(pagination="cursor", list_fields=("name", "moment", "count")),
)
cursor_admin.mount_fastapi(app, "/cursor")

values_admin = Admin(
    auth=PasswordAuth.single_user("admin", "browser-test-password"),
    secret_key="browser-values-fixture-" * 3,
    secure_cookies=False,
    session_cookie="values_session",
    storage=f"{_storage.name}/values-state.sqlite3",
    adapters=[SQLAdapter(engine, include_tables=("previews",))],
)
values_admin.configure(
    "previews",
    options=ModelOptions(
        can_edit=False,
        can_create=False,
        can_delete=False,
        record_label="title",
        list_fields=("url", "code", "payload", "body"),
        fields={
            "url": FieldOptions(display="url"),
            "code": FieldOptions(url_template="https://short.example/{value}"),
            "payload": FieldOptions(display="json"),
            "body": FieldOptions(display="multiline"),
        },
    ),
)
values_admin.mount_fastapi(app, "/values")

editing_adapter = SQLAdapter(engine, include_tables=("previews",))


async def rename_preview(operation, payload, *, guard):
    return await editing_adapter.save_checked(
        operation.model,
        operation.key,
        {
            **payload,
            "url": "https://example.test/renamed",
            "payload": {"renamed": True},
            "body": "Updated text\n" + "Long value " * 20,
        },
        {},
        guard=guard,
    )


editing_admin = Admin(
    auth=PasswordAuth.single_user("admin", "browser-test-password"),
    secret_key="browser-edit-values-" * 3,
    secure_cookies=False,
    session_cookie="editing_session",
    storage=f"{_storage.name}/editing-state.sqlite3",
    adapters=[editing_adapter],
)
editing_admin.configure(
    "previews",
    options=ModelOptions(
        create_fields=("title",),
        edit_fields=("title",),
        list_editable=("title",),
        list_fields=("url", "title", "payload", "body"),
        record_label="title",
        update_handler=rename_preview,
        fields={
            "url": FieldOptions(display="url"),
            "payload": FieldOptions(display="json"),
            "body": FieldOptions(display="multiline"),
        },
    ),
)
editing_admin.mount_fastapi(app, "/editing")

# Exercise the stretched row link when its first cell also owns an interactive control.
for first_field in ("name", "active", "customer_id"):
    row_admin = Admin(
        auth=PasswordAuth.single_user("admin", "browser-test-password"),
        secret_key="browser-row-fixture-only-" * 3,
        secure_cookies=False,
        session_cookie=f"row_{first_field}_session",
        storage=f"{_storage.name}/row-{first_field}-state.sqlite3",
        adapters=[SQLAdapter(engine, include_tables=("entries", "customers"))],
    )
    row_admin.configure(
        "entries",
        options=ModelOptions(
            list_fields=(first_field,)
            + tuple(
                field
                for field in ("name", "active", "customer_id", "count")
                if field != first_field
            ),
            list_editable=("name", "active"),
            fields={"customer_id": FieldOptions(relation_label="caption")},
        ),
    )
    row_admin.mount_fastapi(app, f"/rows-{first_field}")
