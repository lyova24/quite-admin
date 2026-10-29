from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError, ValidationError
from tortoise.expressions import Q
from tortoise.fields import JSONField
from tortoise.transactions import in_transaction

from quite_admin.errors import Conflict, NotFound
from quite_admin.errors import ValidationError as AdminValidationError
from quite_admin.schema import Field, ModelSchema, Query, RecordPage

from ._queries import tortoise_filters
from ._tortoise_relations import TortoiseRelations


class TortoiseAdapter(TortoiseRelations):
    """Discovery happens after host startup, when Tortoise has initialized raw FK fields."""

    def __init__(self, *, models: Iterable[type] = (), apps: Iterable[str] | None = None) -> None:
        self.models = tuple(models)
        self.apps = tuple(apps) if apps is not None else None

    def discover(self) -> Iterable[type]:
        models = set(self.models)
        for name, app in Tortoise.apps.items():
            if self.apps is None or name in self.apps:
                models.update(app.values())
        return sorted(models, key=lambda model: (model.__module__, model.__name__))

    def describe(self, model: type) -> ModelSchema:
        fields = []
        if not model._meta._inited:
            raise ValueError("Initialize Tortoise in the host lifespan before discovering models.")
        foreign_keys = {}
        for relation_name in model._meta.fk_fields | model._meta.o2o_fields:
            relation = model._meta.fields_map[relation_name]
            foreign_keys[relation.source_field] = (
                f"{relation.related_model._meta.db_table}.{relation.to_field}"
            )
        for name in model._meta.fields_db_projection:
            item = model._meta.fields_map[name]
            python_type = item.field_type
            is_json = isinstance(item, JSONField)
            if is_json:
                python_type = object  # JSONField accepts arrays, objects and scalars.
            generated = bool(
                item.generated
                or getattr(item, "auto_now", False)
                or getattr(item, "auto_now_add", False)
            )
            fields.append(
                Field(
                    name=name,
                    python_type=python_type,
                    kind="json" if is_json else None,
                    primary_key=item.pk,
                    nullable=item.null,
                    generated=generated,
                    read_only=generated,
                    has_default=item.default is not None,
                    max_length=getattr(item, "max_length", None),
                    foreign_key=foreign_keys.get(name),
                )
            )
        return ModelSchema(name=model._meta.db_table, fields=tuple(fields))

    def _record(self, model: type, item: Any) -> dict[str, Any]:
        return {field.name: getattr(item, field.name) for field in self.describe(model).fields}

    async def list(self, model: type, query: Query) -> RecordPage:
        query.validate(self.describe(model))
        statement = tortoise_filters(model.all(), query)
        if query.search and query.search_fields:
            statement = statement.filter(
                Q(
                    *(Q(**{f"{name}__icontains": query.search}) for name in query.search_fields),
                    join_type="OR",
                )
            )
        total = await statement.count()
        pk = model._meta.pk_attr
        order = query.order_by or pk
        ordering = [("-" if query.descending else "") + order]
        if order != pk:
            ordering.append(pk)
        items = await statement.order_by(*ordering).offset(query.offset).limit(query.limit)
        return RecordPage([query.project(self._record(model, item)) for item in items], total)

    async def get(self, model: type, key: Mapping[str, Any]) -> dict[str, Any] | None:
        self.describe(model).validate_key(key)
        item = await model.get_or_none(**key)
        return self._record(model, item) if item is not None else None

    async def _write(
        self,
        model: type,
        action: str,
        values: Mapping[str, Any],
        key: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            async with in_transaction(model._meta.default_connection) as connection:
                if action == "create":
                    item = await model.create(using_db=connection, **values)
                else:
                    item = (
                        await model.filter(**key).using_db(connection).select_for_update().first()
                    )
                    if item is None:
                        raise NotFound("Record not found.")
                    if action == "delete":
                        await item.delete(using_db=connection)
                        return None
                    for name, value in values.items():
                        setattr(item, name, value)
                    if values:
                        await item.save(using_db=connection, update_fields=list(values))
                await item.refresh_from_db(using_db=connection)
                return self._record(model, item)
        except IntegrityError as exc:
            raise Conflict("The operation conflicts with a database constraint.") from exc
        except ValidationError as exc:
            raise AdminValidationError({"__all__": "The model rejected these values."}) from exc

    async def create(self, model: type, values: Mapping[str, Any]) -> dict[str, Any]:
        self.describe(model).validate_values(values, creating=True)
        return await self._write(model, "create", values)

    async def update(
        self, model: type, key: Mapping[str, Any], values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.describe(model).validate_key(key)
        self.describe(model).validate_values(values, creating=False)
        return await self._write(model, "update", values, key)

    async def delete(self, model: type, key: Mapping[str, Any]) -> None:
        self.describe(model).validate_key(key)
        await self._write(model, "delete", {}, key)
