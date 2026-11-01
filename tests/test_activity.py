from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from quite_admin import Field, FieldOptions, ModelOptions, ModelSchema
from quite_admin.activity import MAX_VALUE_BYTES, bounded_details, scalar_changes


def test_typed_changes_distinguish_null_empty_false_missing_and_unchanged():
    schema = ModelSchema(
        "items",
        (
            Field("id", int, primary_key=True),
            Field("name", str),
            Field("note", str, nullable=True),
            Field("active", bool),
            Field("price", Decimal),
            Field("updated_at", datetime),
            Field("uuid", UUID),
        ),
    )
    old = {
        "id": 1,
        "name": "same",
        "note": None,
        "active": True,
        "price": Decimal("12345678901234567890.01"),
        "updated_at": datetime(2026, 11, 1, tzinfo=UTC),
    }
    new = {
        **old,
        "note": "",
        "active": False,
        "price": Decimal("12345678901234567890.02"),
        "uuid": UUID("12345678-1234-1234-1234-123456789012"),
    }
    changes = {item.name: item for item in scalar_changes(schema, ModelOptions(), old, new)}
    assert set(changes) == {"note", "active", "price", "uuid"}
    assert (changes["note"].before, changes["note"].after) == (None, "")
    assert (changes["active"].before, changes["active"].after) == ("true", "false")
    assert changes["price"].after == "12345678901234567890.02"
    assert not changes["uuid"].before_present and changes["uuid"].after_present
    deleted = scalar_changes(schema, ModelOptions(), old, None)
    assert deleted and all(item.before_present and not item.after_present for item in deleted)


def test_snapshots_exclude_secrets_even_when_exposed_and_redact_nested_json():
    schema = ModelSchema(
        "items",
        (
            Field("id", int, primary_key=True),
            Field("name", str),
            Field("internal", str),
            Field("password_hash", str),
            Field("apiKey", str),
            Field("config", dict, kind="json"),
        ),
    )
    options = ModelOptions(
        exclude=("internal",),
        expose_sensitive_fields=("password_hash",),
        fields={"name": FieldOptions(formatter=lambda value: "UI-only")},
    )
    old = {
        "id": 1,
        "name": "before",
        "internal": "private-old",
        "password_hash": "hash-old",
        "apiKey": "api-secret-old",
        "config": {"enabled": True, "clientSecret": "secret-old"},
    }
    new = {
        **old,
        "name": "after",
        "internal": "private-new",
        "password_hash": "hash-new",
        "apiKey": "api-secret-new",
        "config": {"enabled": False, "clientSecret": "secret-new"},
    }
    changes = scalar_changes(schema, options, old, new)
    assert {item.name for item in changes} == {"name", "config"}
    assert changes[0].before == "before" and changes[0].after == "after"
    assert "[redacted]" in changes[1].after and "secret-new" not in repr(changes)
    assert old["config"]["clientSecret"] == "secret-old"
    secret_only = {**old, "config": {"enabled": True, "clientSecret": "different"}}
    assert not scalar_changes(schema, options, old, secret_only)


def test_large_unicode_and_deep_json_are_bounded_with_visible_truncation_flags():
    schema = ModelSchema(
        "items",
        (
            Field("id", int, primary_key=True),
            Field("text", str),
            Field("config", dict, kind="json"),
        ),
    )
    nested = {"key": "value"}
    for _ in range(30):
        nested = {"nested": nested}
    changes = scalar_changes(
        schema, ModelOptions(), {}, {"id": 1, "text": "я" * 10000, "config": nested}
    )
    text = next(item for item in changes if item.name == "text")
    assert text.after_truncated and len(text.after.encode()) <= MAX_VALUE_BYTES
    assert next(item for item in changes if item.name == "config").after_truncated
    assert bounded_details(changes).omitted == 0
