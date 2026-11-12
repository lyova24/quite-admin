"""Exercise the extended examples through the real admin and disposable databases."""

import json
from decimal import Decimal
from html import escape
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy import func, select

from examples.common import Product, make_demo, seed
from examples.showcase import (
    DemoAccount,
    FieldSample,
    Folder,
    PriceAlert,
    ReferenceRate,
    RegionalPrice,
)

from .helpers import csrf, login, revision


@pytest.fixture(params=["fastapi", "litestar"])
async def feature_demo(request, tmp_path, monkeypatch):
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_STORAGE_URL", f"sqlite:///{tmp_path}/service.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "correct horse battery staple")
    admin, engine, sessions = make_demo()
    seed(engine, sessions)
    try:
        if request.param == "fastapi":
            app = FastAPI()
            admin.mount_fastapi(app)
        else:
            app = Litestar(route_handlers=[admin.litestar_route()])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await login(client)
            yield admin, engine, sessions, client
    finally:
        engine.dispose()


def record_path(resource, row):
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    return f"/admin/models/{resource.slug}/{resource.schema.record_key(values)}"


async def submit_edit(client, path, values):
    form = await client.get(path)
    assert form.status_code == 200
    return await client.post(
        path, data={"__csrf": csrf(form), "__revision": revision(form), **values}
    )


async def test_showcase_seed_is_additive_and_preserves_edited_records(feature_demo):
    _, engine, sessions, _ = feature_demo
    models = (Product, FieldSample, Folder, RegionalPrice, PriceAlert, ReferenceRate, DemoAccount)
    with sessions.begin() as session:
        counts = {
            model: session.scalar(select(func.count()).select_from(model)) for model in models
        }
        session.scalar(select(Product).order_by(Product.id)).name = "Keep this existing product"
        session.scalar(
            select(FieldSample).order_by(FieldSample.id)
        ).title = "Keep this edited sample"
        session.scalar(select(Folder).order_by(Folder.id)).name = "Keep this edited folder"
    seed(engine, sessions)
    with sessions() as session:
        assert counts == {
            model: session.scalar(select(func.count()).select_from(model)) for model in models
        }
        assert (
            session.scalar(select(Product).order_by(Product.id)).name
            == "Keep this existing product"
        )
        assert (
            session.scalar(select(FieldSample).order_by(FieldSample.id)).title
            == "Keep this edited sample"
        )
        assert session.scalar(select(Folder).order_by(Folder.id)).name == "Keep this edited folder"
        assert counts[Folder] >= 32


async def test_showcase_fields_defaults_privacy_and_native_validation(feature_demo):
    admin, _, sessions, client = feature_demo
    resources = await admin.resources()
    resource = resources["field_samples"]
    home = await client.get("/admin/")
    assert home.status_code == 200 and "data-dashboard" in home.text
    assert "data-demo-calendar" not in home.text
    assert "/pages/showcase" not in home.text and "/pages/report" not in home.text
    for slug in (
        "field_samples",
        "folders",
        "regional_prices",
        "price_alerts",
        "reference_rates",
        "demo_accounts",
    ):
        assert f'href="/admin/models/{slug}/"' in home.text
    with sessions() as session:
        sample = session.scalar(select(FieldSample).order_by(FieldSample.id))
        path = record_path(resource, sample)
        original_id, original_status = sample.public_id, sample.status
        hidden_value = sample.api_key
    form = await client.get(path)
    assert form.status_code == 200
    assert '<select id="field-status"' in form.text
    assert all(f'value="{value}"' in form.text for value in ("draft", "published", "archived"))
    assert "data-json-editor" in form.text
    assert '<textarea id="field-description"' in form.text
    assert 'id="field-public_id"' in form.text and str(original_id) in form.text
    assert 'href="https://example.com/catalog"' in form.text
    assert 'href="https://example.com/issues/DEMO-42"' in form.text
    assert 'class="showcase-ticket-input" id="field-ticket"' in form.text
    assert 'list="showcase-issue-suggestions"' in form.text
    assert '<datalist id="showcase-issue-suggestions">' in form.text
    assert 'name="created_at"' not in form.text and 'id="field-created_at"' in form.text
    assert 'name="binary_preview"' not in form.text and 'id="field-binary_preview"' in form.text
    assert "api_key" not in form.text and hidden_value not in form.text
    listing = await client.get("/admin/models/field_samples/")
    assert 'data-field-display="json"' in listing.text
    assert 'data-field-display="multiline"' in listing.text

    invalid_uuid = await submit_edit(client, path, {"public_id": "not-a-uuid"})
    assert invalid_uuid.status_code == 422
    invalid_enum = await submit_edit(client, path, {"status": "unsupported-status"})
    assert invalid_enum.status_code == 422
    forbidden = await submit_edit(client, path, {"api_key": "forged", "created_at": "2026-01-01"})
    assert forbidden.status_code == 422
    with sessions() as session:
        sample = session.scalar(select(FieldSample).order_by(FieldSample.id))
        assert sample.public_id == original_id and sample.status == original_status
        assert sample.api_key == hidden_value

    new = await client.get("/admin/models/field_samples/new")
    assert "__default__public_id" in new.text and "__default__quantity" in new.text
    created = await client.post(
        "/admin/models/field_samples/new",
        data={"__csrf": csrf(new), "title": "Default-backed sample"},
    )
    assert created.status_code == 303, created.text
    with sessions() as session:
        saved = session.scalar(
            select(FieldSample).where(FieldSample.title == "Default-backed sample")
        )
        assert isinstance(saved.public_id, UUID)
        assert saved.status == "draft" and saved.quantity == 1 and saved.ratio == 1.0
    public_id = uuid4()
    changed = await submit_edit(
        client, created.headers["location"], {"public_id": str(public_id), "ticket": " demo-73 "}
    )
    assert changed.status_code == 303, changed.text
    with sessions() as session:
        saved = session.scalar(
            select(FieldSample).where(FieldSample.title == "Default-backed sample")
        )
        assert saved.public_id == public_id
        assert saved.ticket == "DEMO-73"
    updated_form = await client.get(created.headers["location"])
    assert 'value="DEMO-73"' in updated_form.text
    assert 'href="https://example.com/issues/DEMO-73"' in updated_form.text


