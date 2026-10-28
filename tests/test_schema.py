from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

import pytest

from quite_admin import Field, FieldOptions, ModelOptions, ModelSchema
from quite_admin.errors import NotFound, ValidationError


class Status(Enum):
    DRAFT = "draft"
    ACTIVE = "active"


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
