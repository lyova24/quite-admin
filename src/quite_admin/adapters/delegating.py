from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..schema import Query, RecordPage
from .base import Adapter


class DelegatingAdapter:
    """Reuse reads/metadata while overriding writes with application services.

    Optional relationship writes are deliberately not forwarded: an overridden update
    must never be bypassed by the delegate's atomic relationship-save implementation.
    Implement RelationAdapter explicitly when the service supports that operation.
    """

    def __init__(self, delegate: Adapter) -> None:
        self.delegate = delegate

    def discover(self):
        return self.delegate.discover()

    def describe(self, model):
        return self.delegate.describe(model)

    async def list(self, model: Any, query: Query) -> RecordPage:
        query.validate(self.describe(model))
        return await self.delegate.list(model, query)

    async def get(self, model: Any, key: Mapping[str, Any]):
        self.describe(model).validate_key(key)
        return await self.delegate.get(model, key)

    async def create(self, model: Any, values: Mapping[str, Any]):
        return await self.delegate.create(model, values)

    async def update(self, model: Any, key: Mapping[str, Any], values: Mapping[str, Any]):
        return await self.delegate.update(model, key, values)

    async def delete(self, model: Any, key: Mapping[str, Any]):
        return await self.delegate.delete(model, key)
