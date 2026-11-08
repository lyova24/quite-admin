"""Compatibility failures must be actionable before an extension reaches production."""

import inspect
import subprocess
import sys

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

import quite_admin
from quite_admin import (
    TEMPLATE_API_VERSION,
    Admin,
    Field,
    FieldOptions,
    ModelOptions,
    Page,
    Query,
    RecordPage,
)
from quite_admin.adapters.base import Adapter
from quite_admin.concurrency import StaleRecord
from quite_admin.errors import AdminError, Conflict, NotFound, ValidationError
from scripts.check_api import check

from .helpers import csrf, login


def test_public_contracts_match_the_committed_baseline():
    assert check() == []
    assert check(profile="modern") == []


@pytest.mark.parametrize("parameter", ["primary", "on_primary", "on_danger"])
def test_theme_default_migration_does_not_allow_other_default_changes(monkeypatch, parameter):
    original = inspect.signature(quite_admin.Theme)
    parameters = [
        item.replace(default="#123456") if item.name == parameter else item
        for item in original.parameters.values()
    ]
    monkeypatch.setattr(
        quite_admin.Theme, "__signature__", original.replace(parameters=parameters), raising=False
    )
    assert f"quite_admin:Theme.{parameter}: changed default" in check()


def test_core_import_does_not_load_an_orm():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, quite_admin; "
            "orms = {'sqlalchemy', 'sqlmodel', 'peewee', 'tortoise', 'gino'}; "
            "assert not orms & sys.modules.keys()",
        ],
        check=True,
    )


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_legacy_ui_macro_overrides_do_not_require_new_rail_macros(auth, tmp_path, framework):
    templates = tmp_path / "quite_admin"
    templates.mkdir()
    (templates / "_ui.html").write_text(
        '{% macro csrf_input() %}<input type="hidden" name="__csrf" value="{{ csrf }}">'
        "{% endmacro %}{% macro brand_mark(large=false) %}"
        '<span class="brand-mark" data-legacy-brand></span>{% endmacro %}'
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 48,
        secure_cookies=False,
        templates_dir=tmp_path,
    )
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host, "/tools/admin")
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client, "/tools/admin")
        for path in ("/", "/schema"):
            page = await client.get("/tools/admin" + path)
            assert page.status_code == 200
            assert "data-legacy-brand" in page.text
            assert 'class="shell-nav-link sidebar-home' in page.text
            assert 'aria-label="Home"' in page.text


def test_guard_rejects_removed_export(monkeypatch):
    monkeypatch.setattr(quite_admin, "__all__", [n for n in quite_admin.__all__ if n != "Field"])
    assert any("removed public exports ['Field']" in error for error in check())


@pytest.mark.parametrize("member", ["method", "property", "attribute"])
def test_guard_rejects_new_required_protocol_member(monkeypatch, member):
    async def count(self, model):
        return 0

    if member == "method":
        monkeypatch.setattr(Adapter, "count", count, raising=False)
    elif member == "property":
        monkeypatch.setattr(Adapter, "count", property(count), raising=False)
    else:
        monkeypatch.setattr(Adapter, "__annotations__", {"count": "int"}, raising=False)
    assert any("changed required protocol" in error for error in check())


@pytest.mark.parametrize("change", ["required", "default", "order", "async"])
def test_guard_rejects_incompatible_signatures(monkeypatch, change):
    original = inspect.signature(Admin.add_adapter)
    parameters = list(original.parameters.values())
    if change == "required":
        parameters.append(inspect.Parameter("tenant", inspect.Parameter.KEYWORD_ONLY))
    elif change == "default":
        parameters[2] = parameters[2].replace(default=False)
    elif change == "order":
        parameters[0], parameters[1] = parameters[1], parameters[0]
    if change == "async":

        async def replacement(*args, **kwargs):
            pass
    else:

        def replacement(*args, **kwargs):
            pass

    replacement.__signature__ = original.replace(parameters=parameters)
    monkeypatch.setattr(Admin, "add_adapter", replacement)
    assert any("add_adapter" in error for error in check())


def test_guard_allows_an_optional_keyword_extension(monkeypatch):
    original = inspect.signature(Admin.add_adapter)

    def replacement(*args, **kwargs):
        pass

    replacement.__signature__ = original.replace(
        parameters=[
            *original.parameters.values(),
            inspect.Parameter("new_option", inspect.Parameter.KEYWORD_ONLY, default=None),
        ]
    )
    monkeypatch.setattr(Admin, "add_adapter", replacement)
    assert check() == []


