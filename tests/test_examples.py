import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from .helpers import csrf


@pytest.mark.parametrize("module_name", ["examples.fastapi_app", "examples.litestar_app"])
async def test_example_lifespan_and_custom_report(module_name, monkeypatch, tmp_path):
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "example-password")
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.db")
    module = importlib.import_module(module_name)
    lifecycle = (
        module.app.router.lifespan_context(module.app)
        if module_name == "examples.fastapi_app"
        else module.app.lifespan()
    )
    async with (
        lifecycle,
        AsyncClient(
            transport=ASGITransport(app=module.app),
            base_url="http://testserver",
            follow_redirects=True,
        ) as client,
    ):
        assert (await client.get("/health")).status_code == 200
        form = await client.get("/admin/login")
        assert form.status_code == 200
        result = await client.post(
            "/admin/login",
            data={"__csrf": csrf(form), "username": "admin", "password": "example-password"},
        )
        assert result.status_code == 200
        listing = await client.get("/admin/models/products/")
        assert "Everyday notebook" in listing.text
        assert "8 records" in listing.text
        report = await client.get("/admin/pages/report")
        assert report.status_code == 200, report.text
        assert "Customers in your workspace" in report.text