async def test_showcase_self_relations_page_search_detach_and_label_override(feature_demo):
    admin, _, sessions, client = feature_demo
    resources = await admin.resources()
    folders = resources["folders"]
    relations = {relation.name: relation for relation in folders.adapter.relations(Folder)}
    assert relations["parent"].kind == "many_to_one" and relations["parent"].can_detach
    assert relations["children"].kind == "one_to_many" and relations["children"].can_detach
    with sessions() as session:
        child = session.scalar(
            select(Folder).where(Folder.parent_id.is_not(None)).order_by(Folder.id)
        )
        child_id, parent_id = child.id, child.parent_id
        parent = session.get(Folder, parent_id)
        parent_path = record_path(folders, parent)
        parent_token = parent_path.rsplit("/", 1)[-1]
        sample = session.scalar(select(FieldSample).order_by(FieldSample.id))
        sample_path = record_path(resources["field_samples"], sample)
        target = session.scalar(select(Folder).order_by(Folder.id.desc()))
        target_id, target_name = target.id, target.name
        target_token = folders.schema.record_key({"id": target.id})
    endpoint = "/admin/models/folders/relationships/parent/options"
    first = await client.get(endpoint, params={"record": parent_token})
    assert first.status_code == 200 and len(first.json()["items"]) == 25
    assert first.json()["has_next"]
    second = await client.get(endpoint, params={"record": parent_token, "page": 2})
    assert second.status_code == 200 and second.json()["items"]
    assert not {item["key"] for item in first.json()["items"]} & {
        item["key"] for item in second.json()["items"]
    }
    searched = await client.get(endpoint, params={"record": parent_token, "q": target_name})
    assert any(item["key"] == target_token for item in searched.json()["items"])
    detached = await submit_edit(client, parent_path, {"__relation_present__children": "true"})
    assert detached.status_code == 303, detached.text
    with sessions() as session:
        assert session.get(Folder, child_id).parent_id is None
    related = await submit_edit(
        client,
        sample_path,
        {"__relation_present__folder": "true", "__relation__folder": target_token},
    )
    assert related.status_code == 303, related.text
    with sessions() as session:
        sample = session.scalar(select(FieldSample).order_by(FieldSample.id))
        assert sample.folder_id == target_id
    assert target_name in (await client.get(sample_path)).text


