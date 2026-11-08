import base64
import hashlib
import json
from dataclasses import replace
from html.parser import HTMLParser

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, Field, ModelOptions, ModelSchema, Page

from .helpers import login


class Document(HTMLParser):
    """Read actual HTML attributes and text, including escaped JSON attributes."""

    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.stack = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        element = {"tag": tag, "attrs": dict(attrs), "parents": tuple(self.stack), "text": []}
        self.elements.append(element)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}:
            self.stack.append(element)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, text):
        for element in self.stack:
            element["text"].append(text)

    def with_attribute(self, name):
        return [element for element in self.elements if name in element["attrs"]]


def catalog(document):
    directories = document.with_attribute("data-table-directory")
    assert len(directories) == 1
    assert directories[0]["attrs"]["id"] == "admin-table-directory"
    assert "hidden" in directories[0]["attrs"]
    assert not any(
        element["tag"] in {"a", "nav", "details"}
        for element in document.elements
        if directories[0] in element["parents"]
    ), "Global metadata must not contain another full native table tree."
    return json.loads(directories[0]["attrs"]["data-catalog"])


def home_catalog(document):
    catalogs = document.with_attribute("data-home-catalog")
    assert len(catalogs) == 1
    native = catalogs[0]
    assert all("hidden" not in element["attrs"] for element in (*native["parents"], native))
    assert any("data-dashboard" in element["attrs"] for element in native["parents"])
    links = [
        element
        for element in document.elements
        if element["tag"] == "a" and native in element["parents"]
    ]
    return native, links


def assert_fixed_rail(document):
    for attribute in (
        "data-sidebar-toggle",
        "data-sidebar-resizer",
        "data-table-directory-region",
        "data-table-directory-trigger",
    ):
        assert not document.with_attribute(attribute)
    assert not any(
        any("sidebar" in parent["attrs"].get("class", "").split() for parent in element["parents"])
        for element in document.with_attribute("data-table-search")
    ), "The fixed icon rail must not retain the removed search button."


def mount(admin, framework):
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host, "/tools/admin")
    return host


