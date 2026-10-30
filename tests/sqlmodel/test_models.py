"""SQLModel-specific metadata, Python defaults and Pydantic/table separation."""

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, String
from sqlalchemy.orm import registry
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

from quite_admin import Filter, Query


class State(StrEnum):
    DRAFT = "draft"
    LIVE = "live"


async def test_sqlmodel_registry_defaults_types_and_non_table_schemas(sqlmodel_factory):
    class Base(SQLModel, registry=registry()):
        pass

    class Opaque(TypeDecorator):
        impl = String(80)
        cache_ok = True

    class ItemInput(Base):
        name: str

    class Item(ItemInput, table=True):
        __tablename__ = "typed_items"
        id: UUID = Field(default_factory=uuid4, primary_key=True)
        price: Decimal = Field(default=Decimal("12.50"), max_digits=12, decimal_places=2)
        state: State = Field(default=State.DRAFT)
        extra: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
        note: str | None = Field(default=None, max_length=80)
        opaque: str = Field(default="opaque", sa_column=Column(Opaque))

    # A second registry must never leak into base-scoped discovery.
    class OtherBase(SQLModel, registry=registry()):
        pass

    class Other(OtherBase, table=True):
        id: int | None = Field(default=None, primary_key=True)

    try:
        adapter = await sqlmodel_factory(Base)
        assert list(adapter.discover()) == [Item]
        assert ItemInput.model_validate({"name": "DTO"}).name == "DTO"
        schema = adapter.describe(Item)
        assert schema.by_name["name"].python_type is str
        assert schema.by_name["opaque"].kind == "unsupported"
        assert schema.by_name["id"].python_type is UUID
        assert schema.by_name["id"].generated
        assert schema.by_name["price"].python_type is Decimal
        assert schema.by_name["state"].python_type is State
        assert schema.by_name["extra"].kind == "json"
        assert schema.by_name["note"].nullable and schema.by_name["note"].max_length == 80
        saved = await adapter.create(Item, {"name": "Typed SQLModel"})
        assert isinstance(saved["id"], UUID)
        assert saved["price"] == Decimal("12.50") and saved["state"] is State.DRAFT
        assert saved["extra"] == {} and saved["note"] is None
        key = schema.parse_key(schema.record_key(saved))
        assert await adapter.get(Item, key) == saved
        changed = await adapter.update(Item, key, {"extra": {"nested": [1, True]}})
        assert changed["extra"] == {"nested": [1, True]}
        page = await adapter.list(
            Item, Query(filters=(Filter("state", "eq", State.DRAFT),), columns=("name",))
        )
        assert page.total == 1 and page.records == [{"name": "Typed SQLModel"}]
    finally:
        OtherBase._sa_registry.dispose()
