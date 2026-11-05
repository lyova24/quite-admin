from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..pagination import WindowAdapter
from ..schema import LEGACY_FILTER_OPERATORS, Query, RecordPage
from .base import Adapter


class DelegatingAdapter:
    """Reuse reads/metadata while overriding writes with application services.

    Optional relationship writes are deliberately not forwarded: an overridden update
    must never be bypassed by the delegate's atomic relationship-save implementation.
    Implement RelationAdapter explicitly when the service supports that operation.
    """

    def __init__(self, delegate: Adapter) -> None:
        self.delegate = delegate
        # Preserve optional reads only when they cannot bypass a subclass's list
        # policy. Do not advertise windows for readers that cannot execute them.
        if (
            isinstance(delegate, WindowAdapter)
            and getattr(self.list, "__func__", None) is DelegatingAdapter.list
            and not hasattr(self, "list_window")
        ):
            self.list_window = self._list_window

    async def _list_window(self, model, query, *, after=None, before=None):
        if getattr(self.list, "__func__", None) is not DelegatingAdapter.list:
            raise ValueError("Implement list_window explicitly when overriding list.")
        query.validate(self.describe(model))
        return await self.delegate.list_window(model, query, after=after, before=before)

    @property
    def supports_window_sorting(self):
        return getattr(self.list, "__func__", None) is DelegatingAdapter.list and getattr(
            self.delegate, "supports_window_sorting", False
        )

    @property
    def supported_filter_operators(self):
        return getattr(self.delegate, "supported_filter_operators", LEGACY_FILTER_OPERATORS)

    @property
    def supports_key_search(self):
        return getattr(self.delegate, "supports_key_search", False)

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
