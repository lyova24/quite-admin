import csv
import io
from xml.etree.ElementTree import fromstring
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, ModelOptions, exports
from quite_admin.relations import RelationAdapter

from .helpers import login
from .test_relations import related_backend  # noqa: F401, F811


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
@pytest.mark.parametrize("format", ["csv", "xlsx"])
async def test_filtered_export_all_pages_and_literal_cells(admin, backend, framework, format):
    adapter, model = backend
    await adapter.create(model, {"name": '=HYPERLINK("bad")', "count": 9007199254740993})
    await adapter.create(model, {"name": "Other", "count": 3})
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        params = [
            ("export", format),
            ("columns", "name"),
            ("columns", "count"),
            ("f.count.gte", "4"),
            ("limit", "1"),
            ("page", "999"),
        ]
        response = await client.get("/admin/models/items/", params=params)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert f'filename="items.{format}"' in response.headers["content-disposition"]
        if format == "csv":
            rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
            assert rows == [["name", "count"], ['\'=HYPERLINK("bad")', "9007199254740993"]]
        else:
            with ZipFile(io.BytesIO(response.content)) as archive:
                xml = fromstring(archive.read("xl/worksheets/sheet1.xml"))
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                assert not xml.findall(".//s:f", ns)
                assert [item.text for item in xml.findall(".//s:t", ns)] == [
                    "name",
                    "count",
                    '=HYPERLINK("bad")',
                    "9007199254740993",
                ]
                for name in archive.namelist():
                    fromstring(archive.read(name))
        for extra in [
            [("columns", "internal")],
            [("columns", "name"), ("columns", "name")],
            [("columns", "missing")],
            [],
        ]:
            invalid = await client.get("/admin/models/items/", params=[("export", format), *extra])
            assert invalid.status_code == 400
        bad_filter = await client.get(
            "/admin/models/items/",
            params={"export": format, "columns": "name", "f.count.gte": "invalid"},
        )
        assert bad_filter.status_code == 422
        unsupported = await client.get(
            "/admin/models/items/", params={"export": "json", "columns": "name"}
        )
        assert unsupported.status_code == 400


async def test_export_requires_auth_view_and_rejects_truncation(admin, backend, monkeypatch):
    adapter, model = backend
    for name in ("One", "Two"):
        await adapter.create(model, {"name": name})
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        path = "/admin/models/items/?export=csv&columns=name"
        assert (await client.get(path)).status_code == 303
        await login(client)
        monkeypatch.setattr(exports, "MAX_ROWS", 1)
        assert (await client.get(path)).status_code == 413
        admin.configure("items", options=ModelOptions(permission=lambda r, i, a: a != "view"))
        assert (await client.get(path)).status_code == 403
        assert 'class="export-panel' not in (await client.get("/admin/models/items/")).text


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_export_related_columns_and_target_permissions(related_backend, auth, framework):  # noqa: F811
    adapter, models = related_backend
    parent = await adapter.create(models["parents"], {"name": "Parent"})
    fk = next(f.name for f in adapter.describe(models["children"]).fields if f.foreign_key)
    for name in ("Alpha", "Beta"):
        await adapter.create(models["children"], {"name": name, fk: parent["id"]})
    relation = next(
        item for item in adapter.relations(models["parents"]) if item.target is models["children"]
    )
    assert isinstance(adapter, RelationAdapter)
    admin = Admin(auth=auth, secret_key="s" * 48, adapters=[adapter], secure_cookies=False)
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        params = [("export", "csv"), ("columns", "name"), ("columns", relation.name + ".name")]
        response = await client.get("/admin/models/parents/", params=params)
        assert response.status_code == 200, response.text
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert rows[1] == ["Parent", "Alpha\nBeta"]
        admin.configure("children", options=ModelOptions(exclude=("name",)))
        assert (await client.get("/admin/models/parents/", params=params)).status_code == 400
        admin.configure("children", options=ModelOptions(permission=lambda r, i, a: a != "view"))
        assert (await client.get("/admin/models/parents/", params=params)).status_code == 400


def test_export_size_limits_and_csv_formula_escaping(monkeypatch):
    values = ["=1", " +1", "@cmd", "\tdata", "\n=1", "text,with\nnewline"]
    response = exports.download("items", "csv", ["name"], [[value] for value in values])
    rows = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
    assert [row[0] for row in rows[1:]] == ["'" + value for value in values[:-1]] + values[-1:]
    from starlette.exceptions import HTTPException

    with pytest.raises(HTTPException) as exc:
        exports.download("items", "xlsx", ["name"], [["🙂" * 16384]])
    assert exc.value.status_code == 413
    monkeypatch.setattr(exports, "MAX_BYTES", 1)
    with pytest.raises(HTTPException) as exc:
        exports.download("items", "csv", ["name"], [["too long"]])
    assert exc.value.status_code == 413
