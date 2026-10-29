import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from litestar.logging import LoggingConfig
from litestar.middleware.logging import LoggingMiddlewareConfig

from quite_admin import ModelOptions, Page

from .helpers import csrf, login


@pytest.fixture(params=["fastapi", "litestar", "litestar_logging"])
def host(request, admin):
    if request.param == "fastapi":
        app = FastAPI()
        admin.mount_fastapi(app)
    elif request.param == "litestar":
        app = Litestar(route_handlers=[admin.litestar_route()], debug=True)
    else:
        # Exercise the real middleware's default body-reading behavior, with a
        # silent sink because bodies include credentials and CSRF in this test.
        config = LoggingConfig(
            logging_module="logging",
            handlers={"silent": {"class": "logging.NullHandler"}},
            loggers={"litestar": {"handlers": ["silent"], "propagate": False}},
            root={"handlers": ["silent"], "level": "INFO"},
        )
        app = Litestar(
            route_handlers=[admin.litestar_route()],
            logging_config=config,
            middleware=[LoggingMiddlewareConfig().middleware],
        )
    return app


@pytest.fixture
async def client(host):
    async with AsyncClient(
        transport=ASGITransport(app=host), base_url="http://testserver"
    ) as client:
        yield client


async def test_full_browser_flow(client):
    response = await client.get("/admin/models/items/")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
    await login(client)
    home = await client.get("/admin/")
    assert home.status_code == 200, home.text
    assert "/admin/models/items/" in home.text
    assert (await client.get("/admin/assets/admin.css")).status_code == 200
    create = await client.get("/admin/models/items/new")
    assert create.status_code == 200, create.text
    assert 'name="internal"' not in create.text
    assert 'name="count"' not in create.text
    result = await client.post(
        "/admin/models/items/new",
        data={
            "__csrf": csrf(create),
            "name": "A cup of tea",
            "active": "true",
            "note": "",
        },
    )
    assert result.status_code == 303, result.text
    detail_url = result.headers["location"]
    assert detail_url.startswith("/admin/models/items/")
    detail = await client.get(detail_url)
    assert detail.status_code == 200, detail.text
    assert "A cup of tea" in detail.text
    edit = await client.get(detail_url)
    assert edit.status_code == 200
    result = await client.post(
        detail_url,
        data={
            "__csrf": csrf(edit),
            "name": "<script>alert(1)</script>",
            "active": "false",
            "note": "ok",
        },
    )
    assert result.status_code == 303, result.text
    listing = await client.get("/admin/models/items/?q=script&sort=name&direction=desc&limit=1")
    assert listing.status_code == 200, listing.text
    assert "&lt;script&gt;" in listing.text
    assert "<script>" not in listing.text
    assert "no-store" in listing.headers["cache-control"]
    assert "script-src 'none'" in listing.headers["content-security-policy"]
    confirm = await client.get(detail_url + "/delete")
    assert confirm.status_code == 200
    assert (await client.get(detail_url)).status_code == 200  # GET never deletes.
    deleted = await client.post(detail_url + "/delete", data={"__csrf": csrf(confirm)})
    assert deleted.status_code == 303
    assert (await client.get(detail_url)).status_code == 404
    listing = await client.get("/admin/models/items/")
    assert "0 records" in listing.text
    result = await client.post("/admin/logout", data={"__csrf": csrf(listing)})
    assert result.status_code == 303
    assert (await client.get("/admin/")).status_code == 303


