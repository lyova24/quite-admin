# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "quite-admin[sqlalchemy,fastapi]>=0.8.1,<0.9",
#     "uvicorn>=0.30,<1",
# ]
# ///
"""A standalone local back office. Run with: uv run --script quickstart.py."""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import uvicorn
from anyio import to_thread
from fastapi import FastAPI
from sqlalchemy import Enum, ForeignKey, Numeric, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from quite_admin import Admin, PasswordAuth
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True)
    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(
        Enum("pending", "paid", "shipped", native_enum=False), default="pending"
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    customer: Mapped[Customer | None] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    order: Mapped[Order] = relationship(back_populates="items")


def create_app(data_dir: Path | None = None) -> FastAPI:
    password = os.environ["QUITE_ADMIN_PASSWORD"]
    data_dir = data_dir or Path(__file__).resolve().parent / ".quite-admin" / "quickstart"
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'shop.db'}")
    sessions = sessionmaker(engine)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    def seed():
        Base.metadata.create_all(engine)
        with sessions.begin() as session:
            if session.scalar(select(Customer.id).limit(1)) is None:
                session.add_all(
                    [
                        Customer(
                            name="Alex Morgan",
                            email="alex@example.test",
                            orders=[
                                Order(
                                    name="Starter order",
                                    items=[
                                        OrderItem(
                                            name="Notebook", quantity=2, unit_price=Decimal("12.50")
                                        ),
                                        OrderItem(
                                            name="Desk lamp",
                                            quantity=1,
                                            unit_price=Decimal("39.00"),
                                        ),
                                    ],
                                )
                            ],
                        ),
                        Customer(name="Sam Lee", email="sam@example.test"),
                    ]
                )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await to_thread.run_sync(seed)
            yield
        finally:
            await to_thread.run_sync(engine.dispose)

    app = FastAPI(title="Orders back office", lifespan=lifespan)
    admin = Admin(
        title="Orders back office",
        auth=PasswordAuth.single_user("admin", password),
        secret_key=os.getenv("QUITE_ADMIN_SECRET", secrets.token_urlsafe(48)),
        adapters=[SQLAlchemyAdapter(sessions, base=Base)],
        storage=data_dir / "history.sqlite3",
        secure_cookies=False,  # This example serves local HTTP only.
    )
    admin.mount_fastapi(app)
    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
