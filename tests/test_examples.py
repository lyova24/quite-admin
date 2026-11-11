import html
import importlib
import re
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from examples.quickstart import create_app

from .helpers import confirmation, csrf, login, revision


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
        assert "Deactivate products" in listing.text
        assert "Deactivate products" not in (await client.get("/admin/models/notes/")).text
        keys = re.findall(r'name="keys" value="([^"]+)"', listing.text)
        preview = await client.post(
            "/admin/models/products/actions/bulk",
            data={"__csrf": csrf(listing), "keys": keys[:2], "action": "action:deactivate"},
        )
        assert "Confirm bulk action" in preview.text
        result = await client.post(
            "/admin/models/products/actions/bulk",
            data={"__csrf": csrf(preview), "__confirmation": confirmation(preview)},
        )
        assert "Succeeded: 2" in result.text
        resource = (await module.admin.resources())["products"]
        for key in keys[:2]:
            row = await resource.adapter.get(resource.model, resource.schema.parse_key(key))
            assert row["active"] is False
        report = await client.get("/admin/pages/report")
        assert report.status_code == 200, report.text
        assert "Customers in your workspace" in report.text


async def test_standalone_quickstart_crud_relationships_and_persistence(monkeypatch, tmp_path):
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("QUITE_ADMIN_SECRET", "s" * 32)
    app = create_app(tmp_path)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client,
    ):
        assert (await client.get("/admin/")).status_code == 303
        await login(client)
        home = await client.get("/admin/")
        for collection in ("customers", "orders", "order_items"):
            assert f"/admin/models/{collection}/" in home.text
        orders = await client.get("/admin/models/orders/")
        assert "Starter order" in orders.text
        assert "Alex Morgan" in (await client.get("/admin/models/customers/")).text
        assert "Notebook" in (await client.get("/admin/models/order_items/")).text

        form = await client.get("/admin/models/customers/new")
        created = await client.post(
            "/admin/models/customers/new",
            data={"__csrf": csrf(form), "name": "Trial customer", "email": "trial@example.test"},
        )
        assert created.status_code == 303, created.text
        customer_url = created.headers["location"]
        form = await client.get(customer_url)
        updated = await client.post(
            customer_url,
            data={
                "__csrf": csrf(form),
                "__revision": revision(form),
                "name": "Updated customer",
                "email": "trial@example.test",
            },
        )
        assert updated.status_code == 303, updated.text

        order_url = html.unescape(
            re.search(r'<a class="record-row-link[^\"]*" href="([^\"]+)"', orders.text)[1]
        )
        form = await client.get(order_url)
        customer_select = re.search(
            r'<select[^>]+name="__relation__customer"[^>]*>(.*?)</select>', form.text, re.S
        )
        original_customer = re.search(r'<option value="([^"]+)"\s+selected', customer_select[1])[1]
        order_data = {"name": "Starter order", "status": "paid"}
        for customer_key in (customer_url.rsplit("/", 1)[1], original_customer):
            form = await client.get(order_url)
            changed = await client.post(
                order_url,
                data={
                    "__csrf": csrf(form),
                    "__revision": revision(form),
                    **order_data,
                    "__relation_present__customer": "true",
                    "__relation__customer": customer_key,
                },
            )
            assert changed.status_code == 303, changed.text
            with sqlite3.connect(tmp_path / "shop.db") as connection:
                expected_name = (
                    "Alex Morgan" if customer_key == original_customer else "Updated customer"
                )
                assert (
                    connection.execute(
                        "SELECT customers.name FROM orders "
                        "JOIN customers ON customers.id = orders.customer_id"
                    ).fetchone()[0]
                    == expected_name
                )

        history = await client.get("/admin/history")
        assert "Trial customer" in history.text and "Updated customer" in history.text
        confirmation = await client.get(customer_url + "/delete")
        deleted = await client.post(customer_url + "/delete", data={"__csrf": csrf(confirmation)})
        assert deleted.status_code == 303, deleted.text
        assert (await client.get(customer_url)).status_code == 404

    restarted = create_app(tmp_path)
    async with (
        restarted.router.lifespan_context(restarted),
        AsyncClient(transport=ASGITransport(app=restarted), base_url="http://testserver") as client,
    ):
        await login(client)
        orders = await client.get("/admin/models/orders/")
        assert "paid" in orders.text
        assert "Updated customer" in (await client.get("/admin/history")).text

    with sqlite3.connect(tmp_path / "shop.db") as connection:
        assert connection.execute("SELECT count(*) FROM customers").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM order_items").fetchone()[0] == 2