async def test_showcase_composite_keys_support_create_edit_and_delete(feature_demo):
    admin, _, sessions, client = feature_demo
    resource = (await admin.resources())["regional_prices"]
    new = await client.get("/admin/models/regional_prices/new")
    assert new.status_code == 200
    created = await client.post(
        "/admin/models/regional_prices/new",
        data={
            "__csrf": csrf(new),
            "region": "TEST",
            "sku": "test/sku-42",
            "price": "12.34",
            "currency": "EUR",
        },
    )
    assert created.status_code == 303, created.text
    path = created.headers["location"]
    key = resource.schema.parse_key(path.rsplit("/", 1)[-1])
    assert key == {"region": "TEST", "sku": "test/sku-42"}
    form = await client.get(path)
    assert 'id="field-region"' in form.text and 'id="field-sku"' in form.text
    updated = await submit_edit(client, path, {"price": "19.50"})
    assert updated.status_code == 303
    with sessions() as session:
        assert session.get(RegionalPrice, ("TEST", "test/sku-42")).price == Decimal("19.50")
    rejected = await submit_edit(client, path, {"price": "-1"})
    assert rejected.status_code == 422
    with sessions() as session:
        assert session.get(RegionalPrice, ("TEST", "test/sku-42")).price == Decimal("19.50")
    confirmation = await client.get(path + "/delete")
    deleted = await client.post(path + "/delete", data={"__csrf": csrf(confirmation)})
    assert deleted.status_code == 303
    with sessions() as session:
        assert session.get(RegionalPrice, ("TEST", "test/sku-42")) is None


async def test_showcase_composite_foreign_key_search_and_atomic_reassignment(feature_demo):
    admin, _, sessions, client = feature_demo
    resources = await admin.resources()
    alerts, prices = resources["price_alerts"], resources["regional_prices"]
    relation = next(
        relation
        for relation in alerts.adapter.relations(PriceAlert)
        if relation.name == "regional_price"
    )
    assert relation.kind == "many_to_one" and not relation.can_detach
    assert set(relation.source_fields) == {"region", "sku"}
    with sessions() as session:
        alert = session.scalar(select(PriceAlert).order_by(PriceAlert.id))
        alert_id = alert.id
        path = record_path(alerts, alert)
        original_key = {"region": alert.region, "sku": alert.sku}
        original = alert.regional_price
        original_label = prices.record_label(
            {column.name: getattr(original, column.name) for column in original.__table__.columns}
        )
        original_token = prices.schema.record_key(original_key)
        target = next(
            row
            for row in session.scalars(
                select(RegionalPrice).order_by(RegionalPrice.region, RegionalPrice.sku)
            )
            if (row.region, row.sku) != (alert.region, alert.sku)
        )
        target_key = {"region": target.region, "sku": target.sku}
        target_token = prices.schema.record_key(target_key)
    form = await client.get(path)
    assert form.status_code == 200
    assert 'name="region"' not in form.text and 'name="sku"' not in form.text
    assert 'name="__relation__regional_price"' in form.text
    assert f'value="{original_token}" selected' in form.text
    assert escape(original_label) in form.text
    endpoint = "/admin/models/price_alerts/relationships/regional_price/options"
    found = await client.get(
        endpoint,
        params={"record": path.rsplit("/", 1)[-1], "q": json.dumps(target_key)},
    )
    assert found.status_code == 200
    assert found.json()["total"] == 1
    option = found.json()["items"][0]
    assert option["key"] == target_token
    assert prices.schema.parse_key(option["key"]) == target_key
    assert target_key["region"] in option["identity"] and target_key["sku"] in option["identity"]
    saved = await submit_edit(
        client,
        path,
        {
            "threshold": "9.25",
            "__relation_present__regional_price": "true",
            "__relation__regional_price": target_token,
        },
    )
    assert saved.status_code == 303, saved.text

    def persisted():
        with sessions() as session:
            row = session.get(PriceAlert, alert_id)
            return row.region, row.sku, row.threshold

    expected = target_key["region"], target_key["sku"], Decimal("9.25")
    assert persisted() == expected
    absent = prices.schema.record_key({"region": "MISSING", "sku": "missing-sku"})
    invalid = await submit_edit(
        client,
        path,
        {
            "threshold": "99.00",
            "__relation_present__regional_price": "true",
            "__relation__regional_price": absent,
        },
    )
    assert invalid.status_code == 404
    assert persisted() == expected
    negative = await submit_edit(
        client,
        path,
        {
            "threshold": "-1",
            "__relation_present__regional_price": "true",
            "__relation__regional_price": original_token,
        },
    )
    assert negative.status_code == 422
    assert persisted() == expected


