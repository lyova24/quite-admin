import inspect

import pytest

from quite_admin import DelegatingAdapter, Filter, RelationAdapter
from quite_admin.errors import Conflict, NotFound, ValidationError
from quite_admin.schema import Query


async def test_discovery_crud_search_pagination_and_rollback(backend):
    adapter, model = backend
    discovered = adapter.discover()
    if inspect.isawaitable(discovered):
        discovered = await discovered
    assert model in discovered
    schema = adapter.describe(model)
    assert schema.name == "items"
    assert schema.by_name["active"].kind == "boolean"
    assert schema.by_name["note"].nullable
    assert schema.by_name["id"].generated
    first = await adapter.create(model, {"name": "100% tea", "note": None})
    assert first["active"] is True
    assert first["count"] == 0
    second = await adapter.create(model, {"name": "coffee", "active": False})
    key = schema.parse_key(schema.record_key(first))
    assert await adapter.get(model, key) == first
    updated = await adapter.update(model, key, {"name": "tea", "active": False, "note": "hello"})
    assert updated["note"] == "hello"
    assert updated["active"] is False
    page = await adapter.list(model, Query(limit=1, order_by="name"))
    assert page.total == 2
    assert page.records[0]["id"] == second["id"]
    page2 = await adapter.list(model, Query(limit=1, offset=1, order_by="name"))
    assert page2.records[0]["id"] == first["id"]
    search = await adapter.list(model, Query(search="TEA", search_fields=("name",)))
    assert search.total == 1
    assert search.records[0]["id"] == first["id"]
    with pytest.raises(Conflict):
        await adapter.update(model, key, {"name": "coffee"})
    assert (await adapter.get(model, key))["name"] == "tea"
    with pytest.raises(Conflict):
        await adapter.create(model, {"name": "coffee"})
    await adapter.delete(model, key)
    assert await adapter.get(model, key) is None
    with pytest.raises(NotFound):
        await adapter.delete(model, key)
    with pytest.raises(NotFound):
        await adapter.update(model, key, {"name": "gone"})
    await adapter.create(model, {"name": "still works"})
    assert (await adapter.list(model, Query())).total == 2


async def test_literal_search_wildcards(backend):
    adapter, model = backend
    await adapter.create(model, {"name": "100% tea"})
    await adapter.create(model, {"name": "other"})
    result = await adapter.list(model, Query(search="%", search_fields=("name",)))
    assert result.total == 1


async def test_schema_keys_are_typed(backend):
    adapter, model = backend
    schema = adapter.describe(model)
    record = await adapter.create(model, {"name": "record"})
    assert schema.parse_key(schema.record_key(record)) == {"id": record["id"]}


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ((Filter("count", "eq", 2),), ["b"]),
        ((Filter("count", "lt", 2),), ["a"]),
        ((Filter("count", "lte", 2),), ["a", "b"]),
        ((Filter("count", "gt", 2),), ["c"]),
        ((Filter("count", "gte", 2),), ["b", "c"]),
        ((Filter("count", "in", (1, 3)),), ["a", "c"]),
        ((Filter("count", "in", ()),), []),
        ((Filter("note", "is_null", True),), ["a", "c"]),
        ((Filter("note", "is_null", False),), ["b"]),
        ((Filter("note", "eq", None),), ["a", "c"]),
        ((Filter("count", "gte", 2), Filter("active", "eq", True)), ["c"]),
    ],
)
async def test_typed_filters_and_projection(backend, filters, expected):
    adapter, model = backend
    for count, name in enumerate(("a", "b", "c"), start=1):
        await adapter.create(
            model,
            {
                "name": name,
                "count": count,
                "active": name != "b",
                "note": "present" if name == "b" else None,
            },
        )
    result = await adapter.list(model, Query(filters=filters, columns=("name",), order_by="name"))
    assert result.total == len(expected)
    assert result.records == [{"name": name} for name in expected]


@pytest.mark.parametrize(
    "query",
    [
        Query(filters=(Filter("name", "eq", "x' OR 1=1 --"),), columns=("name",)),
    ],
)
async def test_filter_values_are_bound(backend, query):
    adapter, model = backend
    await adapter.create(model, {"name": "ordinary"})
    assert (await adapter.list(model, query)).total == 0
    assert (await adapter.list(model, Query())).total == 1


