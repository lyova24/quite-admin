"""The local walkthrough uses normal permissions and the existing exact-hash CSP."""

import base64
import hashlib
import html
import json
import re
from dataclasses import replace
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from examples.common import make_demo, seed
from examples.tour import build_tour_config
from quite_admin import Admin

from .helpers import login

PREFIX = "/ops/admin"


def tour_config(response):
    match = re.search(r"<div data-admin-tour hidden data-config='([^']*)'", response.text)
    assert match is not None, response.text
    return json.loads(html.unescape(match[1]))


def assert_no_tour(response):
    assert "data-admin-tour" not in response.text
    assert "/assets/tour.js" not in response.text
    assert "/assets/tour.css" not in response.text


def mount(admin, framework):
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host, path=PREFIX)
    return host


@pytest.fixture(params=["fastapi", "litestar"])
def tour_demo(request, monkeypatch, tmp_path):
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("QUITE_ADMIN_LANGUAGE", "en")
    admin, engine, sessions = make_demo()
    seed(engine, sessions)
    try:
        yield admin, request.param
    finally:
        engine.dispose()


def test_tour_helper_localizes_steps_and_omits_unavailable_capabilities():
    def url(path):
        return "/mounted/admin" + path

    english = build_tour_config(url, "en", "local-tour")
    russian = build_tour_config(url, "ru", "local-tour")
    expected = ["home", "list", "form", "relationships", "calendar", "export", "schema", "history"]
    assert [step["id"] for step in english["steps"]] == expected
    assert [step["id"] for step in russian["steps"]] == expected
    assert english["homeUrl"] == "/mounted/admin/"
    assert english["steps"][4]["open"] == "calendar"
    assert english["steps"][5]["open"] == "details"
    assert all(
        before["title"] != after["title"] and before["body"] != after["body"]
        for before, after in zip(english["steps"], russian["steps"], strict=True)
    )
    limited = build_tour_config(url, "en", "limited-tour", {"home": True, "history": True})
    assert [step["id"] for step in limited["steps"]] == ["home", "history"]
    assert build_tour_config(url, "en", "empty-tour", {})["steps"] == []


async def test_demo_tour_is_absent_from_login_and_ordinary_admin(tour_demo, auth):
    demo, framework = tour_demo
    ordinary = Admin(
        auth=auth,
        secret_key="s" * 48,
        adapters=[demo.sources[0].adapter],
        secure_cookies=False,
    )
    for admin in (ordinary, demo):
        async with AsyncClient(
            transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
        ) as client:
            assert_no_tour(await client.get(PREFIX + "/login"))
            await login(client, prefix=PREFIX)
            if admin is ordinary:
                assert_no_tour(await client.get(PREFIX + "/"))


async def test_authenticated_demo_config_is_mount_aware_and_uses_exact_sri(tour_demo):
    admin, framework = tour_demo
    async with AsyncClient(
        transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
    ) as client:
        await login(client, prefix=PREFIX)
        page = await client.get(PREFIX + "/")
        config = tour_config(page)
        assert config["language"] == "en"
        assert config["storageKey"] == "quite-admin-demo-tour:/ops/admin/:admin"
        assert config["homeUrl"] == PREFIX + "/"
        assert len(config["steps"]) == 8
        assert "Everyday notebook" not in json.dumps(config)
        for step in config["steps"]:
            parsed = urlsplit(step["url"])
            assert not parsed.scheme and not parsed.netloc and not parsed.query
            assert parsed.path.startswith(PREFIX + "/")
        script = await client.get(PREFIX + "/assets/tour.js")
        assert script.status_code == 200
        digest = "sha256-" + base64.b64encode(hashlib.sha256(script.content).digest()).decode()
        assert f'integrity="{digest}"' in page.text
        assert f"'{digest}'" in page.headers["content-security-policy"]
        script_policy = re.search(r"script-src ([^;]+)", page.headers["content-security-policy"])[1]
        assert "'self'" not in script_policy
        assert "unsafe-inline" not in script_policy and "unsafe-eval" not in script_policy
        assert (await client.get(PREFIX + "/assets/tour.css")).status_code == 200
        form = await client.get(PREFIX + "/models/products/new")
        assert tour_config(form)["steps"] == config["steps"]
        assert 'name="__csrf"' in form.text and "data-relation-picker" in form.text
        missing = await client.get(PREFIX + "/models/not-present/")
        assert missing.status_code == 404
        assert_no_tour(missing)


async def test_demo_tour_uses_relationship_target_permissions(tour_demo):
    admin, framework = tour_demo
    tags = (await admin.resources())["tags"]
    admin.configure(
        "tags", options=replace(tags.options, permission=lambda request, user, action: False)
    )
    async with AsyncClient(
        transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
    ) as client:
        await login(client, prefix=PREFIX)
        config = tour_config(await client.get(PREFIX + "/"))
        ids = {step["id"] for step in config["steps"]}
        assert "form" in ids and "relationships" not in ids


async def test_demo_tour_does_not_offer_forbidden_screens(tour_demo):
    admin, framework = tour_demo
    for slug, resource in (await admin.resources()).items():
        admin.configure(
            slug, options=replace(resource.options, permission=lambda request, user, action: False)
        )
    admin.history_permission = lambda request, user, action: False
    async with AsyncClient(
        transport=ASGITransport(app=mount(admin, framework)), base_url="http://test"
    ) as client:
        await login(client, prefix=PREFIX)
        config = tour_config(await client.get(PREFIX + "/"))
        assert [step["id"] for step in config["steps"]] == ["home"]
        assert config["steps"][0]["url"] == PREFIX + "/"
