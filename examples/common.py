"""Local demo only. Production applications supply their own models and DB lifespan."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from quite_admin import Admin, FieldOptions, ModelOptions, Page, PasswordAuth
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    pinned: Mapped[bool] = mapped_column(default=False)


def make_demo():
    engine = create_engine(os.getenv("QUITE_ADMIN_DEMO_DB", "sqlite:///quite-admin-demo.db"))
    sessions = sessionmaker(engine)
    password = os.environ["QUITE_ADMIN_PASSWORD"]
    admin = Admin(
        auth=PasswordAuth.single_user("admin", password),
        secret_key=os.getenv("QUITE_ADMIN_SECRET", secrets.token_urlsafe(48)),
        adapters=[SQLAlchemyAdapter(sessions, base=Base)],
        templates_dir=Path(__file__).parent / "templates",
        secure_cookies=False,  # This example runs over localhost HTTP.
    )
    admin.register(Customer, options=ModelOptions(readonly_fields=("joined_at",)))
    admin.register(Order, options=ModelOptions(readonly_fields=("created_at",)))
    admin.register(
        Product,
        options=ModelOptions(
            list_fields=("id", "name", "category", "price", "stock", "active"),
            fields={"stock": FieldOptions(help_text="Available units in the warehouse.")},
        ),
    )

    async def report(request):
        from anyio import to_thread

        def counts():
            with sessions() as session:
                return {
                    "customer_count": session.scalar(select(func.count()).select_from(Customer)),
                    "order_count": session.scalar(select(func.count()).select_from(Order)),
                }

        return await to_thread.run_sync(counts)

    admin.add_page(Page("report", "Store report", "report.html", context=report))
    return admin, engine, sessions


def seed(engine, sessions):
    Base.metadata.create_all(engine)
    with sessions.begin() as session:
        if session.scalar(select(func.count()).select_from(Product)):
            return
        session.add_all(
            [
                Customer(name="Alex Morgan", email="alex@example.com"),
                Customer(name="Jamie Park", email="jamie@example.com"),
                Customer(name="Sam Rivera", email="sam@example.com", active=False),
                Customer(name="Robin Chen", email="robin@example.com"),
                Customer(name="Taylor Reed", email="taylor@example.com"),
                Customer(name="Jordan Ellis", email="jordan@example.com"),
            ]
        )
        session.add_all(
            [
                Product(
                    name="Everyday notebook",
                    category="Stationery",
                    price=Decimal("18.00"),
                    stock=124,
                ),
                Product(
                    name="Ceramic pour-over", category="Kitchen", price=Decimal("42.00"), stock=38
                ),
                Product(
                    name="Linen tote", category="Accessories", price=Decimal("24.00"), stock=86
                ),
                Product(
                    name="Desk organizer", category="Workspace", price=Decimal("36.00"), stock=52
                ),
                Product(name="Morning blend", category="Coffee", price=Decimal("16.50"), stock=210),
                Product(
                    name="Brass bookmark",
                    category="Stationery",
                    price=Decimal("12.00"),
                    stock=0,
                    active=False,
                ),
                Product(name="Glass carafe", category="Kitchen", price=Decimal("28.00"), stock=67),
                Product(
                    name="Weekly planner", category="Stationery", price=Decimal("22.00"), stock=95
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Order(
                    customer_id=index % 6 + 1,
                    total=Decimal("42.00"),
                    status="completed" if index % 2 else "pending",
                )
                for index in range(8)
            ]
        )
        session.add(
            Note(title="Welcome to Quite Admin", body="Make yourself at home.", pinned=True)
        )
