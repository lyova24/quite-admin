from __future__ import annotations

from collections.abc import Awaitable, Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from quite_admin.schema import ModelSchema, Query, RecordPage


@runtime_checkable
class Adapter(Protocol):
    """The entire ORM boundary. Return scalar mappings, never lazy ORM objects.

    A synchronous ORM must run a complete unit of work in a worker thread.
    Each write must commit atomically, rollback on failure, and translate expected
    constraint failures to Conflict. The adapter owns its sessions, not the engine.
    """

    def discover(self) -> Iterable[Any] | Awaitable[Iterable[Any]]: ...
    def describe(self, model: Any) -> ModelSchema: ...
    async def list(self, model: Any, query: Query) -> RecordPage: ...
    async def get(self, model: Any, key: Mapping[str, Any]) -> dict[str, Any] | None: ...
    async def create(self, model: Any, values: Mapping[str, Any]) -> dict[str, Any]: ...
    async def update(
        self, model: Any, key: Mapping[str, Any], values: Mapping[str, Any]
    ) -> dict[str, Any]: ...
    async def delete(self, model: Any, key: Mapping[str, Any]) -> None: ...
