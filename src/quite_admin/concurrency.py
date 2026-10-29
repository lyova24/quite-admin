"""Optional atomic edit preconditions, independent of ORM implementations."""

from __future__ import annotations

import base64
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from .errors import Conflict

STALE_RECORD = (
    "This record changed after you opened it. Your changes have not been saved. "
    "Reload the record and review the latest values."
)


class StaleRecord(Conflict):
    def __init__(self) -> None:
        super().__init__(STALE_RECORD)


def canonical(value: Any) -> str:
    """Stable, type-aware snapshots; never include their contents in logs or cookies."""

    def encode(item):
        if isinstance(item, Enum):
            return ["enum", encode(item.value)]
        if isinstance(item, Mapping):
            return ["map", sorted((str(k), encode(v)) for k, v in item.items())]
        if isinstance(item, (list, tuple)):
            return ["list", [encode(v) for v in item]]
        if isinstance(item, bytes):
            return ["bytes", base64.b64encode(item).decode()]
        if isinstance(item, (datetime, date, time)):
            return [type(item).__name__, item.isoformat()]
        if isinstance(item, (Decimal, UUID)):
            return [type(item).__name__, str(item)]
        if item is None or isinstance(item, (str, int, float, bool)):
            return [type(item).__name__, item]
        raise TypeError("The adapter returned an unsupported revision value.")

    return json.dumps(encode(value), ensure_ascii=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class WriteGuard:
    """Compare freshly read state *inside* the same transaction as the write.

    Custom services implement CheckedAdapter and call these checks after acquiring
    a row lock (or an equivalent compare-and-swap), before mutating any data.
    """

    record_digest: str
    relation_digests: Mapping[str, str]
    fields: tuple[str, ...]
    fingerprint: Callable[[Any], str] = field(repr=False)

    def check_record(self, record: Mapping[str, Any]) -> None:
        actual = self.fingerprint({name: record.get(name) for name in self.fields})
        if not hmac.compare_digest(self.record_digest, actual):
            raise StaleRecord()

    def check_relation(self, name: str, record_keys: Sequence[str]) -> None:
        if name in self.relation_digests:
            actual = self.fingerprint(sorted(record_keys))
            if not hmac.compare_digest(self.relation_digests[name], actual):
                raise StaleRecord()


@runtime_checkable
class CheckedAdapter(Protocol):
    async def save_checked(
        self,
        model: Any,
        key: Mapping[str, Any],
        values: Mapping[str, Any],
        selections: Mapping[str, list[Mapping[str, Any]]],
        *,
        guard: WriteGuard,
    ) -> dict[str, Any]: ...


_guard: ContextVar[tuple[Any, Mapping[str, Any], WriteGuard, set[str]] | None] = ContextVar(
    "quite_admin_write_guard", default=None
)


def guarded() -> bool:
    return _guard.get() is not None


def check_record(model, record) -> None:
    current = _guard.get()
    if (
        current
        and current[0] is model
        and "record" not in current[3]
        and all(record.get(k) == v for k, v in current[1].items())
    ):
        current[2].check_record(record)
        current[3].add("record")


def check_relation(model, name, schema, records) -> None:
    current = _guard.get()
    marker = "relation:" + name
    if current and current[0] is model and marker not in current[3]:
        current[2].check_relation(name, [schema.record_key(row) for row in records])
        current[3].add(marker)


class CheckedWrites:
    """Native adapters check the context inside their existing write transactions."""

    async def save_checked(self, model, key, values, selections, *, guard):
        token = _guard.set((model, key, guard, set()))
        try:
            if selections:
                return await self.save_relations(model, values, selections, key=key)
            return await self.update(model, key, values)
        finally:
            _guard.reset(token)


def sqlite_session_lock(session) -> None:
    if guarded() and session.get_bind().dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
