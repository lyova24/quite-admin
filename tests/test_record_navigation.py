import html
import re
from dataclasses import replace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

from quite_admin import Admin, ModelOptions, RecordAction
from quite_admin.adapters.sql import SQLAdapter

from .helpers import csrf, login, revision


def attribute(page, pattern, name="href"):
    tag = re.search(pattern, page.text)[0]
    return html.unescape(re.search(rf'{name}="([^"]*)"', tag)[1])


@pytest.fixture(params=("fastapi", "litestar"))
async def navigation(request, tmp_path, auth):
    engine = create_engine(f"sqlite:///{tmp_path}/navigation.sqlite3")
    metadata = MetaData()
    people = Table(
        "people", metadata, Column("id", Integer, primary_key=True), Column("name", String(100))
    )
    entries = Table(
        "entries",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
        Column("person_id", ForeignKey("people.id")),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(people.insert(), {"id": 1, "name": "Related person"})
        connection.execute(
            entries.insert(), [{"name": f"Entry {index}", "person_id": 1} for index in range(3)]
        )
    adapter = SQLAdapter(engine)
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)

    async def touch(operation):
        return operation.record

    admin.configure(
        "people",
        options=ModelOptions(relations=(), actions=(RecordAction("touch", "Touch record", touch),)),
    )
    admin.configure(
        "entries",
        options=ModelOptions(
            label="Source entries",
            list_fields=("person_id", "name"),
            relations=(),
        ),
    )
    prefix = "/nested/admin"
    if request.param == "fastapi":
        app = FastAPI()
        admin.mount_fastapi(app, prefix)
    else:
        app = Litestar(route_handlers=[admin.litestar_route(prefix)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client, prefix)
        yield admin, client
    await admin.aclose()
    engine.dispose()


async def test_related_record_returns_to_exact_source_listing_through_form_flows(navigation):
    admin, client = navigation
    source = "/nested/admin/models/entries/?" + urlencode(
        {
            "q": "Entry",
            "f.name.icontains": "Entry",
            "sort": "name",
            "direction": "desc",
            "page": 2,
            "limit": 1,
        }
    )
    listing = await client.get(source)
    assert listing.status_code == 200
    related_url = attribute(listing, r'<a class="relation-value"[^>]*>')
    assert parse_qs(urlsplit(related_url).query) == {"return_to": [source]}
    assert urlsplit(related_url).path.startswith("/nested/admin/models/people/")
    row_url = attribute(listing, r'<a class="record-row-link cell-open"[^>]*>')
    assert parse_qs(urlsplit(row_url).query) == {"return_to": [source]}
    page = await client.get(related_url)
    assert page.status_code == 200
    assert attribute(page, r'<a class="back-link"[^>]*>') == source
    assert f'href="{html.escape(source, quote=True)}">Source entries</a>' in page.text
    assert (
        attribute(page, r'<form method="post"[^>]*class="panel record-form"', "action")
        == related_url
    )
    invalid = await client.post(
        related_url,
        data={
            "__csrf": csrf(page),
            "__revision": revision(page),
            "name": "x" * 101,
        },
    )
    assert invalid.status_code == 422
    assert attribute(invalid, r'<a class="back-link"[^>]*>') == source
    saved = await client.post(
        related_url,
        data={
            "__csrf": csrf(invalid),
            "__revision": revision(invalid),
            "name": "Updated person",
        },
    )
    assert saved.status_code == 303 and saved.headers["location"] == related_url
    page = await client.get(saved.headers["location"])
    assert attribute(page, r'<a class="back-link"[^>]*>') == source
    action_url = attribute(
        page, r'<form method="post" action="[^"]+/actions/touch[^\"]*"', "action"
    )
    action = await client.post(action_url, data={"__csrf": csrf(page)})
    assert action.status_code == 303 and action.headers["location"] == related_url
    legacy = urlsplit(related_url)._replace(path=urlsplit(related_url).path + "/edit").geturl()
    redirected = await client.get(legacy)
    assert redirected.headers["location"] == related_url
    options = admin.collection_options["people"]
    admin.configure("people", options=replace(options, can_edit=False))
    readonly = await client.get(related_url)
    assert attribute(readonly, r'<a class="back-link"[^>]*>') == source
    assert f'href="{html.escape(source, quote=True)}">Back</a>' in readonly.text
    row_page = await client.get(row_url)
    delete_url = attribute(row_page, r'<a class="button danger-outline"[^>]*>')
    confirmation = await client.get(delete_url)
    assert attribute(confirmation, r'<a class="back-link"[^>]*>') == source
    assert f'href="{html.escape(source, quote=True)}">Keep record</a>' in confirmation.text
    deleted = await client.post(delete_url, data={"__csrf": csrf(confirmation)})
    assert deleted.status_code == 303 and deleted.headers["location"] == source


async def test_related_record_preserves_signed_cursor_page_on_return(navigation):
    admin, client = navigation
    admin.configure(
        "entries", options=replace(admin.collection_options["entries"], pagination="cursor")
    )
    first = await client.get(
        "/nested/admin/models/entries/?q=Entry&sort=name&direction=desc&limit=1"
    )
    source = attribute(first, r'<a class="button secondary small"[^>]*>')
    assert parse_qs(urlsplit(source).query)["after"]
    listing = await client.get(source)
    assert listing.status_code == 200
    related = attribute(listing, r'<a class="relation-value"[^>]*>')
    assert parse_qs(urlsplit(related).query)["return_to"] == [source]
    page = await client.get(related)
    back = attribute(page, r'<a class="back-link"[^>]*>')
    assert back == source
    restored = await client.get(back)
    assert restored.status_code == 200
    assert "Entry 1" in restored.text


@pytest.mark.parametrize(
    "target",
    (
        "https://evil.test/nested/admin/models/entries/",
        "//evil.test/",
        " /nested/admin/models/entries/",
        "/nested/admin/models/entries/ ",
        "/other/admin/models/entries/",
        "/nested/admin/models/entries/../people/",
        "/nested/admin/models/entries/%2e%2e/people/",
        "/nested/admin/models/entries/\\evil",
        "/nested/admin/models/entries/#fragment",
        "/nested/admin/models/entries/\r\nLocation:evil",
        "/nested/admin/models/missing/",
        "/nested/admin/models/entries/new",
    ),
)
async def test_return_context_rejects_external_or_nonlisting_destinations(navigation, target):
    _, client = navigation
    listing = await client.get("/nested/admin/models/entries/")
    url = urlsplit(attribute(listing, r'<a class="relation-value"[^>]*>')).path
    page = await client.get(url, params={"return_to": target})
    assert page.status_code == 200
    assert attribute(page, r'<a class="back-link"[^>]*>') == "/nested/admin/models/people/"
    assert attribute(page, r'<form method="post"[^>]*class="panel record-form"', "action") == url


async def test_return_context_rechecks_source_permissions_and_rejects_duplicates(navigation):
    admin, client = navigation
    source = "/nested/admin/models/entries/?q=Entry&page=2&limit=1"
    listing = await client.get(source)
    related = attribute(listing, r'<a class="relation-value"[^>]*>')
    path = urlsplit(related).path
    duplicate = await client.get(path, params=[("return_to", source), ("return_to", source)])
    assert attribute(duplicate, r'<a class="back-link"[^>]*>') == "/nested/admin/models/people/"
    admin.configure(
        "entries",
        options=replace(
            admin.collection_options["entries"],
            permission=lambda request, identity, action: action != "list",
        ),
    )
    denied = await client.get(related)
    assert denied.status_code == 200
    assert attribute(denied, r'<a class="back-link"[^>]*>') == "/nested/admin/models/people/"
    # The normal source listing still enforces its own authorization on return.
    assert (await client.get(source)).status_code == 403
    client.cookies.clear()
    anonymous = await client.get(related)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/nested/admin/login"
