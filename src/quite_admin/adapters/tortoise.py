from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError, ValidationError
from tortoise.expressions import Case, Q, When
from tortoise.fields import JSONField, TextField
from tortoise.transactions import in_transaction

from quite_admin.concurrency import CheckedWrites, check_record
from quite_admin.errors import Conflict, NotFound
from quite_admin.errors import ValidationError as AdminValidationError
from quite_admin.pagination import WindowReads, finish_window, validate_window, window_fields
from quite_admin.schema import FILTER_OPERATORS, Field, ModelSchema, Query, RecordPage

from ._queries import tortoise_filters, validate_query
from ._tortoise_relations import TortoiseRelations


class TortoiseAdapter(CheckedWrites, TortoiseRelations, WindowReads):
    """Discovery happens after host startup, when Tortoise has initialized raw FK fields."""

    supports_related_filters = True
    supports_key_search = True
    supported_filter_operators = FILTER_OPERATORS

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
                    multiline=isinstance(item, TextField),
                    foreign_key=foreign_keys.get(name),
                    minimum=item.constraints.get("ge") if python_type is int else None,
                    maximum=item.constraints.get("le") if python_type is int else None,
                )
            )
        return ModelSchema(name=model._meta.db_table, fields=tuple(fields))

    def _record(self, model: type, item: Any, *, schema=None) -> dict[str, Any]:
        return {
            field.name: getattr(item, field.name)
            for field in (schema or self.describe(model)).fields
        }

    async def list(self, model: type, query: Query) -> RecordPage:
        return await self._list(model, query)

    async def _list(self, model, query, *, after=None, before=None, window=False):
        schema = validate_query(self, model, query)
        if window:
            validate_window(schema, query, after, before)
        statement = tortoise_filters(model.all(), query)
        for item in query.related:
            statement = statement.filter(
                **{item.relation + "__" + name: value for name, value in item.key.items()}
            )
        search = (
            [Q(**{f"{name}__icontains": query.search}) for name in query.search_fields]
            if query.search
            else []
        )
        if query.search_key is not None:
            search.append(Q(**query.search_key))
        if search:
            statement = statement.filter(Q(*search, join_type="OR"))
        total = None if window else await statement.count()
        pk = model._meta.pk_attr
        order = query.order_by or pk
        reverse = window and before is not None
        ordering = []
        if window:
            fields = window_fields(schema, query)
            boundary = after if after is not None else before
            if boundary is not None:
                condition = prefix = None
                for index, field in enumerate(fields):
                    value = boundary[field.name]
                    descending = (query.descending if index == 0 else False) != reverse
                    part = (
                        Q(**{field.name + "__isnull": False}) if value is None and reverse else None
                    )
                    if value is not None:
                        suffix = "__lt" if descending else "__gt"
                        part = Q(**{field.name + suffix: value})
                        if field.nullable and not reverse:
                            part |= Q(**{field.name + "__isnull": True})
                    if part is not None:
                        part = prefix & part if prefix is not None else part
                        condition = part if condition is None else condition | part
                    equal = (
                        Q(**{field.name + "__isnull": True})
                        if value is None
                        else Q(**{field.name: value})
                    )
                    prefix = equal if prefix is None else prefix & equal
                statement = statement.filter(condition)
            for index, field in enumerate(fields):
                descending = (query.descending if index == 0 else False) != reverse
                if field.nullable:
                    annotation = "qa_window_null_" + str(index)
                    statement = statement.annotate(
                        **{
                            annotation: Case(
                                When(**{field.name + "__isnull": True}, then=1), default=0
                            )
                        }
                    )
                    ordering.append(("-" if reverse else "") + annotation)
                ordering.append(("-" if descending else "") + field.name)
        else:
            ordering = [("-" if query.descending else "") + order]
            if order != pk:
                ordering.append(pk)
        statement = statement.order_by(*ordering).limit(query.limit + int(window))
        if not window:
            statement = statement.offset(query.offset)
        if query.columns:
            records = await statement.values(*query.columns)
        else:
            records = [self._record(model, item, schema=schema) for item in await statement]
        return (
            finish_window(schema, query, records, after, before)
            if window
            else RecordPage(records, total)
        )

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
                    check_record(model, self._record(model, item))
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
        except OverflowError as exc:
            raise AdminValidationError({"__all__": "The database rejected these values."}) from exc

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
