import re
from html.parser import HTMLParser

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import FieldOptions, ModelOptions

from .helpers import csrf, login, revision


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.nested = False
        self.external = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.nested |= bool(self.depth)
            self.depth += 1
            data = dict(attrs)
            if data.get("target") == "_blank":
                self.external.append(data)

    def handle_endtag(self, tag):
        if tag == "a":
            self.depth -= 1


@pytest.fixture(params=["fastapi", "litestar"])
async def display_client(request, web_admin):
    host = FastAPI() if request.param == "fastapi" else Litestar()
    getattr(web_admin, "mount_" + request.param)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        yield client


async def test_url_display_uses_formatter_without_nested_links_or_inline_write(
    display_client, web_admin, web_backend
):
    adapter, model = web_backend
    row = await adapter.create(model, {"name": "short-code"})
    web_admin.configure(
        "items",
        options=ModelOptions(
            list_fields=("name",),
            fields={
                "name": FieldOptions(
                    display="url", formatter=lambda value: "https://example.test/" + value
                )
            },
        ),
    )
    listing = await display_client.get("/admin/models/items/")
    links = Links()
    links.feed(listing.text)
    assert not links.nested
    assert len(links.external) == 1
    assert links.external[0]["href"] == "https://example.test/short-code"
    assert "noopener" in links.external[0]["rel"] and "noreferrer" in links.external[0]["rel"]
    assert "data-inline-endpoint=" not in listing.text
    assert "values.js" in listing.text
    script = re.search(r'<script[^>]+src="[^"]+/values.js"[^>]+integrity="([^"]+)"', listing.text)
    assert script and script[1] in listing.headers["content-security-policy"]
    key = adapter.describe(model).record_key(row)
    form = await display_client.get(f"/admin/models/items/{key}")
    assert 'class="field-url-preview"' in form.text
    assert 'name="name"' in form.text
    assert (await display_client.get(f"/admin/models/items/{key}/inline/name")).status_code == 403


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//example.test/x",
        "https://",
        "https://exa\nmple.test",
        'https://example.test/" onclick="alert(1)',
    ],
)
async def test_url_scheme_restriction_and_escaped_values(
    display_client, web_admin, web_backend, value
):
    adapter, model = web_backend
    await adapter.create(model, {"name": value})
    web_admin.configure(
        "items",
        options=ModelOptions(list_fields=("name",), fields={"name": FieldOptions(display="url")}),
    )
    page = await display_client.get("/admin/models/items/")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    links = Links()
    links.feed(page.text)
    assert all(item["href"].startswith(("https://", "http://")) for item in links.external)
    assert all("onclick" not in item for item in links.external)
    if not value.startswith("https://example.test/"):
        assert not links.external
    assert not links.nested


async def test_json_and_multiline_readonly_displays_keep_writes_and_exports_plain(
    display_client, web_admin, web_backend
):
    adapter, model = web_backend
    value = '{"hello":"Привет","nested":[1,2]}'
    row = await adapter.create(model, {"name": "JSON", "note": value, "internal": "hidden-value"})
    web_admin.configure(
        "items",
        options=ModelOptions(
            list_fields=("name", "note"),
            exclude=("internal",),
            fields={"note": FieldOptions(display="json"), "internal": FieldOptions(display="url")},
        ),
    )
    page = await display_client.get("/admin/models/items/")
    assert 'data-field-display="json"' in page.text
    assert 'class="value-details"' in page.text
    assert "  &#34;hello&#34;: &#34;Привет&#34;" in page.text
    assert "hidden-value" not in page.text
    export = await display_client.get("/admin/models/items/?export=csv&columns=note")
    assert "data-copy" not in export.text
    assert '""hello"":""Привет""' in export.text
    path = "/admin/models/items/" + adapter.describe(model).record_key(row)
    web_admin.configure(
        "items",
        options=ModelOptions(fields={"note": FieldOptions(display="multiline", read_only=True)}),
    )
    readonly = await display_client.get(path)
    assert 'data-field-display="multiline"' in readonly.text
    assert "data-copy-source" in readonly.text
    web_admin.configure(
        "items",
        options=ModelOptions(edit_fields=("note",), fields={"note": FieldOptions(display="json")}),
    )
    form = await display_client.get(path)
    updated = await display_client.post(
        path,
        data={
            "__csrf": csrf(form),
            "__revision": revision(form),
            "note": "still an ordinary string",
        },
    )
    assert updated.status_code == 303
    assert (await adapter.get(model, {"id": row["id"]}))["note"] == "still an ordinary string"


def test_unknown_display_rejected(web_backend):
    adapter, model = web_backend
    with pytest.raises(ValueError, match="display must"):
        ModelOptions(fields={"name": FieldOptions(display="html")}).validate(
            adapter.describe(model)
        )


async def test_url_template_is_presentation_only_and_encodes_values(
    display_client, web_admin, web_backend
):
    adapter, model = web_backend
    row = await adapter.create(model, {"name": "abc/123?x=1"})
    web_admin.configure(
        "items",
        options=ModelOptions(
            list_fields=("name",),
            edit_fields=("name",),
            fields={"name": FieldOptions(url_template="https://short.example/{value}")},
        ),
    )
    page = await display_client.get("/admin/models/items/")
    assert 'href="https://short.example/abc%2F123%3Fx%3D1"' in page.text
    exported = await display_client.get("/admin/models/items/?export=csv&columns=name")
    assert "abc/123?x=1" in exported.text
    assert "short.example" not in exported.text
    path = "/admin/models/items/" + adapter.describe(model).record_key(row)
    form = await display_client.get(path)
    assert 'value="abc/123?x=1"' in form.text
    result = await display_client.post(
        path, data={"__csrf": csrf(form), "__revision": revision(form), "name": "next/code"}
    )
    assert result.status_code == 303
    assert (await adapter.get(model, {"id": row["id"]}))["name"] == "next/code"
    changed = (await web_admin.storage.activities()).events[0].details.changes
    assert any(item.after == "next/code" for item in changed)
    assert all("short.example" not in (item.after or "") for item in changed)


@pytest.mark.parametrize(
    "template",
    [
        "javascript:{value}",
        "https://example.test/{other}",
        "https://example.test/",
        "https://example.test/{value.__class__}",
    ],
)
def test_url_template_configuration_is_validated(web_backend, template):
    adapter, model = web_backend
    with pytest.raises(ValueError, match="url_template"):
        ModelOptions(fields={"name": FieldOptions(url_template=template)}).validate(
            adapter.describe(model)
        )
