import html
import re
from datetime import date
from decimal import Decimal
from enum import Enum
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from starlette.datastructures import QueryParams

from quite_admin import Field, ModelOptions, ModelSchema
from quite_admin import filters as ui_filters

from .helpers import login


class Status(Enum):
    OPEN = "open"
    DONE = "done"


def test_filter_controls_preserve_decimal_date_enum_and_null_types():
    resource = SimpleNamespace(
        options=ModelOptions(),
        schema=ModelSchema(
            "items",
            (
                Field("id", int, primary_key=True),
                Field("amount", Decimal),
                Field("day", date),
                Field("status", Status),
                Field("note", str, nullable=True),
                Field("password_hash", str),
            ),
        ),
    )
    fields = ui_filters.controls(resource)
    assert "password_hash" not in {field.name for field in fields}
    filters, errors, active = ui_filters.parse(
        resource,
        fields,
        QueryParams(
            {
                "f.amount.gte": "123456789012345678.123456789",
                "f.day.lte": "2026-10-30",
                "f.status.eq": "done",
                "f.note.is_null": "true",
            }
        ),
    )
    assert not errors
    assert filters[0].value == Decimal("123456789012345678.123456789")
    assert filters[1].value == date(2026, 10, 30)
    assert filters[2].value is Status.DONE and filters[3].value is True
    for params in ({"f.password_hash.eq": "secret"}, {"f.amount.ne": "10"}):
        with pytest.raises(ValueError):
            ui_filters.parse(resource, fields, QueryParams(params))
    _, errors, _ = ui_filters.parse(resource, fields, QueryParams({"f.day.gte": "bad"}))
    assert "f.day.gte" in errors


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_list_filters_combine_and_survive_navigation(admin, backend, framework):
    adapter, model = backend
    await adapter.create(model, {"name": "Row Alpha", "count": 15, "active": False, "note": None})
    await adapter.create(model, {"name": "Row Beta", "count": 18, "active": False, "note": None})
    await adapter.create(model, {"name": "Row Gamma", "count": 16, "active": True, "note": "text"})
    host = FastAPI() if framework == "fastapi" else Litestar()
    if framework == "fastapi":
        admin.mount_fastapi(host)
    else:
        admin.mount_litestar(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        path = "/admin/models/items/"
        params = {
            "f.active.eq": "false",
            "f.count.gte": "10",
            "f.count.lte": "20",
            "f.note.is_null": "true",
            "q": "Row",
            "limit": "1",
            "sort": "count",
        }
        result = await client.get(path, params=params)
        assert result.status_code == 200, result.text
        assert "2 records" in result.text
        body = result.text.split("<tbody>")[1].split("</tbody>")[0]
        assert "Row Alpha" in body and "Row Beta" not in body and "Row Gamma" not in body
        assert "f.internal." not in result.text
        links = [html.unescape(url) for url in re.findall(r'href="([^"]+)"', result.text)]
        sort = next(url for url in links if "sort=name" in url)
        assert all(name + "=" + value in sort for name, value in params.items() if name != "sort")
        next_page = next(url for url in links if "page=2" in url)
        assert "Row Beta" in (await client.get(next_page)).text.split("<tbody>")[1]
        invalid = await client.get(path, params={"f.count.gte": "20", "f.count.lte": "10"})
        assert invalid.status_code == 422 and 'value="10"' in invalid.text
        assert "upper bound" in invalid.text and 'aria-invalid="true"' in invalid.text
        # Inclusive bounds form one editable condition; removing it removes both bounds.
        assert result.text.count("data-filter-edit=") == 3
        range_remove = next(
            url
            for url in links
            if "f.active.eq=false" in url
            and "f.note.is_null=true" in url
            and "page=1" in url
            and "f.count.gte" not in url
            and "f.count.lte" not in url
        )
        assert "sort=count" in range_remove and "limit=1" in range_remove
        for operator, value, expected in (
            ("eq", "15", 1),
            ("gt", "15", 2),
            ("lt", "16", 1),
            ("gte", "16", 2),
            ("lte", "15", 1),
        ):
            response = await client.get(path, params={"q": "Row", "f.count." + operator: value})
            assert response.status_code == 200
            assert f"{expected} " + ("record" if expected == 1 else "records") in response.text
        for bad in (
            {"f.internal.eq": "hidden"},
            {"f.name__contains.eq": "x"},
            {"f.count.raw_sql": "0"},
        ):
            assert (await client.get(path, params=bad)).status_code == 400
        duplicate = await client.get(path + "?f.active.eq=true&f.active.eq=false")
        assert duplicate.status_code == 400
        admin.configure(
            "items", options=ModelOptions(filter_fields=("active",), exclude=("internal",))
        )
        assert (await client.get(path, params={"f.count.gte": "0"})).status_code == 400


def test_exact_decimal_and_comparison_parameters_do_not_lose_precision():
    resource = SimpleNamespace(
        options=ModelOptions(),
        schema=ModelSchema(
            "items",
            (
                Field("id", int, primary_key=True),
                Field("amount", Decimal),
            ),
        ),
    )
    for operator in ("eq", "gt", "gte", "lt", "lte"):
        parsed, errors, active = ui_filters.parse(
            resource,
            ui_filters.controls(resource),
            QueryParams({f"f.amount.{operator}": "123456789012345678.123456789"}),
        )
        assert not errors
        assert parsed[0].value == Decimal("123456789012345678.123456789")
        assert active[0]["value"] == "123456789012345678.123456789"


async def test_filter_assets_are_integrity_checked_and_metadata_is_safe(admin):
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        response = await client.get("/admin/models/items/", params={"f.name.eq": "<script>'&"})
    assert response.status_code == 200
    import base64
    import hashlib
    from pathlib import Path

    digest = base64.b64encode(
        hashlib.sha256(
            (Path(__file__).parents[1] / "src/quite_admin/static/filters.js").read_bytes()
        ).digest()
    ).decode()
    csp = response.headers["content-security-policy"]
    assert f"'sha256-{digest}'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert f'integrity="sha256-{digest}"' in response.text
    assert "data-filter-builder" in response.text
    assert response.text.index("assets/forms.js") < response.text.index("assets/filters.js")
    assert "<script>'&" not in response.text
    assert "\\u003cscript\\u003e" in response.text


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_text_membership_empty_filters_compose_with_search_and_export(
    admin, backend, framework
):
    adapter, model = backend
    await adapter.create(model, {"name": "Alex Smith", "note": "", "count": 9007199254740993})
    await adapter.create(model, {"name": "alex Brown", "note": None, "count": 2})
    await adapter.create(model, {"name": "Other", "note": "", "count": 3})
    app = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        path = "/admin/models/items/"
        result = await client.get(path, params={"f.name.icontains": "Alex", "limit": "1"})
        assert result.status_code == 200 and "2 records" in result.text
        assert "f.name.icontains" in result.text
        assert '"icontains"' in html.unescape(result.text)
        selected = {"f.name.icontains": "Alex", "f.note.is_empty": "true"}
        response = await client.get(path, params={**selected, "export": "csv", "columns": "name"})
        assert response.status_code == 200
        assert "Alex Smith" in response.text and "alex Brown" not in response.text
        result = await client.get(path, params={"f.count.in": '["9007199254740993", "3"]'})
        assert "2 records" in result.text
        result = await client.get(path, params={"f.note.is_empty": "false"})
        assert result.status_code == 200 and "0 records" in result.text
        for params in ({"f.count.in": "bad"}, {"f.count.in": "[]"}, {"f.count.in": "[1]"}):
            assert (await client.get(path, params=params)).status_code == 422
        for params in ({"f.internal.icontains": "hidden"}, {"f.count.icontains": "1"}):
            assert (await client.get(path, params=params)).status_code == 400


def test_whole_day_filters_use_half_open_bounds_and_keep_explicit_timezone():
    from datetime import datetime, timedelta, timezone

    from quite_admin.schema import FILTER_OPERATORS

    resource = SimpleNamespace(
        options=ModelOptions(),
        adapter=SimpleNamespace(supported_filter_operators=FILTER_OPERATORS),
        schema=ModelSchema(
            "events", (Field("id", int, primary_key=True), Field("created", datetime))
        ),
    )
    result, errors, active = ui_filters.parse(
        resource,
        ui_filters.controls(resource),
        QueryParams({"f.created.on": "2026-11-01T00:00:00+03:00"}),
    )
    assert not errors and [item.operator for item in result] == ["gte", "lt"]
    assert result[0].value == datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=3)))
    assert result[1].value == result[0].value + timedelta(days=1)
    assert len(active) == 1
    _, errors, _ = ui_filters.parse(
        resource,
        ui_filters.controls(resource),
        QueryParams({"f.created.on": "2026-11-01T12:00:00"}),
    )
    assert "f.created.on" in errors


