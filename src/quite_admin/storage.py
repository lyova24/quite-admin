"""Library-owned state and activity, independent of business models and their ORM."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Protocol
from urllib.parse import unquote
from uuid import uuid4

from anyio import to_thread

from .activity import MAX_DETAILS_BYTES, ActivityDetails, decode_details, encode_details

TABLE_PREFIX = "quiteadmin_"
SCHEMA_VERSION = 2
MAX_DOCUMENT_BYTES = 1024 * 1024


class StorageError(Exception):
    """Safe public error; connection details and stored data stay out of responses."""

    def __init__(self):
        super().__init__("The admin storage is unavailable.")


class StorageConflict(Exception):
    """The document was changed or deleted by another writer."""


@dataclass(frozen=True)
class Document:
    key: str
    kind: str
    owner: str
    payload: dict[str, Any]
    revision: int = 1
    format_version: int = 1


@dataclass(frozen=True)
class Activity:
    id: str
    occurred_at: str
    subject: str
    display_name: str
    collection: str
    action: str
    outcome: str
    status_code: int
    details: ActivityDetails | None = None

    @classmethod
    def new(cls, *, subject, display_name, collection, action, outcome, status_code, details=None):
        return cls(
            uuid4().hex,
            datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            subject,
            display_name,
            collection,
            action,
            outcome,
            status_code,
            details,
        )


@dataclass(frozen=True)
class ActivityPage:
    events: tuple[Activity, ...]
    has_more: bool


class AdminStore(Protocol):
    async def initialize(self) -> None: ...
    async def get_document(self, key: str) -> Document | None: ...
    async def save_document(
        self, document: Document, *, expected_revision: int = 0
    ) -> Document: ...
    async def delete_document(self, key: str, *, expected_revision: int) -> None: ...
    async def documents(
        self, kind: str, *, owner: str | None = None, after: str = "", limit: int = 100
    ) -> tuple[Document, ...]: ...
    async def append_activity(self, event: Activity) -> None: ...
    async def activities(
        self,
        *,
        collections: tuple[str, ...] | None = None,
        subject: str = "",
        collection: str | None = None,
        action: str = "",
        outcome: str = "",
        before: tuple[str, str] | None = None,
        limit: int = 50,
        changes_only: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ActivityPage: ...
    async def actors(
        self, *, collections: tuple[str, ...], search: str = "", limit: int = 50
    ) -> tuple[tuple[str, str], ...]: ...


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


# Fixed physical schema. New dashboard/widget types are versioned documents,
# not new business models. Every object, including indexes, has the reserved prefix.
_TABLES = (
    "CREATE TABLE IF NOT EXISTS quiteadmin_meta "
    "(name VARCHAR(64) PRIMARY KEY, version INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quiteadmin_documents ("
    "namespace VARCHAR(64) NOT NULL, document_key VARCHAR(64) NOT NULL, "
    "original_key TEXT NOT NULL, kind VARCHAR(100) NOT NULL, owner TEXT NOT NULL, "
    "owner_key VARCHAR(64) NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL, "
    "format_version INTEGER NOT NULL, PRIMARY KEY (namespace, document_key))",
    "CREATE TABLE IF NOT EXISTS quiteadmin_activity ("
    "id VARCHAR(32) PRIMARY KEY, namespace VARCHAR(64) NOT NULL, "
    "occurred_at VARCHAR(27) NOT NULL, subject TEXT NOT NULL, display_name TEXT NOT NULL, "
    "actor_key VARCHAR(64) NOT NULL, collection TEXT NOT NULL, "
    "collection_key VARCHAR(64) NOT NULL, action VARCHAR(100) NOT NULL, "
    "outcome VARCHAR(16) NOT NULL, status_code INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quiteadmin_actors ("
    "namespace VARCHAR(64) NOT NULL, actor_key VARCHAR(64) NOT NULL, "
    "collection_key VARCHAR(64) NOT NULL, subject TEXT NOT NULL, display_name TEXT NOT NULL, "
    "PRIMARY KEY (namespace, actor_key, collection_key))",
    "CREATE TABLE IF NOT EXISTS quiteadmin_activity_details ("
    "activity_id VARCHAR(32) PRIMARY KEY, namespace VARCHAR(64) NOT NULL, payload TEXT NOT NULL)",
)
_INDEXES = {
    "quiteadmin_documents_kind": "quiteadmin_documents (namespace, kind, document_key)",
    "quiteadmin_activity_time": "quiteadmin_activity (namespace, occurred_at, id)",
    "quiteadmin_activity_actor": ("quiteadmin_activity (namespace, actor_key, occurred_at, id)"),
    "quiteadmin_activity_collection": (
        "quiteadmin_activity (namespace, collection_key, occurred_at, id)"
    ),
    "quiteadmin_activity_actor_collection": (
        "quiteadmin_activity (namespace, actor_key, collection_key, occurred_at, id)"
    ),
    "quiteadmin_actors_collection": "quiteadmin_actors (namespace, collection_key, actor_key)",
}


class _RelationalStore:
    def __init__(self, *, namespace="default"):
        if not isinstance(namespace, str) or not namespace or len(namespace) > 200:
            raise ValueError("Use a nonempty storage namespace of at most 200 characters.")
        self.namespace = namespace
        self._namespace = _digest(namespace)
        self._ready = False

    async def _run(self, operation: Callable, *, write=False):
        raise NotImplementedError

    def _schema(self, execute, create_indexes):
        execute(_TABLES[0], {})
        rows = execute("SELECT version FROM quiteadmin_meta WHERE name = 'schema'", {}).rows
        if rows and rows[0]["version"] not in {1, SCHEMA_VERSION}:
            raise StorageError()
        for statement in _TABLES[1:]:
            execute(statement, {})
        create_indexes()
        if not rows:
            execute(
                "INSERT INTO quiteadmin_meta (name, version) VALUES ('schema', :version)",
                {"version": SCHEMA_VERSION},
            )
        elif rows[0]["version"] != SCHEMA_VERSION:
            execute(
                "UPDATE quiteadmin_meta SET version = :version WHERE name = 'schema'",
                {"version": SCHEMA_VERSION},
            )

    async def initialize(self):
        if not self._ready:
            await self._run(lambda execute: None)

    @staticmethod
    def _document(row):
        return Document(
            row["original_key"],
            row["kind"],
            row["owner"],
            json.loads(row["payload"]),
            row["revision"],
            row["format_version"],
        )

    async def get_document(self, key):
        def operation(execute):
            rows = execute(
                "SELECT * FROM quiteadmin_documents "
                "WHERE namespace = :namespace AND document_key = :key",
                {"namespace": self._namespace, "key": _digest(key)},
            ).rows
            return self._document(rows[0]) if rows else None

        return await self._run(operation)

    async def save_document(self, document, *, expected_revision=0):
        if (
            not document.key
            or len(document.key) > 1000
            or not document.kind
            or len(document.kind) > 100
            or not isinstance(document.payload, dict)
            or document.format_version < 1
            or expected_revision < 0
        ):
            raise ValueError("Invalid admin document.")
        payload = json.dumps(document.payload, ensure_ascii=False, allow_nan=False)
        if len(payload.encode()) > MAX_DOCUMENT_BYTES:
            raise ValueError("An admin document exceeds 1 MiB.")
        revision = expected_revision + 1
        params = {
            "namespace": self._namespace,
            "key": _digest(document.key),
            "original_key": document.key,
            "kind": document.kind,
            "owner": document.owner,
            "owner_key": _digest(document.owner),
            "payload": payload,
            "revision": revision,
            "format_version": document.format_version,
            "expected": expected_revision,
        }

        def operation(execute):
            if expected_revision == 0:
                execute(
                    "INSERT INTO quiteadmin_documents "
                    "(namespace, document_key, original_key, kind, owner, owner_key, payload, "
                    "revision, format_version) VALUES (:namespace, :key, :original_key, :kind, "
                    ":owner, :owner_key, :payload, :revision, :format_version)",
                    params,
                )
            else:
                result = execute(
                    "UPDATE quiteadmin_documents SET kind = :kind, owner = :owner, "
                    "owner_key = :owner_key, payload = :payload, revision = :revision, "
                    "format_version = :format_version WHERE namespace = :namespace "
                    "AND document_key = :key AND revision = :expected",
                    params,
                )
                if result.rowcount != 1:
                    raise StorageConflict()
            return Document(
                document.key,
                document.kind,
                document.owner,
                json.loads(payload),
                revision,
                document.format_version,
            )

        return await self._run(operation, write=True)

    async def delete_document(self, key, *, expected_revision):
        if expected_revision < 1:
            raise ValueError("A positive document revision is required.")

        def operation(execute):
            result = execute(
                "DELETE FROM quiteadmin_documents WHERE namespace = :namespace "
                "AND document_key = :key AND revision = :expected",
                {"namespace": self._namespace, "key": _digest(key), "expected": expected_revision},
            )
            if result.rowcount != 1:
                raise StorageConflict()

        await self._run(operation, write=True)

    async def documents(self, kind, *, owner=None, after="", limit=100):
        _limit(limit)
        params = {"namespace": self._namespace, "kind": kind, "after": after, "limit": limit}
        condition = ""
        if owner is not None:
            condition = " AND owner_key = :owner"
            params["owner"] = _digest(owner)

        def operation(execute):
            rows = execute(
                "SELECT * FROM quiteadmin_documents WHERE namespace = :namespace "
                "AND kind = :kind AND document_key > :after"
                + condition
                + " ORDER BY document_key LIMIT :limit",
                params,
            ).rows
            return tuple(self._document(row) for row in rows)

        # A public key is converted to the same stable ordering key used by SQL.
        params["after"] = _digest(after) if after else ""
        return await self._run(operation)

    async def append_activity(self, event):
        if (
            event.outcome not in {"success", "failure"}
            or not event.action
            or len(event.action) > 100
            or not event.subject
            or not 100 <= event.status_code <= 599
        ):
            raise ValueError("Invalid activity event.")
        params = {
            name: getattr(event, name)
            for name in Activity.__dataclass_fields__
            if name != "details"
        }
        payload = encode_details(event.details) if event.details is not None else None
        if payload is not None and len(payload.encode()) > MAX_DETAILS_BYTES:
            raise ValueError("Activity details exceed 512 KiB.")
        params.update(
            namespace=self._namespace,
            actor_key=_digest(event.subject),
            collection_key=_digest(event.collection),
        )

        def operation(execute):
            execute(
                "INSERT INTO quiteadmin_activity "
                "(id, namespace, occurred_at, subject, display_name, "
                "actor_key, collection, collection_key, action, outcome, status_code) VALUES "
                "(:id, :namespace, :occurred_at, :subject, :display_name, :actor_key, :collection, "
                ":collection_key, :action, :outcome, :status_code)",
                params,
            )
            if payload is not None:
                execute(
                    "INSERT INTO quiteadmin_activity_details (activity_id, namespace, payload) "
                    "VALUES (:id, :namespace, :payload)",
                    {"id": event.id, "namespace": self._namespace, "payload": payload},
                )
            # One compact identity per actor/collection, in the event transaction.
            # Autocomplete must not GROUP BY the entire ever-growing activity log.
            upsert = (
                " ON DUPLICATE KEY UPDATE subject = :subject, display_name = :display_name"
                if self._dialect == "mysql"
                else " ON CONFLICT (namespace, actor_key, collection_key) DO UPDATE SET "
                "subject = :subject, display_name = :display_name"
            )
            execute(
                "INSERT INTO quiteadmin_actors "
                "(namespace, actor_key, collection_key, subject, display_name) VALUES "
                "(:namespace, :actor_key, :collection_key, :subject, :display_name)" + upsert,
                params,
            )

        await self._run(operation, write=True)

    def _conditions(self, collections):
        params = {"namespace": self._namespace}
        conditions = ["namespace = :namespace"]
        if collections is not None:
            if not collections:
                conditions.append("1 = 0")
            else:
                names = []
                for index, collection in enumerate(dict.fromkeys(collections)):
                    name = f"collection_{index}"
                    names.append(":" + name)
                    params[name] = _digest(collection)
                conditions.append("collection_key IN (" + ", ".join(names) + ")")
        return conditions, params

    async def activities(
        self,
        *,
        collections=None,
        subject="",
        collection=None,
        action="",
        outcome="",
        before=None,
        limit=50,
        changes_only=False,
        date_from=None,
        date_to=None,
    ):
        _limit(limit)
        if any(value is not None and type(value) is not date for value in (date_from, date_to)):
            raise ValueError("Activity date bounds must be dates.")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("Activity date bounds are reversed.")
        conditions, params = self._conditions(collections)
        if date_from is not None:
            conditions.append("occurred_at >= :date_from")
            params["date_from"] = date_from.isoformat() + "T00:00:00.000000Z"
        if date_to is not None:
            conditions.append("occurred_at <= :date_to")
            params["date_to"] = date_to.isoformat() + "T23:59:59.999999Z"
        if changes_only:
            conditions.append(
                "(action IN ('create', 'edit', 'inline_edit', 'delete') OR action LIKE 'action:%')"
            )
        for column, value in (
            ("actor_key", _digest(subject) if subject else ""),
            ("collection_key", _digest(collection) if collection is not None else ""),
            ("action", action),
            ("outcome", outcome),
        ):
            if value:
                conditions.append(column + " = :" + column)
                params[column] = value
        if before is not None:
            conditions.append("(occurred_at < :time OR (occurred_at = :time AND id < :id))")
            params.update(time=before[0], id=before[1])
        params["limit"] = limit + 1

        def operation(execute):
            rows = execute(
                "SELECT * FROM quiteadmin_activity WHERE "
                + " AND ".join(conditions)
                + " ORDER BY occurred_at DESC, id DESC LIMIT :limit",
                params,
            ).rows
            selected = rows[:limit]
            details = {}
            for offset in range(0, len(selected), 400):
                ids = {
                    f"id_{index}": row["id"]
                    for index, row in enumerate(selected[offset : offset + 400])
                }
                values = execute(
                    "SELECT activity_id, payload FROM quiteadmin_activity_details "
                    "WHERE namespace = :namespace AND activity_id IN ("
                    + ", ".join(":" + name for name in ids)
                    + ")",
                    {**ids, "namespace": self._namespace},
                ).rows
                details.update(
                    {row["activity_id"]: decode_details(row["payload"]) for row in values}
                )
            events = tuple(
                Activity(
                    **{
                        name: row[name]
                        for name in Activity.__dataclass_fields__
                        if name != "details"
                    },
                    details=details.get(row["id"]),
                )
                for row in selected
            )
            return ActivityPage(events, len(rows) > limit)

        return await self._run(operation)

    async def actors(self, *, collections, search="", limit=50):
        _limit(limit)
        conditions, params = self._conditions(collections)
        if search:
            conditions.append(
                "(LOWER(subject) LIKE :search ESCAPE '!' "
                "OR LOWER(display_name) LIKE :search ESCAPE '!')"
            )
            params["search"] = (
                "%" + search.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            )
        params["limit"] = limit

        def operation(execute):
            rows = execute(
                "SELECT subject, MAX(display_name) AS display_name "
                "FROM quiteadmin_actors WHERE "
                + " AND ".join(conditions)
                + " GROUP BY actor_key, subject ORDER BY subject, actor_key LIMIT :limit",
                params,
            ).rows
            return tuple((row["subject"], row["display_name"]) for row in rows)

        return await self._run(operation)


def _limit(value):
    if not isinstance(value, int) or not 1 <= value <= 1000:
        raise ValueError("A storage page must contain between 1 and 1000 items.")


@dataclass
class _Result:
    rows: list[dict]
    rowcount: int


class SQLiteStore(_RelationalStore):
    """File-backed, zero-dependency store. Connections live for one operation."""

    def __init__(self, path: str | Path = ".quite-admin/state.sqlite3", *, namespace="default"):
        super().__init__(namespace=namespace)
        if str(path) == ":memory:":
            raise ValueError("Use a persistent file for the admin SQLite store.")
        self.path = Path(path).expanduser().resolve()
        self._dialect = "sqlite"
        self._lock = threading.Lock()

    async def _run(self, operation, *, write=False):
        return await to_thread.run_sync(self._sync, operation, write)

    @staticmethod
    def _enable_wal(connection):
        # Changing journal mode races across newly started workers. SQLite can
        # report BUSY immediately here despite busy_timeout; retry only this
        # idempotent setup operation, not user writes/transactions.
        deadline = monotonic() + 15
        while True:
            try:
                mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                if mode != "wal":
                    mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if mode != "wal":
                    raise StorageError()
                return
            except sqlite3.OperationalError as exc:
                if (
                    getattr(exc, "sqlite_errorcode", None)
                    not in {
                        sqlite3.SQLITE_BUSY,
                        sqlite3.SQLITE_LOCKED,
                    }
                    or monotonic() >= deadline
                ):
                    raise
                sleep(0.02)

    def _sync(self, operation, write):
        try:
            with self._lock:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                # O_EXCL creates private files without chmod-ing user-owned files.
                try:
                    fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    pass
                else:
                    os.close(fd)
                connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
                connection.row_factory = sqlite3.Row

                def execute(statement, params):
                    cursor = connection.execute(statement, params)
                    rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
                    return _Result(rows, cursor.rowcount)

                try:
                    if not self._ready:
                        self._enable_wal(connection)
                    execute("BEGIN IMMEDIATE" if write or not self._ready else "BEGIN", {})
                    if not self._ready:
                        self._schema(
                            execute,
                            lambda: [
                                execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}", {})
                                for name, target in _INDEXES.items()
                            ],
                        )
                    result = operation(execute)
                    connection.commit()
                    self._ready = True
                    return result
                finally:
                    connection.close()
        except sqlite3.IntegrityError as exc:
            raise StorageConflict() from exc
        except (sqlite3.Error, OSError) as exc:
            raise StorageError() from exc


def create_store(value: AdminStore | str | Path | None) -> AdminStore:
    if value is None:
        value = os.environ.get("QUITE_ADMIN_STORAGE_URL", ".quite-admin/state.sqlite3")
    if isinstance(value, Path):
        return SQLiteStore(value)
    if not isinstance(value, str):
        return value
    if value.startswith("sqlite:///"):
        path = value.removeprefix("sqlite:///")
        if "?" in path or "#" in path:
            raise ValueError("Pass a SQLite file path without URL options.")
        return SQLiteStore(unquote(path))
    if "://" not in value:
        return SQLiteStore(value)
    from .stores.sqlalchemy import SQLAlchemyStore

    return SQLAlchemyStore(value)