async def test_showcase_actions_hooks_and_read_only_examples(feature_demo):
    admin, _, sessions, client = feature_demo
    resources = await admin.resources()
    with sessions() as session:
        sample = session.scalar(select(FieldSample).order_by(FieldSample.id))
        sample_id, quantity, ratio = sample.id, sample.quantity, sample.ratio
        path = record_path(resources["field_samples"], sample)
        folder = session.get(Folder, sample.folder_id)
        folder_path = record_path(resources["folders"], folder)
        rate = session.scalar(select(ReferenceRate))
        rate_path = record_path(resources["reference_rates"], rate)
    form = await client.get(path)
    for action, status in (("archive", "archived"), ("publish", "published")):
        endpoint = path + "/actions/" + action
        assert (await client.get(endpoint)).status_code == 405
        assert (await client.post(endpoint, data={"__csrf": "wrong"})).status_code == 403
        changed = await client.post(endpoint, data={"__csrf": csrf(form)})
        assert changed.status_code == 303
        with sessions() as session:
            assert session.get(FieldSample, sample_id).status == status
    assert (await submit_edit(client, path, {"quantity": "-1"})).status_code == 422
    assert (await submit_edit(client, path, {"ratio": "-0.1"})).status_code == 422
    with sessions() as session:
        assert session.get(FieldSample, sample_id).quantity == quantity
        assert session.get(FieldSample, sample_id).ratio == ratio
    authentication = (await admin.storage.activities(subject="admin", collection="")).events
    assert any(event.action == "login" and event.outcome == "success" for event in authentication)
    events = (await admin.storage.activities(subject="admin", collection="field_samples")).events
    failed = [event for event in events if event.outcome == "failure"]
    assert any(event.action == "edit" and event.status_code == 422 for event in failed)
    assert all(event.details is None for event in failed)
    readonly = await client.get(rate_path)
    assert readonly.status_code == 200 and "Save changes</button>" not in readonly.text
    assert (await client.get("/admin/models/reference_rates/new")).status_code == 403
    assert (
        await client.post(rate_path, data={"__csrf": csrf(readonly), "value": "9"})
    ).status_code == 403
    assert (await client.get(rate_path + "/delete")).status_code == 403
    folder_form = await client.get(folder_path)
    assert 'name="__relation__samples"' not in folder_form.text
    forged = await submit_edit(client, folder_path, {"__relation_present__samples": "true"})
    assert forged.status_code == 422


async def test_showcase_account_service_validates_secrets_and_checks_stale_edits(
    feature_demo, caplog
):
    _, _, sessions, client = feature_demo
    path = "/admin/models/demo_accounts/new"
    form = await client.get(path)
    assert 'name="new_password"' in form.text and 'type="password"' in form.text
    assert "password_hash" not in form.text
    invalid = await client.post(
        path,
        data={
            "__csrf": csrf(form),
            "username": "service_editor",
            "display_name": "Editor",
            "new_password": "tiny",
        },
    )
    assert invalid.status_code == 422 and 'value="tiny"' not in invalid.text
    secret = "showcase-service-private-password"
    created = await client.post(
        path,
        data={
            "__csrf": csrf(form),
            "username": "service_editor",
            "display_name": "Service editor",
            "new_password": secret,
        },
    )
    assert created.status_code == 303, created.text
    with sessions() as session:
        account = session.scalar(
            select(DemoAccount).where(DemoAccount.username == "service_editor")
        )
        account_id, original_hash = account.id, account.password_hash
        assert original_hash and original_hash != secret
        assert account.display_name == "Service editor"
    path = created.headers["location"]
    edit_form = await client.get(path)
    assert secret not in edit_form.text and original_hash not in edit_form.text
    draft = {
        "__csrf": csrf(edit_form),
        "__revision": revision(edit_form),
        "display_name": "Checked service edit",
        "new_password": "",
    }
    edited = await client.post(path, data=draft)
    assert edited.status_code == 303, edited.text
    stale = await client.post(path, data={**draft, "display_name": "Must not overwrite"})
    assert stale.status_code == 409
    with sessions() as session:
        account = session.get(DemoAccount, account_id)
        assert (
            account.display_name == "Checked service edit"
            and account.password_hash == original_hash
        )
    replacement = "replacement-showcase-private-password"
    changed = await submit_edit(client, path, {"new_password": replacement})
    assert changed.status_code == 303, changed.text
    with sessions() as session:
        account = session.get(DemoAccount, account_id)
        assert account.password_hash != original_hash and account.password_hash != replacement
    history = await client.get("/admin/history?collection=demo_accounts")
    assert (
        secret not in history.text
        and replacement not in history.text
        and original_hash not in history.text
    )
    assert secret not in caplog.text and replacement not in caplog.text