async def test_csrf_mass_assignment_and_validation(client):
    login_form = await client.get("/admin/login")
    assert (await client.post("/admin/login", data={"username": "admin"})).status_code == 403
    bad = await client.post(
        "/admin/login",
        data={
            "__csrf": csrf(login_form),
            "username": "admin",
            "password": "wrong",
        },
    )
    assert bad.status_code == 401
    await login(client)
    form = await client.get("/admin/models/items/new")
    base = {"__csrf": csrf(form), "name": "first", "active": "true"}
    for extra in (
        {"count": "100"},
        {"internal": "exposed"},
        {"id": "100"},
        {"wat": "x"},
        {"__default__count": "true"},
    ):
        response = await client.post("/admin/models/items/new", data={**base, **extra})
        assert response.status_code == 422, response.text
    response = await client.post("/admin/models/items/new", data={**base, "active": "perhaps"})
    assert response.status_code == 422
    assert (
        await client.post("/admin/models/items/new", data={**base, "__csrf": "wrong"})
    ).status_code == 403
    assert (await client.post("/admin/models/items/new", data=base)).status_code == 303
    duplicate = await client.post("/admin/models/items/new", data=base)
    assert duplicate.status_code == 409
    assert "constraint" in duplicate.text
    valid = await client.post("/admin/models/items/new", data={**base, "name": "after conflict"})
    assert valid.status_code == 303
    assert (await client.get("/admin/models/items/?sort=internal")).status_code == 400
    assert (await client.get("/admin/models/items/?page=wat")).status_code == 400
    assert (await client.get("/admin/models/items/not-a-valid-key")).status_code == 404
    assert (await client.post("/admin/models/items/new", json=base)).status_code == 415


async def test_permissions_checked_for_direct_requests(client, admin, backend):
    adapter, model = backend
    record = await adapter.create(model, {"name": "visible"})
    key = adapter.describe(model).record_key(record)
    admin.register(
        model,
        options=ModelOptions(
            can_create=False,
            can_delete=False,
            permission=lambda request, identity, action: action in {"list", "view"},
        ),
    )
    await login(client)
    listing = await client.get("/admin/models/items/")
    assert "Create record" not in listing.text
    assert (await client.get("/admin/models/items/new")).status_code == 403
    assert (await client.get(f"/admin/models/items/{key}/edit")).status_code == 403
    assert (await client.post(f"/admin/models/items/{key}/delete", data={})).status_code == 403
    assert (await client.get(f"/admin/models/items/{key}")).status_code == 200


async def test_one_record_page_handles_editing_and_read_only_access(client, admin, backend):
    adapter, model = backend
    record = await adapter.create(model, {"name": "A single record page"})
    key = adapter.describe(model).record_key(record)
    path = f"/admin/models/items/{key}"
    await login(client)
    page = await client.get(path)
    assert page.status_code == 200
    assert f'action="{path}"' in page.text
    assert 'name="name"' in page.text and "Save changes" in page.text
    legacy = await client.get(path + "/edit")
    assert legacy.status_code == 303 and legacy.headers["location"] == path
    saved = await client.post(path, data={"__csrf": csrf(page), "name": "Updated in place"})
    assert saved.status_code == 303 and saved.headers["location"] == path
    admin.register(
        model, options=ModelOptions(can_edit=False, can_delete=False, exclude=("internal",))
    )
    readonly = await client.get(path)
    assert readonly.status_code == 200
    assert "Updated in place" in readonly.text
    assert 'name="name"' not in readonly.text
    assert "Save changes" not in readonly.text
    rejected = await client.post(path, data={"__csrf": csrf(readonly), "name": "Not allowed"})
    assert rejected.status_code == 403
    assert (await adapter.get(model, adapter.describe(model).parse_key(key)))[
        "name"
    ] == "Updated in place"


async def test_custom_templates_pages_are_authenticated(client, admin, tmp_path):
    from jinja2 import FileSystemLoader

    (tmp_path / "report.html").write_text(
        '{% extends "quite_admin/base.html" %}{% block content %}'
        "<h1>{{ page.title }}</h1><p>{{ count }}</p><p>{{ example }}</p>{% endblock %}"
    )
    admin.templates.env.loader.loaders.insert(0, FileSystemLoader(tmp_path))

    async def context(request):
        assert request.state.identity.subject == "admin"
        return {"count": 42, "example": "<b>escaped</b>"}

    admin.add_page(Page("report", "Weekly report", "report.html", context=context))
    admin.add_page(Page("private", "Hidden", "report.html", permission=lambda *args: False))
    assert (await client.get("/admin/pages/report")).status_code == 303
    await login(client)
    report = await client.get("/admin/pages/report")
    assert report.status_code == 200, report.text
    assert "Weekly report" in report.text
    assert "42" in report.text
    assert "&lt;b&gt;escaped&lt;/b&gt;" in report.text
    assert "/admin/pages/private" not in report.text
    assert (await client.get("/admin/pages/private")).status_code == 403
    assert (await client.get("/admin/pages/missing")).status_code == 404
