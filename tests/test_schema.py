from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

import pytest

from quite_admin import Field, FieldOptions, ModelOptions, ModelSchema, RecordAction, Theme
from quite_admin.errors import NotFound, ValidationError


class Status(Enum):
    DRAFT = "draft"
    ACTIVE = "active"


@pytest.mark.parametrize("collision", ["bulk", "record", "shared"])
def test_bulk_action_slugs_are_unambiguous(collision):
    action = RecordAction("reset", "Reset", lambda operation: None, bulk=collision == "shared")
    options = (
        ModelOptions(bulk_actions=(action, action))
        if collision == "bulk"
        else ModelOptions(actions=(action,), bulk_actions=(action,))
    )
    schema = ModelSchema("items", (Field("id", int, primary_key=True),))
    with pytest.raises(ValueError, match="Duplicate .*action slugs"):
        options.validate(schema)


def test_bulk_actions_require_action_definitions():
    with pytest.raises(TypeError, match="RecordAction"):
        ModelOptions(bulk_actions=("delete",)).validate(
            ModelSchema("items", (Field("id", int, primary_key=True),))
        )


def test_explicit_constructors_keep_defaults_validation_and_replacement():
    field = Field("display_name")
    assert field.label == "Display Name" and field.kind == "string"
    assert replace(field, label="Name") == Field("display_name", label="Name")
    assert Field("status", Status).choices == ("draft", "active")
    assert Field("blob", bytes).read_only
    assert Field("unknown", object).read_only
    schema = ModelSchema("order_items", (Field("id", int, primary_key=True), field))
    assert schema.label == "Order Items"
    assert replace(schema, label="Items").fields == schema.fields
    theme = Theme(primary="#ABC", on_danger="#DEF")
    assert theme.primary == "#aabbcc" and theme.on_danger == "#ddeeff"
    assert replace(theme, primary="#123").primary == "#112233"

    def handler(operation):
        return None

    action = RecordAction("publish", "Publish", handler)
    assert action.required_permission == "edit" and action.handler is handler
    assert replace(action, required_permission="delete").required_permission == "delete"
    for name in ("", "__hidden"):
        with pytest.raises(ValueError, match="Field names"):
            Field(name)
    with pytest.raises(ValueError, match="Duplicate field"):
        ModelSchema("items", (schema.fields[0], schema.fields[0]))
    with pytest.raises(ValueError, match="no primary key"):
        ModelSchema("items", (field,))
    with pytest.raises(ValueError, match="Action slugs"):
        RecordAction("../publish", "Publish", handler)
    with pytest.raises(ValueError, match="Unknown required"):
        RecordAction("publish", "Publish", handler, required_permission="unknown")


@pytest.mark.parametrize(
    "name",
    [
        "primary",
        "background",
        "surface",
        "text",
        "muted",
        "border",
        "danger",
        "on_primary",
        "on_danger",
    ],
)
def test_explicit_theme_constructor_validates_every_color(name):
    with pytest.raises(ValueError, match=rf"Theme\.{name} must be"):
        Theme(**{name: "#fff;}body{display:none}"})


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        (Field("age", int), "42", 42),
        (Field("active", bool), "false", False),
        (Field("price", Decimal), "12.30", Decimal("12.30")),
        (Field("date", date), "2026-01-01", date(2026, 1, 1)),
        (
            Field("time", datetime),
            "2026-01-01T12:30:00+00:00",
            datetime.fromisoformat("2026-01-01T12:30:00+00:00"),
        ),
        (Field("status", Status), "draft", Status.DRAFT),
        (Field("data", dict), '{"hello": true}', {"hello": True}),
        (Field("note", str, nullable=True), "", None),
    ],
)
def test_field_coercion(field, raw, expected):
    assert field.parse(raw) == expected


@pytest.mark.parametrize(
    ("field", "raw"),
    [
        (Field("x", int), "wat"),
        (Field("x", bool), "yes"),
        (Field("x", Decimal), "NaN"),
        (Field("x", float), "inf"),
        (Field("x", dict), "[]"),
        (Field("x", dict), '{"n": NaN}'),
        (Field("x", dict), "null"),
        (Field("x", Status), "missing"),
        (Field("x", str, max_length=2), "long"),
    ],
)
def test_invalid_fields(field, raw):
    with pytest.raises(ValueError):
        field.parse(raw)


def test_composite_and_uuid_keys():
    schema = ModelSchema(
        "records", (Field("tenant", UUID, primary_key=True), Field("slug", str, primary_key=True))
    )
    record = {"tenant": uuid4(), "slug": "folder/a?b=1#Привет"}
    assert schema.parse_key(schema.record_key(record)) == record
    with pytest.raises(NotFound):
        schema.parse_key("not a key")


def test_field_policy_is_enforced_without_browser():
    schema = ModelSchema(
        "items",
        (
            Field("id", int, primary_key=True, generated=True),
            Field("name"),
            Field("secret"),
            Field("count", int),
        ),
    )
    options = ModelOptions(
        exclude=("secret",),
        readonly_fields=("count",),
        edit_fields=("id", "name", "count"),
        fields={"name": FieldOptions(label="Display name")},
    )
    options.validate(schema)
    assert options.parse_values(schema, {"name": "new"}, False) == {"name": "new"}
    for field in ("id", "secret", "count", "unknown"):
        with pytest.raises(ValidationError):
            options.parse_values(schema, {"name": "new", field: "4"}, False)
    assert options.visible_fields(schema)[1].label == "Display name"
    with pytest.raises(ValueError):
        ModelOptions(readonly_fields=("typo",)).validate(schema)


def test_defaults_are_omitted_only_explicitly():
    schema = ModelSchema(
        "items",
        (Field("id", int, primary_key=True, generated=True), Field("name", str, has_default=True)),
    )
    options = ModelOptions()
    assert options.parse_values(schema, {"name": "", "__default__name": "true"}, True) == {}
    assert options.parse_values(schema, {"name": ""}, True) == {"name": ""}
