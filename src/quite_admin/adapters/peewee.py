from __future__ import annotations

import operator
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from datetime import date, datetime, time
from decimal import Decimal
from functools import reduce
from typing import Any
from uuid import UUID

import peewee as pw
from anyio import to_thread

from quite_admin.concurrency import CheckedWrites, check_record, guarded
from quite_admin.errors import Conflict, NotFound
from quite_admin.schema import Field, ModelSchema, Query, RecordPage

from ._peewee_relations import PeeweeRelations
from ._queries import ordering as order_expressions
from ._queries import predicates, validate_query


class PeeweeAdapter(CheckedWrites, PeeweeRelations):
    """Pass models explicitly or a project-specific base. Never scans unrelated global models."""

    supports_related_filters = True

    def __init__(self, *, models: Iterable[type] = (), base: type | None = None) -> None:
        self.models = tuple(models)
        self.base = base

    def discover(self) -> Iterable[type]:
        models = set(self.models)

        def descend(parent: type) -> None:
            for model in parent.__subclasses__():
                if model._meta.primary_key is not False:
                    models.add(model)
                descend(model)

        if self.base is not None:
            descend(self.base)
        return sorted(models, key=lambda model: (model.__module__, model.__name__))

    def _type(self, item: pw.Field) -> type:
        if isinstance(item, pw.ForeignKeyField):
            return self._type(item.rel_field)
        for field_type, python_type in (
            (pw.BooleanField, bool),
            (pw.IntegerField, int),
            (pw.FloatField, float),
            (pw.DecimalField, Decimal),
            (pw.DateTimeField, datetime),
            (pw.DateField, date),
            (pw.TimeField, time),
            (pw.UUIDField, UUID),
            (pw.TextField, str),
            (pw.CharField, str),
            (pw.BlobField, bytes),
        ):
            if isinstance(item, field_type):
                return python_type
        return object

    def describe(self, model: type) -> ModelSchema:
        primary = model._meta.primary_key
        keys = (
            set(primary.field_names)
            if isinstance(primary, pw.CompositeKey)
            else {primary.name}
            if primary is not False
            else set()
        )
        fields = []
        for item in model._meta.sorted_fields:
            # Use __data__ rather than relationship attributes to avoid lazy queries.
            fields.append(
                Field(
                    name=item.name,
                    python_type=self._type(item),
                    nullable=item.null,
                    primary_key=item.name in keys,
                    generated=isinstance(item, pw.AutoField),
                    has_default=item.default is not None,
                    max_length=getattr(item, "max_length", None),
                    choices=tuple(str(choice[0]) for choice in (item.choices or ())),
                    foreign_key=f"{item.rel_model._meta.table_name}.{item.rel_field.name}"
                    if isinstance(item, pw.ForeignKeyField)
                    else None,
                )
            )
        return ModelSchema(name=model._meta.table_name, fields=tuple(fields))

    def _record(self, model: type, item: Any) -> dict[str, Any]:
        return {field.name: item.__data__.get(field.name) for field in self.describe(model).fields}

    async def _run(self, model: type, operation: Callable[[], Any], *, write: bool = False) -> Any:
        def run() -> Any:
            database = model._meta.database
            # Open and close in the SAME worker; Peewee connections are thread-local.
            with database.connection_context():
                with (
                    (
                        database.atomic("IMMEDIATE")
                        if guarded() and isinstance(database, pw.SqliteDatabase)
                        else database.atomic()
                    )
                    if write
                    else nullcontext()
                ):
                    return operation()

        try:
            return await to_thread.run_sync(run)
        except pw.IntegrityError as exc:
            raise Conflict("The operation conflicts with a database constraint.") from exc

    def _where(self, model: type, key: Mapping[str, Any]) -> Any:
        return reduce(operator.and_, (getattr(model, name) == value for name, value in key.items()))

    def _locked_get(self, model, key):
        query = model.select().where(self._where(model, key))
        if guarded() and not isinstance(model._meta.database, pw.SqliteDatabase):
            query = query.for_update()
        return query.first()

    async def list(self, model: type, query: Query) -> RecordPage:
        validate_query(self, model, query)

        def operation() -> RecordPage:
            statement = model.select()
            for condition in self._filter_conditions(model, query):
                statement = statement.where(condition)
            if query.filters:
                statement = statement.where(
                    *predicates(query, lambda name: getattr(model, name), peewee=True)
                )
            if query.search and query.search_fields:
                # Peewee contains() escapes LIKE wildcards internally.
                statement = statement.where(
                    reduce(
                        operator.or_,
                        (
                            getattr(model, name).contains(query.search)
                            for name in query.search_fields
                        ),
                    )
                )
            total = statement.count()
            ordering = tuple(
                order_expressions(query, self.describe(model), lambda name: getattr(model, name))
            )
            items = statement.order_by(*ordering).offset(query.offset).limit(query.limit)
            return RecordPage([query.project(self._record(model, item)) for item in items], total)

        return await self._run(model, operation)

    async def get(self, model: type, key: Mapping[str, Any]) -> dict[str, Any] | None:
        self.describe(model).validate_key(key)

        def operation() -> dict[str, Any] | None:
            item = model.get_or_none(self._where(model, key))
            return self._record(model, item) if item is not None else None

        return await self._run(model, operation)

    async def create(self, model: type, values: Mapping[str, Any]) -> dict[str, Any]:
        self.describe(model).validate_values(values, creating=True)

        def operation() -> dict[str, Any]:
            item = model.create(**values)
            return self._record(model, item)

        return await self._run(model, operation, write=True)

    async def update(
        self, model: type, key: Mapping[str, Any], values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.describe(model).validate_key(key)
        self.describe(model).validate_values(values, creating=False)

        def operation() -> dict[str, Any]:
            item = self._locked_get(model, key)
            if item is None:
                raise NotFound("Record not found.")
            check_record(model, self._record(model, item))
            if values:
                for name, value in values.items():
                    setattr(item, name, value)
                item.save(only=[getattr(model, name) for name in values])
            return self._record(model, item)

        return await self._run(model, operation, write=True)

    async def delete(self, model: type, key: Mapping[str, Any]) -> None:
        self.describe(model).validate_key(key)

        def operation() -> None:
            item = self._locked_get(model, key)
            if item is None:
                raise NotFound("Record not found.")
            item.delete_instance()

        await self._run(model, operation, write=True)
