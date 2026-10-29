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
        for bad in ({"f.internal.eq": "hidden"}, {"f.name__contains.eq": "x"}, {"f.count.ne": "0"}):
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
    assert f"script-src 'sha256-{digest}'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert f'integrity="sha256-{digest}"' in response.text
    assert "data-filter-builder" in response.text
    assert "<script>'&" not in response.text
    assert "\\u003cscript\\u003e" in response.text
