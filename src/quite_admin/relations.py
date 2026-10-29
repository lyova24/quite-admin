"""Optional relationship contract, independent of templates and ORM classes."""

from __future__ import annotations

from collections.abc import Awaitable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from .schema import Field, Query, RecordPage


@dataclass(frozen=True)
class Junction:
    name: str
    fields: tuple[Field, ...]
    source_fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    model: Any = None


@dataclass(frozen=True)
class Relation:
    name: str
    target: Any
    kind: Literal["one_to_one", "many_to_one", "one_to_many", "many_to_many"]
    source_fields: tuple[str, ...] = ()
    target_fields: tuple[str, ...] = ()
    can_detach: bool = True
    read_only: bool = False
    mutates_target: bool = False
    source_key_fields: tuple[str, ...] = ()
    target_key_fields: tuple[str, ...] = ()
    through: str | None = None
    junction: Junction | None = None

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@runtime_checkable
class RelationAdapter(Protocol):
    """Optional extension to Adapter. A relationship write is one atomic unit of work.

    Targets must exist; detaching an unrelated target must not change either row.
    Never interpret submitted names as ORM expressions or delete target records.
    """

    def relations(self, model: Any) -> Iterable[Relation] | Awaitable[Iterable[Relation]]: ...
    async def related(
        self, model: Any, name: str, key: Mapping[str, Any], query: Query
    ) -> RecordPage: ...
    async def save_relations(
        self,
        model: Any,
        values: Mapping[str, Any],
        selections: Mapping[str, list[Mapping[str, Any]]],
        *,
        key: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...