@pytest.mark.parametrize(
    "query",
    [
        Query(filters=(Filter("name) OR 1=1", "eq", "x"),)),
        Query(filters=(Filter("name", "raw_sql", "x"),)),
        Query(filters=(Filter("count", "eq", "1 OR 1=1"),)),
        Query(filters=(Filter("count", "in", "1, 2"),)),
        Query(filters=(Filter("name", "is_null", "true"),)),
        Query(columns=("name FROM items; DROP TABLE items",)),
        Query(columns=("unknown",)),
    ],
)
async def test_rejects_filter_operators_and_column_expressions(backend, query):
    adapter, model = backend
    with pytest.raises(ValueError):
        await adapter.list(model, query)


async def test_service_adapter_keeps_writes_behind_business_rules(backend):
    adapter, model = backend
    record = await adapter.create(model, {"name": "ordinary"})

    class ServiceAdapter(DelegatingAdapter):
        async def update(self, model, key, values):
            if values.get("count", 0) < 0:
                raise ValidationError({"count": "The service forbids negative stock."})
            return await super().update(model, key, values)

    service = ServiceAdapter(adapter)
    # Forwarding native save_relations here would bypass the overridden service update.
    assert not isinstance(service, RelationAdapter)
    key = {"id": record["id"]}
    with pytest.raises(ValidationError) as rejected:
        await service.update(model, key, {"count": -1})
    assert "negative stock" in rejected.value.errors["count"]
    assert await service.get(model, key) == record
    assert (await service.update(model, key, {"count": 2}))["count"] == 2


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("icontains", "alex", {"Alex Smith", "alex Brown", "Alice Alex"}),
        ("istartswith", "alex", {"Alex Smith", "alex Brown"}),
        ("iendswith", "alex", {"Alice Alex"}),
        ("not_icontains", "alex", {"A%lex", "A_lex", "A!lex"}),
        ("icontains", "%", {"A%lex"}),
        ("icontains", "_", {"A_lex"}),
        ("icontains", "!", {"A!lex"}),
        ("ne", "Alex Smith", {"alex Brown", "Alice Alex", "A%lex", "A_lex", "A!lex"}),
    ],
)
async def test_text_filter_contract_is_literal_and_case_insensitive(backend, op, value, expected):
    adapter, model = backend
    for name in ("Alex Smith", "alex Brown", "Alice Alex", "A%lex", "A_lex", "A!lex"):
        await adapter.create(model, {"name": name})
    result = await adapter.list(model, Query(filters=(Filter("name", op, value),)))
    assert {row["name"] for row in result.records} == expected
    assert result.total == len(expected)
    # NULL is never silently included by an exclusion predicate.
    result = await adapter.list(model, Query(filters=(Filter("note", "not_icontains", "x"),)))
    assert result.total == 0


async def test_search_key_unions_text_matches_before_counting_and_pagination(backend):
    adapter, model = backend
    exact = await adapter.create(model, {"name": "Identifier match"})
    by_text = await adapter.create(model, {"name": f"Label {exact['id']}"})
    await adapter.create(model, {"name": "Other"})
    options = dict(search=str(exact["id"]), search_fields=("name",), search_key={"id": exact["id"]})
    first = await adapter.list(model, Query(**options, limit=1))
    second = await adapter.list(model, Query(**options, offset=1, limit=1))
    assert first.total == second.total == 2
    assert {first.records[0]["id"], second.records[0]["id"]} == {exact["id"], by_text["id"]}
    for search_key in ({}, {"id": "bad"}, {"secret": 1}):
        with pytest.raises(ValueError):
            await adapter.list(model, Query(search="1", search_key=search_key))


async def test_database_projection_preserves_scalar_types_without_a_primary_key(backend):
    adapter, model = backend
    await adapter.create(
        model, {"name": "Typed", "count": 2**63 - 1, "active": False, "note": None}
    )
    result = await adapter.list(model, Query(columns=("count", "active", "note")))
    assert result.records == [{"count": 2**63 - 1, "active": False, "note": None}]
    assert type(result.records[0]["count"]) is int
    assert type(result.records[0]["active"]) is bool
