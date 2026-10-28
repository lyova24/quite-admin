import importlib

import pytest
from starlette.testclient import TestClient

from .helpers import csrf


@pytest.mark.parametrize("module_name", ["examples.fastapi_app", "examples.litestar_app"])
def test_example_lifespan_and_custom_report(module_name, monkeypatch, tmp_path):
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "example-password")
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.db")
    module = importlib.import_module(module_name)
    with TestClient(module.app) as client:
        assert client.get("/health").status_code == 200
        form = client.get("/admin/login")
        assert form.status_code == 200
        result = client.post(
            "/admin/login",
            data={"__csrf": csrf(form), "username": "admin", "password": "example-password"},
        )
        assert result.status_code == 200
        listing = client.get("/admin/models/products/")
        assert "Everyday notebook" in listing.text
        assert "8 records" in listing.text
        report = client.get("/admin/pages/report")
        assert report.status_code == 200, report.text
        assert "Customers in your workspace" in report.text
