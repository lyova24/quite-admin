import sys
from datetime import UTC, datetime, timedelta

import anyio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quite_admin import ActivityDetails, Admin, Document, SQLiteStore
from quite_admin.stores.sqlalchemy import SQLAlchemyStore

from . import test_storage
from .helpers import login
from .test_storage import event

store = test_storage.store


async def test_purge_is_bounded_scoped_and_cleans_details_and_unused_actors(store):
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    other = (
        SQLiteStore(store.path, namespace=store.namespace + "-other")
        if isinstance(store, SQLiteStore)
        else SQLAlchemyStore(store.engine, namespace=store.namespace + "-other")
    )
    expired = event(
        occurred_at="2025-01-01T00:00:00.000000Z", details=ActivityDetails(record_key="test")
    )
    await store.append_activity(expired)
    await store.append_activity(event("old-only", occurred_at="2025-02-01T00:00:00.000000Z"))
    kept = event(occurred_at="2026-01-01T00:00:00.000000Z")
    await store.append_activity(kept)
    await other.append_activity(event(occurred_at=expired.occurred_at))
    await store.save_document(Document("saved", "settings", "admin", {"kept": True}))
    assert await store.purge_activities(before=cutoff, limit=1) == 1
    assert len((await store.activities()).events) == 2
    assert await store.purge_activities(before=cutoff, limit=1) == 1
    assert await store.purge_activities(before=cutoff, limit=1) == 0
    assert (await store.activities()).events == (kept,)
    assert await store.actors(collections=("items",)) == (("alice", "Alice"),)
    assert len((await other.activities()).events) == 1
    assert (await store.get_document("saved")).payload == {"kept": True}
    rows = await store._run(
        lambda execute: (
            execute(
                "SELECT * FROM quiteadmin_activity_details WHERE activity_id = :id",
                {"id": expired.id},
            ).rows
        )
    )
    assert rows == []
    with pytest.raises(ValueError, match="timezone-aware"):
        await store.purge_activities(before=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        await store.purge_activities(before=cutoff, limit=1001)


@pytest.mark.parametrize("retention", [90, 7, None])
async def test_default_and_custom_retention_run_on_requests(auth, tmp_path, retention):
    store = SQLiteStore(tmp_path / "history.sqlite3")
    now = datetime.now(UTC)
    for days in (100, 30, 1):
        await store.append_activity(
            event(occurred_at=(now - timedelta(days=days)).isoformat().replace("+00:00", "Z"))
        )
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        storage=store,
        **({} if retention == 90 else {"history_retention_days": retention}),
    )
    assert admin.history_retention_days == retention
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        assert (await client.get("/admin/history")).status_code == 200
    assert len((await store.activities()).events) == {90: 2, 7: 1, None: 3}[retention]


async def test_cleanup_is_throttled_and_failure_does_not_block_requests(auth, tmp_path, caplog):
    class FailingStore(SQLiteStore):
        attempts = 0

        async def purge_activities(self, **kwargs):
            self.attempts += 1
            raise RuntimeError("private connection string")

    store = FailingStore(tmp_path / "state.sqlite3")
    admin = Admin(auth=auth, secret_key="s" * 32, storage=store, secure_cookies=False)
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        for _ in range(3):
            assert (await client.get("/admin/")).status_code == 200
    assert store.attempts == 1
    assert "quite_admin.history_cleanup_failed" in caplog.text
    assert "private connection string" not in caplog.text


@pytest.mark.parametrize("value", [0, -1, True, "90", 1.5, 365001])
def test_retention_configuration_is_validated(auth, value):
    with pytest.raises(ValueError, match="history_retention_days"):
        Admin(auth=auth, secret_key="s" * 32, history_retention_days=value)


async def test_cleanup_cli_drains_batches_and_keeps_other_namespaces(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path, namespace="backoffice")
    other = SQLiteStore(path)
    for _ in range(3):
        await store.append_activity(event(occurred_at="2000-01-01T00:00:00.000000Z"))
    await other.append_activity(event(occurred_at="2000-01-01T00:00:00.000000Z"))
    result = await anyio.run_process(
        [
            sys.executable,
            "-m",
            "quite_admin",
            "cleanup-history",
            "--storage",
            str(path),
            "--namespace",
            "backoffice",
            "--batch-size",
            "1",
        ],
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert b"Deleted 3" in result.stdout
    assert not (await store.activities()).events
    assert len((await other.activities()).events) == 1