def test_public_error_hierarchy_and_field_errors():
    assert issubclass(NotFound, AdminError)
    assert issubclass(Conflict, AdminError)
    assert isinstance(StaleRecord(), Conflict)
    error = ValidationError({"name": "Please enter a name."})
    assert isinstance(error, AdminError)
    assert error.errors == {"name": "Please enter a name."}


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_documented_template_context_and_field_include(
    auth, web_backend, tmp_path, framework
):
    adapter, model = web_backend
    (tmp_path / "contract.html").write_text(
        '{% extends "quite_admin/base.html" %}{% block title %}API contract{% endblock %}'
        '{% block head %}<meta name="contract" content="{{ template_api_version }}">{% endblock %}'
        '{% block content %}<p id="contract">{{ page.slug }}|{{ identity.subject }}|'
        "{{ request.method }}|{{ title }}|{{ description }}|{{ language }}|{{ theme.primary }}|"
        "{{ resources[0].slug }}|{{ resources[0].label }}|{{ pages[0].slug }}|"
        '{{ resource_groups["Data"][0].slug }}|{{ breadcrumbs[0].label }}|'
        '{{ t("Search") }}|{{ tn("record", "records", 2) }}|{{ admin.title }}|'
        '{{ url("/models/items/") }}|{{ scripts|length }}|{{ logo_url is none }}|'
        "{{ csrf|length > 0 }}|{{ custom }}</p>{% endblock %}"
    )
    (tmp_path / "counter.html").write_text(
        '<input id="custom-counter" name="{{ field.name }}" value="{{ values[field.name] }}" '
        'data-kind="{{ field.kind }}" data-editable="{{ editable }}" '
        'data-help="{{ help.help_text }}" data-creating="{{ creating }}" '
        'data-resource="{{ resource.slug }}" data-api="{{ template_api_version }}">'
        '<span id="counter-error">{{ errors.get(field.name, "") }}</span>'
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        title="Contract admin",
        description="Contract description",
        templates_dir=tmp_path,
    )
    admin.configure(
        "items",
        options=ModelOptions(
            group="Data",
            fields={"count": FieldOptions(template="counter.html", help_text="Count")},
        ),
    )
    admin.add_page(
        Page(
            "contract",
            "Contract",
            "contract.html",
            context=lambda request: {
                "custom": "Application context",
                "template_api_version": 999,
                "identity": None,
                "csrf": "",
                "url": None,
                "resources": [],
                "resource_groups": {},
                "request": None,
                "template": "missing.html",
                "page": None,
                "status": 418,
                "trusted_scripts": ("forms.js",),
            },
        )
    )
    render = admin.templates.TemplateResponse

    def render_contract(*, request, name, context, status_code):
        assert {
            "request",
            "admin",
            "identity",
            "csrf",
            "url",
            "title",
            "description",
            "language",
            "theme",
            "logo_url",
            "t",
            "tn",
            "resources",
            "resource_groups",
            "pages",
            "breadcrumbs",
            "scripts",
            "template_api_version",
        } <= context.keys()
        if name == "quite_admin/list.html":
            assert {
                "resource",
                "columns",
                "result",
                "page_number",
                "limit",
                "query",
                "query_url",
                "permissions",
            } <= context.keys()
            assert isinstance(context["result"], RecordPage)
            assert isinstance(context["query"], Query)
            assert all(isinstance(column, Field) for column in context["columns"])
            assert context["page_number"] == 1 and context["limit"] == 25
            assert context["query_url"](page=2).startswith(prefix + "/models/items/")
            assert set(context["permissions"]) == {"view", "create", "edit", "delete"}
        elif name == "quite_admin/form.html":
            assert {
                "resource",
                "fields",
                "values",
                "errors",
                "defaults",
                "creating",
                "writable",
                "record",
                "form_action",
                "revision_token",
                "stale",
                "editable",
                "can_delete",
                "record_actions",
            } <= context.keys()
            assert all(isinstance(value, str) for value in context["values"].values())
            assert isinstance(context["defaults"], set)
            assert isinstance(context["revision_token"], str)
            assert all(isinstance(field, Field) for field in context["writable"].values())
        return render(request=request, name=name, context=context, status_code=status_code)

    admin.templates.TemplateResponse = render_contract
    host = FastAPI() if framework == "fastapi" else Litestar()
    if framework == "fastapi":
        admin.mount_fastapi(host, "/control")
    else:
        admin.mount_litestar(host, "/control")
    prefix = "/proxy/control"
    async with AsyncClient(
        transport=ASGITransport(app=host, root_path="/proxy"), base_url="http://test"
    ) as client:
        await login(client, prefix)
        page = await client.get(prefix + "/pages/contract")
        assert page.status_code == 200
        assert '<meta name="contract" content="1">' in page.text
        assert "contract|admin|GET|Contract admin|Contract description|en|#3395fd|" in page.text
        assert "items|Items|contract|items|Home|Search|records|Contract admin|" in page.text
        assert prefix + "/models/items/|2|True|True|Application context" in page.text
        listing = await client.get(prefix + "/models/items/")
        assert listing.status_code == 200
        form = await client.get(prefix + "/models/items/new")
        assert 'id="custom-counter" name="count" value=""' in form.text
        assert 'data-kind="integer" data-editable="True"' in form.text
        assert 'data-help="Count" data-creating="True"' in form.text
        assert f'data-resource="items" data-api="{TEMPLATE_API_VERSION}"' in form.text
        invalid = await client.post(
            prefix + "/models/items/new",
            data={
                "__csrf": csrf(form),
                "name": "Contract",
                "active": "true",
                "count": "invalid",
            },
        )
        assert invalid.status_code == 422
        assert 'id="custom-counter" name="count" value="invalid"' in invalid.text
        assert '<span id="counter-error">Enter a valid integer.</span>' in invalid.text
        record = await adapter.create(model, {"name": "Read only", "count": 42})
        admin.configure(
            "items",
            options=ModelOptions(
                readonly_fields=("count",),
                fields={"count": FieldOptions(template="counter.html")},
            ),
        )
        detail = await client.get(
            prefix + "/models/items/" + adapter.describe(model).record_key(record)
        )
        assert 'id="custom-counter"' not in detail.text
        assert 'id="field-count"' in detail.text and "42" in detail.text
