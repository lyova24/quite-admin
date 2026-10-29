"""Request-scoped write lifecycle, independent of templates and ORM implementations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request

    from .auth import Identity


@dataclass(frozen=True)
class Operation:
    request: Request
    identity: Identity
    collection: str
    model: Any
    action: str
    key: Mapping[str, Any] | None
    values: Mapping[str, Any]
    relations: Mapping[str, tuple[Mapping[str, Any], ...]]
    record: Mapping[str, Any]


BeforeWrite = Callable[[Operation], None | Awaitable[None]]
AfterWrite = Callable[[Operation, Mapping[str, Any] | None], None | Awaitable[None]]


@dataclass(frozen=True)
class OperationHooks:
    before_write: BeforeWrite | None = None
    after_write: AfterWrite | None = None


_operation: ContextVar[Operation | None] = ContextVar("quite_admin_operation", default=None)


def current_operation() -> Operation | None:
    """Available to services/ORM hooks during admin writes; None outside that scope."""
    return _operation.get()
