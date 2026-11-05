"""Optional count-free keyset reads, independent of database implementations."""

from collections.abc import Mapping
from dataclasses import dataclass
from operator import eq, ne
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


def window_fields(schema, query):
    order = query.order_by or schema.primary_keys[0].name
    return (schema.by_name[order],) + tuple(
        field for field in schema.primary_keys if field.name != order
    )


def validate_window(schema, query, after, before):
    if after is not None and before is not None:
        raise ValueError("Choose either after or before.")
    if query.offset:
        raise ValueError("Keyset reads require zero offset.")
    fields = window_fields(schema, query)
    if fields[0].kind in {"json", "binary", "unsupported", "password"}:
        raise ValueError("This field does not support cursor ordering.")
    if query.columns is not None and any(field.name not in query.columns for field in fields):
        raise ValueError("Keyset projections must include primary keys and the sort field.")
    boundary = after if after is not None else before
    if boundary is not None:
        if set(boundary) != {field.name for field in fields}:
            raise ValueError("Keyset boundaries must include primary keys and the sort field.")
        schema.validate_key({field.name: boundary[field.name] for field in schema.primary_keys})
        for name, value in boundary.items():
            if value is None:
                if not schema.by_name[name].nullable:
                    raise ValueError("A non-nullable cursor field cannot be NULL.")
            else:
                Filter(name, "eq", value).validate(schema)


def window_condition(schema, query, boundary, reverse, column):
    if boundary is None:
        return None
    result = prefix = None
    for index, field in enumerate(window_fields(schema, query)):
        descending = (query.descending if index == 0 else False) != reverse
        value = boundary[field.name]
        target = column(field.name)
        # Forward traversal always puts NULL last; reverse traversal inverts it.
        expression = ne(target, None) if value is None and reverse else None
        if value is not None:
            expression = target < value if descending else target > value
            if field.nullable and not reverse:
                expression = expression | eq(target, None)
        if expression is not None:
            if prefix is not None:
                expression = prefix & expression
            result = expression if result is None else result | expression
        equal = eq(target, value)
        prefix = equal if prefix is None else prefix & equal
    return result


def window_ordering(schema, query, reverse, column):
    for index, field in enumerate(window_fields(schema, query)):
        descending = (query.descending if index == 0 else False) != reverse
        if field.nullable:
            null = eq(column(field.name), None)
            yield null.desc() if reverse else null.asc()
        yield column(field.name).desc() if descending else column(field.name).asc()


def finish_window(schema, query, records, after, before):
    extra = len(records) > query.limit
    records = records[: query.limit]
    if before is not None:
        records.reverse()
    has_next = before is not None or extra
    has_previous = extra if before is not None else after is not None

    def key(record):
        return {field.name: record[field.name] for field in window_fields(schema, query)}

    return RecordWindow(
        records,
        has_next,
        has_previous,
        key(records[-1]) if records and has_next else None,
        key(records[0]) if records and has_previous else None,
    )


class WindowReads:
    supports_window_sorting = True

    async def list_window(self, model, query, *, after=None, before=None):
        return await self._list(model, query, after=after, before=before, window=True)
