import inspect

import pytest

from quite_admin.errors import Conflict, NotFound
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
