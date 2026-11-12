"""Additional fictional models demonstrating the public customization interfaces.

These tables are deliberately separate from the original shop tables so an existing
local example database can gain the showcase without a schema migration.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from anyio import to_thread
from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic import Field as PydanticField
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    Numeric,
    String,
    Text,
    Uuid,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from examples.base import Base
from quite_admin import Field, FieldOptions, ModelOptions, OperationHooks, RecordAction
from quite_admin.auth import hash_password
from quite_admin.errors import ValidationError


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    parent: Mapped[Folder | None] = relationship(remote_side="Folder.id", back_populates="children")
    children: Mapped[list[Folder]] = relationship(back_populates="parent")
    samples: Mapped[list[FieldSample]] = relationship(back_populates="folder")


class FieldSample(Base):
    __tablename__ = "field_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(
        Enum("draft", "published", "archived", name="sample_status", native_enum=False),
        default="draft",
    )
    public_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    quantity: Mapped[int] = mapped_column(default=1)
    ratio: Mapped[float] = mapped_column(Float, default=1.0)
    website: Mapped[str] = mapped_column(String(240), default="https://example.com/catalog")
    ticket: Mapped[str] = mapped_column(String(60), default="DEMO-42")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    binary_preview: Mapped[bytes] = mapped_column(LargeBinary, default=b"Fictional sample")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    api_key: Mapped[str] = mapped_column(String(80), default="fictional-hidden-example")
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    folder: Mapped[Folder | None] = relationship(back_populates="samples")


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class RegionalPrice(Base):
    __tablename__ = "regional_prices"
    region: Mapped[str] = mapped_column(String(8), primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="sample_currency", native_enum=False), default=Currency.USD
    )
    alerts: Mapped[list[PriceAlert]] = relationship(back_populates="regional_price")


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        ForeignKeyConstraint(["region", "sku"], ["regional_prices.region", "regional_prices.sku"]),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(8))
    sku: Mapped[str] = mapped_column(String(40))
    threshold: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    regional_price: Mapped[RegionalPrice] = relationship(back_populates="alerts")


class ReferenceRate(Base):
    __tablename__ = "reference_rates"
    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 4))


class DemoAccount(Base):
    __tablename__ = "demo_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    password_hash: Mapped[str] = mapped_column(String(200))


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = PydanticField(min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = PydanticField(min_length=1, max_length=100)
    active: bool = True
    new_password: SecretStr = PydanticField(min_length=8, max_length=128)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = PydanticField(
        default=None, min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]*$"
    )
    display_name: str | None = PydanticField(default=None, min_length=1, max_length=100)
    active: bool | None = None
    new_password: SecretStr | None = PydanticField(default=None, min_length=8, max_length=128)


def validate_showcase_write(operation):
    """Use a pre-write hook for business validation, without recording user values."""
    names = {
        FieldSample: ("quantity", "ratio"),
        RegionalPrice: ("price",),
        PriceAlert: ("threshold",),
    }.get(operation.model, ())
    errors = {
        name: "Use a value of zero or greater."
        for name in names
        if operation.values.get(name) is not None and operation.values[name] < 0
    }
    if errors:
        raise ValidationError(errors)


def configure_showcase(admin, adapter):
    admin.hooks = OperationHooks(before_write=validate_showcase_write)
    admin.register(
        Folder,
        options=ModelOptions(
            group="Showcase",
            record_label="name",
            list_fields=("id", "name", "parent_id"),
            readonly_relations=("samples",),
            fields={
                "parent_id": FieldOptions(relation_label="name"),
                "name": FieldOptions(help_text="Choose a parent to build a folder tree."),
            },
        ),
    )

    async def archive_sample(operation):
        return await adapter.update(operation.model, operation.key, {"status": "archived"})

    async def publish_sample(operation):
        return await adapter.update(operation.model, operation.key, {"status": "published"})

    admin.register(
        FieldSample,
        options=ModelOptions(
            group="Showcase",
            label="Field samples",
            record_label="title",
            list_fields=(
                "id",
                "title",
                "status",
                "public_id",
                "website",
                "ticket",
                "description",
                "payload",
                "folder_id",
            ),
            readonly_fields=("created_at", "binary_preview"),
            fields={
                "status": FieldOptions(
                    help_text="Choose a stage, or use the record actions below."
                ),
                "public_id": FieldOptions(
                    label="Public UUID", help_text="A UUID, separate from the record ID."
                ),
                "quantity": FieldOptions(
                    help_text="Zero or more units. Negative values are rejected."
                ),
                "ratio": FieldOptions(help_text="A nonnegative floating-point value."),
                "website": FieldOptions(
                    display="url", help_text="A complete HTTP or HTTPS address."
                ),
                "ticket": FieldOptions(
                    label="Issue",
                    display="url",
                    url_template="https://example.com/issues/{value}",
                    template="ticket_input.html",
                    parser=lambda value: str(value).strip().upper(),
                    formatter=lambda value: str(value).upper(),
                    help_text="Issue keys are saved in uppercase and linked to their detail page.",
                ),
                "description": FieldOptions(
                    display="multiline", help_text="Line breaks are preserved."
                ),
                "payload": FieldOptions(
                    display="json", help_text="Structured settings with a JSON preview."
                ),
                "folder_id": FieldOptions(relation_label="name"),
                "binary_preview": FieldOptions(label="Binary preview"),
            },
            actions=(
                RecordAction("archive", "Archive sample", archive_sample),
                RecordAction("publish", "Publish sample", publish_sample),
            ),
        ),
    )
    admin.register(
        RegionalPrice,
        options=ModelOptions(
            group="Showcase",
            label="Regional prices",
            list_fields=("region", "sku", "price", "currency"),
            fields={
                "region": FieldOptions(
                    label="Region", help_text="Part of the composite record key."
                ),
                "sku": FieldOptions(label="SKU", help_text="Part of the composite record key."),
                "price": FieldOptions(help_text="Zero or greater; validated before saving."),
            },
        ),
    )
    admin.register(
        PriceAlert,
        options=ModelOptions(
            group="Showcase",
            label="Price alerts",
            record_label="title",
            list_fields=("id", "title", "region", "sku", "threshold"),
            fields={
                "threshold": FieldOptions(
                    help_text="Zero or greater. The selected price supplies both Region and SKU."
                ),
            },
        ),
    )
    admin.register(
        ReferenceRate,
        options=ModelOptions(
            group="Showcase",
            label="Reference rates",
            record_label="code",
            can_create=False,
            can_edit=False,
            can_delete=False,
            fields={"value": FieldOptions(help_text="Fictional reference data; viewing only.")},
        ),
    )

    async def create_account(operation, payload):
        values = payload.model_dump(exclude={"new_password"}, exclude_unset=True)
        values["password_hash"] = await to_thread.run_sync(
            hash_password, payload.new_password.get_secret_value()
        )
        return await adapter.create(operation.model, values)

    async def update_account(operation, payload, *, guard):
        values = payload.model_dump(exclude={"new_password"}, exclude_unset=True)
        if payload.new_password is not None:
            values["password_hash"] = await to_thread.run_sync(
                hash_password, payload.new_password.get_secret_value()
            )
        # Forward the optimistic-lock guard into the same database transaction.
        return await adapter.save_checked(
            operation.model, operation.key, values, operation.relations, guard=guard
        )

    admin.register(
        DemoAccount,
        options=ModelOptions(
            group="Showcase",
            label="Demo accounts",
            record_label="username",
            list_fields=("id", "username", "display_name", "active", "created_at"),
            input_fields=(
                Field(
                    "new_password",
                    label="New password",
                    kind="password",
                    nullable=True,
                    max_length=128,
                ),
            ),
            create_schema=AccountCreate,
            update_schema=AccountUpdate,
            create_handler=create_account,
            update_handler=update_account,
            fields={
                "username": FieldOptions(
                    help_text="Lowercase letters, numbers and underscores; start with a letter."
                ),
                "display_name": FieldOptions(label="Display name"),
                "new_password": FieldOptions(
                    help_text="8–128 characters. Leave blank on edit to keep the current password."
                ),
            },
        ),
    )


def seed_showcase(session):
    """Fill only empty new tables; restarting never replaces a user's local edits."""
    folder = session.scalar(select(Folder).order_by(Folder.id))
    if folder is None:
        folder = Folder(name="Catalog folder")
        session.add(folder)
        session.add_all(
            Folder(name=f"Folder {index:02d}", parent=folder if index <= 3 else None)
            for index in range(1, 36)
        )
        session.flush()
    if session.scalar(select(FieldSample.id).limit(1)) is None:
        session.add(
            FieldSample(
                title="Field control showcase",
                public_id=UUID("2a7d9c7b-1965-4a0a-88a5-5cf6f6a1b001"),
                description="First line of the sample.\nSecond line keeps its own paragraph.",
                payload={"theme": "blue", "capacity": 12, "enabled": True},
                folder=folder,
            )
        )
    if session.scalar(select(RegionalPrice.region).limit(1)) is None:
        session.add_all(
            (
                RegionalPrice(region="US", sku="NOTE-001", price=Decimal("18.00"), currency="USD"),
                RegionalPrice(region="EU", sku="NOTE-001", price=Decimal("17.00"), currency="EUR"),
                RegionalPrice(region="GB", sku="NOTE-001", price=Decimal("15.00"), currency="GBP"),
            )
        )
    if session.scalar(select(PriceAlert.id).limit(1)) is None:
        prices = session.scalars(
            select(RegionalPrice).order_by(RegionalPrice.region, RegionalPrice.sku).limit(2)
        ).all()
        session.add_all(
            PriceAlert(
                title=f"{price.region} price watch",
                regional_price=price,
                threshold=Decimal("15.00"),
            )
            for price in prices
        )
    if session.scalar(select(ReferenceRate.code).limit(1)) is None:
        session.add_all(
            ReferenceRate(code=code, value=value)
            for code, value in (
                ("USD", Decimal("1.0000")),
                ("EUR", Decimal("0.9200")),
                ("GBP", Decimal("0.7900")),
            )
        )
    if session.scalar(select(DemoAccount.id).limit(1)) is None:
        session.add(
            DemoAccount(
                username="demo_editor",
                display_name="Demo editor",
                password_hash=hash_password(secrets.token_urlsafe(24)),
            )
        )
