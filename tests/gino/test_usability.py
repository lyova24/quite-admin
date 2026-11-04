"""The same HTTP usability contracts on the isolated GINO/SQLAlchemy 1.3 profile."""

# ruff: noqa: F401

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from quite_admin import Activity, Admin
from quite_admin.stores.sqlalchemy import SQLAlchemyStore
from tests.test_bulk_actions import (
    bulk_client,
    test_bulk_action_uses_existing_hooks_and_preserves_partial_results,
    test_bulk_rechecks_permissions_and_record_changes,
)
from tests.test_field_display import (
    display_client,
    test_url_template_is_presentation_only_and_encodes_values,
)


@pytest.fixture
def web_backend(backend):
    return backend


@pytest.fixture
def web_admin(web_backend, auth):
    adapter, model = web_backend
    return Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, adapters=[adapter])


async def test_owned_legacy_storage_supports_retention_and_cleanup(tmp_path):
    store = SQLAlchemyStore(f"sqlite:///{tmp_path}/legacy.sqlite3")
    event = Activity.new(
        subject="admin",
        display_name="Admin",
        collection="items",
        action="edit",
        outcome="success",
        status_code=303,
    )
    await store.append_activity(replace(event, occurred_at="2000-01-01T00:00:00.000000Z"))
    assert await store.purge_activities(before=datetime.now(UTC)) == 1
    assert not (await store.activities()).events
    await store.aclose()