def deny_record_operation(*args, **kwargs):
    raise AssertionError("The Home catalog must not read, count, or modify table records.")


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("group", [None, 'Sales <confidential-team> & "operations"'])
async def test_home_has_configured_branding_and_a_native_authorized_table_catalog(
    web_backend, auth, monkeypatch, tmp_path, framework, language, group
):
    adapter, model = web_backend
    logo = tmp_path / "brand.svg"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>')
    options = ModelOptions(
        label='Visible <confidential-table> & "stock"', slug="inventory", group=group
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 48,
        adapters=[adapter],
        secure_cookies=False,
        language=language,
        title="Service <Operations>",
        description='Service <description> & "workspace"',
        logo=logo,
    )
    admin.register(model, options=options)
    for method in ("list", "get", "count", "aggregate", "create", "update", "delete"):
        monkeypatch.setattr(adapter, method, deny_record_operation, raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
    ) as client:
        assert (await client.get("/tools/admin/")).status_code == 303
        await login(client, "/tools/admin")
        response = await client.get("/tools/admin/")
        assert response.status_code == 200, response.text
        document = Document(response.text)
        homes = document.with_attribute("data-dashboard")
        assert len(homes) == 1
        home = homes[0]
        assert admin.title in [
            "".join(element["text"]).strip()
            for element in document.elements
            if element["tag"] == "h1" and home in element["parents"]
        ]
        assert admin.description in "".join(home["text"])
        assert any(
            element["tag"] == "img"
            and element["attrs"].get("src") == "/tools/admin/logo"
            and home in element["parents"]
            for element in document.elements
        )
        assert catalog(document) == [
            {
                "id": "inventory",
                "name": "items",
                "label": options.label,
                "group": group or admin.gettext("Other collections"),
                "url": "/tools/admin/models/inventory/",
            }
        ]
        assert "<confidential-table>" not in response.text
        assert "<confidential-team>" not in response.text
        assert "Service &lt;Operations&gt;" in response.text
        assert "Service &lt;description&gt;" in response.text
        assert_fixed_rail(document)
        native, links = home_catalog(document)
        assert [link["attrs"]["href"] for link in links] == ["/tools/admin/models/inventory/"]
        assert options.label in "".join(links[0]["text"])
        assert (group or admin.gettext("Other collections")) in "".join(native["text"])
        assert any(
            element["tag"] == "details" and native in element["parents"]
            for element in document.elements
        ), "Every authorized group must be operable through native details without JavaScript."
        assert all(
            native in element["parents"]
            for element in document.elements
            if element["tag"] == "a" and "/models/" in element["attrs"].get("href", "")
            if home in element["parents"]
        ), "Server-rendered table links belong only to the Home catalog."
        search = [
            element
            for element in document.with_attribute("data-table-search")
            if home in element["parents"]
        ]
        assert search and all("hidden" in element["attrs"] for element in search)
        for attribute in ("data-home-pinned-section", "data-home-recent-section"):
            sections = document.with_attribute(attribute)
            assert len(sections) == 1 and "hidden" in sections[0]["attrs"]
        for attribute in ("data-home-pinned", "data-home-recent"):
            containers = document.with_attribute(attribute)
            assert len(containers) == 1 and not "".join(containers[0]["text"]).strip()
        assert admin.gettext("Available tables: {count}", count=1) in "".join(home["text"])

        # Rebuilding a response must recheck permissions, not retain an earlier catalog.
        admin.configure(
            "items", options=replace(options, permission=lambda request, identity, action: False)
        )
        denied = await client.get("/tools/admin/")
        assert denied.status_code == 200
        denied_document = Document(denied.text)
        assert catalog(denied_document) == []
        assert home_catalog(denied_document)[1] == []
        for private in ("inventory", "confidential-table", "stock", "confidential-team"):
            assert private not in denied.text


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
@pytest.mark.parametrize("language", ["en", "ru"])
async def test_home_and_inherited_pages_share_catalog_and_hash_trusted_global_scripts(
    web_backend, auth, tmp_path, framework, language
):
    adapter, model = web_backend
    (tmp_path / "report.html").write_text(
        '{% extends "quite_admin/base.html" %}{% block content %}'
        '<h1>{{ page.title }}</h1><output id="catalog-context">{{ table_catalog|tojson }}</output>'
        '<output id="group-count-context">{{ table_group_count }}</output>{% endblock %}'
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 48,
        adapters=[adapter],
        secure_cookies=False,
        language=language,
        templates_dir=tmp_path,
    )
    admin.register(model, options=ModelOptions(slug="inventory", group="Sales"))
    admin.add_page(Page("report", "Report <team>", "report.html"))
    admin.add_page(
        Page("secret-report", "Private report", "report.html", permission=lambda r, i, a: False)
    )
    async with AsyncClient(
        transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
    ) as client:
        signed_out = await client.get("/tools/admin/login")
        assert not Document(signed_out.text).with_attribute("data-table-directory")
        assert "table-navigation.js" not in signed_out.text
        assert "navigation.js" not in signed_out.text
        assert "dashboard.js" not in signed_out.text
        await login(client, "/tools/admin")
        expected_catalog = None
        for path in ("/", "/models/inventory/", "/schema", "/history", "/pages/report"):
            response = await client.get("/tools/admin" + path)
            assert response.status_code == 200, response.text
            document = Document(response.text)
            current_catalog = catalog(document)
            assert_fixed_rail(document)
            topbar = next(
                element
                for element in document.elements
                if "topbar" in element["attrs"].get("class", "").split()
            )
            assert ("hidden" in topbar["attrs"]) is (path == "/")
            brand = next(
                element
                for element in document.elements
                if "service-brand" in element["attrs"].get("class", "").split()
            )
            assert topbar in brand["parents"]
            assert admin.title in "".join(brand["text"])
            crumbs = next(
                element
                for element in document.elements
                if "breadcrumbs" in element["attrs"].get("class", "").split()
            )
            assert not any(
                element["tag"] == "svg" and crumbs in element["parents"]
                for element in document.elements
            )
            if path in {"/schema", "/history"}:
                heading = next(element for element in document.elements if element["tag"] == "h1")
                assert "sr-only" in heading["attrs"].get("class", "").split()
                assert "Who changed what, with field values before and after." not in response.text
            if expected_catalog is None:
                expected_catalog = current_catalog
            assert current_catalog == expected_catalog
            assert "secret-report" not in response.text and "Private report" not in response.text
            assert "Report &lt;team&gt;" in response.text
            native_catalogs = document.with_attribute("data-home-catalog")
            assert len(native_catalogs) == (1 if path == "/" else 0)
            if path != "/":
                assert not document.with_attribute("data-collection-navigation")
                assert not document.with_attribute("data-table-link")
            results = document.with_attribute("data-table-search-results")
            assert len(results) == 1 and not "".join(results[0]["text"]).strip()
            assert not any(
                results[0] in element["parents"] and element["tag"] in {"li", "a", "button"}
                for element in document.elements
            ), "The shared search modal must start without a duplicate table list."
            scripts = {
                element["attrs"]["src"]: element["attrs"]
                for element in document.elements
                if element["tag"] == "script" and "src" in element["attrs"]
            }
            globals = ("table-navigation.js", "navigation.js")
            assert ("/tools/admin/assets/dashboard.js" in scripts) is (path == "/")
            for asset_name in globals + (("dashboard.js",) if path == "/" else ()):
                asset_url = "/tools/admin/assets/" + asset_name
                assert asset_url in scripts
                asset = await client.get(asset_url)
                assert asset.status_code == 200
                digest = (
                    "sha256-" + base64.b64encode(hashlib.sha256(asset.content).digest()).decode()
                )
                assert scripts[asset_url]["integrity"] == digest
                assert scripts[asset_url]["crossorigin"] == "anonymous"
                assert f"'{digest}'" in response.headers["content-security-policy"]
            policy = response.headers["content-security-policy"]
            assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
            assert "'self'" not in policy.split("script-src ")[1].split(";")[0]
            if path == "/pages/report":
                outputs = {
                    element["attrs"].get("id"): "".join(element["text"])
                    for element in document.elements
                    if element["tag"] == "output"
                }
                assert json.loads(outputs["catalog-context"]) == current_catalog
                assert outputs["group-count-context"] == "1"