def test_custom_adapters_opt_in_to_new_operators():
    resource = SimpleNamespace(
        options=ModelOptions(),
        schema=ModelSchema("items", (Field("id", int, primary_key=True), Field("name", str))),
    )
    with pytest.raises(ValueError):
        ui_filters.parse(
            resource, ui_filters.controls(resource), QueryParams({"f.name.icontains": "Alex"})
        )
    descriptors, _ = ui_filters.presentation(
        ui_filters.controls(resource), [], [], str, ui_filters.supported(resource)
    )
    assert "icontains" not in descriptors[1]["operators"]


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_repeated_conditions_are_independent_and_survive_export(admin, backend, framework):
    adapter, model = backend
    await adapter.create(model, {"name": "Alex Smith", "count": 15})
    await adapter.create(model, {"name": "Alex Brown", "count": 16})
    app = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        path = "/admin/models/items/"
        params = {"f.name.icontains": "Alex", "f.name.icontains~1": "Smith"}
        result = await client.get(path, params=params)
        assert result.status_code == 200 and "1 record" in result.text
        assert result.text.count("data-filter-edit=") == 2
        result = await client.get(path, params={**params, "export": "csv", "columns": "name"})
        assert "Alex Smith" in result.text and "Alex Brown" not in result.text
        result = await client.get(path, params={"f.count.gte~1": "15", "f.count.lte~1": "16"})
        assert result.status_code == 200 and result.text.count("data-filter-edit=") == 1
        result = await client.get(path, params={"f.count.gte~1": "16", "f.count.lte~1": "15"})
        assert result.status_code == 422 and "upper bound" in result.text
        for invalid in (
            {"f.name.icontains~0": "Alex"},
            {"f.name.icontains~51": "Alex"},
            {"f.name.icontains~1": "Alex", "f.name.icontains~1~2": "Smith"},
        ):
            assert (await client.get(path, params=invalid)).status_code == 400
