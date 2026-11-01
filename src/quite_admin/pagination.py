"""Optional count-free keyset reads, independent of database implementations."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .schema import Filter, Query


@dataclass(frozen=True)
class RecordWindow:
    records: list[dict[str, Any]]
    has_next: bool
    has_previous: bool
    next_key: Mapping[str, Any] | None = None
    previous_key: Mapping[str, Any] | None = None


@runtime_checkable
class WindowAdapter(Protocol):
    async def list_window(
        self,
        model: Any,
        query: Query,
        *,
        after: Mapping[str, Any] | None = None,
        before: Mapping[str, Any] | None = None,
    ) -> RecordWindow: ...


def validate_window(schema, query, after, before):
    if after is not None and before is not None:
        raise ValueError("Choose either after or before.")
    if query.offset or query.order_by not in {None, schema.primary_keys[0].name}:
        raise ValueError("Keyset reads require zero offset and primary-key ordering.")
    if query.columns is not None and any(
        field.name not in query.columns for field in schema.primary_keys
    ):
        raise ValueError("Keyset projections must include complete primary keys.")
    boundary = after if after is not None else before
    if boundary is not None:
        schema.validate_key(boundary)
        for name, value in boundary.items():
            Filter(name, "eq", value).validate(schema)


def window_condition(schema, query, boundary, reverse, column):
    if boundary is None:
        return None
    result = prefix = None
    for index, field in enumerate(schema.primary_keys):
        descending = (query.descending if index == 0 else False) != reverse
        expression = (
            column(field.name) < boundary[field.name]
            if descending
            else column(field.name) > boundary[field.name]
        )
        if prefix is not None:
            expression = prefix & expression
        result = expression if result is None else result | expression
        equal = column(field.name) == boundary[field.name]
        prefix = equal if prefix is None else prefix & equal
    return result


def window_ordering(schema, query, reverse, column):
    for index, field in enumerate(schema.primary_keys):
        descending = (query.descending if index == 0 else False) != reverse
        yield column(field.name).desc() if descending else column(field.name).asc()


def finish_window(schema, query, records, after, before):
    extra = len(records) > query.limit
    records = records[: query.limit]
    if before is not None:
        records.reverse()
    has_next = before is not None or extra
    has_previous = extra if before is not None else after is not None

    def key(record):
        return {field.name: record[field.name] for field in schema.primary_keys}

    return RecordWindow(
        records,
        has_next,
        has_previous,
        key(records[-1]) if records and has_next else None,
        key(records[0]) if records and has_previous else None,
    )


class WindowReads:
    async def list_window(self, model, query, *, after=None, before=None):
        return await self._list(model, query, after=after, before=before, window=True)