class MetadataOnlyAdapter:
    def discover(self):
        return [f"table_{index:04d}" for index in range(1994)]

    def describe(self, model):
        return ModelSchema(model, (Field("id", int, primary_key=True),))

    list = get = count = aggregate = create = update = delete = staticmethod(deny_record_operation)


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_large_home_renders_native_authorized_catalog_without_record_queries(auth, framework):
    adapter = MetadataOnlyAdapter()
    admin = Admin(auth=auth, secret_key="s" * 48, adapters=[adapter], secure_cookies=False)
    for index in range(1, 1993):
        admin.configure(f"table_{index:04d}", options=ModelOptions(group=f"Group {index % 20}"))
    admin.configure(
        "table_1993",
        options=ModelOptions(
            label="Restricted table", group="Restricted group", permission=lambda r, i, a: False
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
    ) as client:
        await login(client, "/tools/admin")
        response = await client.get("/tools/admin/")
        assert response.status_code == 200, response.text
        document = Document(response.text)
        tables = catalog(document)
        assert len(tables) == 1993
        assert len({table["group"] for table in tables}) == 21
        assert {table["id"] for table in tables} == {f"table_{index:04d}" for index in range(1993)}
        assert all(table["url"].startswith("/tools/admin/models/") for table in tables)
        assert "Restricted table" not in response.text and "Restricted group" not in response.text
        assert "table_1993" not in response.text
        native, links = home_catalog(document)
        assert len(links) == 1993
        assert {link["attrs"]["href"] for link in links} == {table["url"] for table in tables}
        assert (
            sum(
                element["tag"] == "details" and native in element["parents"]
                for element in document.elements
            )
            == 21
        )
        assert_fixed_rail(document)
