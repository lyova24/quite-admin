from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from asyncpg import IntegrityConstraintViolationError
from gino import Gino
from sqlalchemy import JSON, String, and_, func, or_, select
from sqlalchemy.dialects import registry
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from quite_admin.errors import Conflict, NotFound
from quite_admin.schema import Field, ModelSchema, Query, RecordPage

from ._gino_relations import GinoRelations
from ._queries import ordering, predicates

# SQLAlchemy 1.3's entry-point loader depends on the removed pkg_resources module.
# Register GINO's own dialect through SQLAlchemy's public API instead. Import this
# adapter before the host opens its pool; no engines are created here.
registry.register("postgresql.asyncpg", "gino.dialects.asyncpg", "AsyncpgDialect")


class GinoAdapter(GinoRelations):
    """GINO 1.0 / SQLAlchemy 1.3 / PostgreSQL, using the host-owned Gino pool.

    Install quite-admin[gino-legacy]. Discover imported subclasses of db.Model,
    or restrict exposure with models=.
    Native model persistence is used for record writes. Application services must
    be connected explicitly through DelegatingAdapter, as with other adapters.
    """

    def __init__(self, db: Gino, *, models: Iterable[type] | None = None) -> None:
        self.db = db
        self.models = tuple(models) if models is not None else None
        if self.models is not None:
            for model in self.models:
                self._table(model)

    def _table(self, model: type):
        if not isinstance(model, type) or not issubclass(model, self.db.Model):
            raise ValueError("Pass GINO models belonging to this Gino instance.")
        table = model.__table__
        if table is None or table.metadata is not self.db:
            raise ValueError("A concrete GINO model from this Gino instance is required.")
        return table

    @staticmethod
    def _attribute(model: type, column: str) -> str:
        # GINO supports Column('database_name', ...) under a different attribute.
        return model._column_name_map.invert_get(column)

    def discover(self) -> Iterable[type]:
        if self.models is not None:
            return self.models
        result = set()

        def descend(base):
            for model in base.__subclasses__():
                if model.__table__ is not None and model.__table__.metadata is self.db:
                    result.add(model)
                descend(model)

        descend(self.db.Model)
        return sorted(result, key=lambda model: (model.__module__, model.__name__))

    def describe(self, model: type) -> ModelSchema:
        table = self._table(model)
        fields = []
        for column in table.columns:
            try:
                python_type = column.type.python_type
            except (NotImplementedError, AttributeError):
                python_type = object
            if isinstance(column.type, PGUUID):
                # SQLAlchemy 1.3 does not implement UUID.python_type. GINO's
                # asyncpg dialect always returns UUID values, including as_uuid=False.
                python_type = UUID
            default = column.default is not None or column.server_default is not None
            computed = column.computed is not None
            generated = computed or (
                column.primary_key
                and (
                    default
                    or (
                        python_type is int
                        and len(table.primary_key.columns) == 1
                        and column.autoincrement is not False
                    )
                )
            )
            choices = tuple(getattr(column.type, "enums", ()) or ())
            if getattr(column.type, "enum_class", None) is not None:
                python_type = column.type.enum_class
                choices = ()
            is_json = isinstance(column.type, JSON)
            fields.append(
                Field(
                    name=self._attribute(model, column.name),
                    python_type=object if is_json else python_type,
                    kind="json" if is_json else None,
                    nullable=column.nullable,
                    primary_key=column.primary_key,
                    generated=bool(generated),
                    read_only=computed,
                    has_default=default,
                    max_length=getattr(column.type, "length", None),
                    choices=choices,
                    foreign_key=next((fk.target_fullname for fk in column.foreign_keys), None),
                )
            )
        return ModelSchema(name=table.name, fields=tuple(fields))

    def _record(self, model: type, item: Any) -> dict[str, Any]:
        return {field.name: getattr(item, field.name) for field in self.describe(model).fields}

    def _where(self, model: type, key: Mapping[str, Any]):
        self.describe(model).validate_key(key)
        return and_(*(getattr(model, name) == value for name, value in key.items()))

    async def _page(self, model: type, query: Query, *, condition=None) -> RecordPage:
        schema = self.describe(model)
        query.validate(schema)
        statement = model.query
        conditions = list(predicates(query, lambda name: getattr(model, name)))
        if condition is not None:
            conditions.append(condition)
        if query.search and query.search_fields:
            conditions.append(
                or_(
                    *(
                        getattr(model, name)
                        .cast(String)
                        .ilike(
                            "%"
                            + query.search.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                            + "%",
                            escape="!",
                        )
                        for name in query.search_fields
                    )
                )
            )
        for expression in conditions:
            statement = statement.where(expression)
        # One operation-scoped connection; reads never open/commit a transaction.
        async with self.db.acquire(reuse=False, reusable=False) as connection:
            total = await connection.scalar(select([func.count()]).select_from(statement.alias()))
            rows = await connection.all(
                statement.order_by(*ordering(query, schema, lambda name: getattr(model, name)))
                .offset(query.offset)
                .limit(query.limit)
            )
        return RecordPage([query.project(self._record(model, row)) for row in rows], total or 0)

    async def list(self, model: type, query: Query) -> RecordPage:
        return await self._page(model, query)

    async def get(self, model: type, key: Mapping[str, Any]) -> dict[str, Any] | None:
        statement = model.query.where(self._where(model, key))
        async with self.db.acquire(reuse=False, reusable=False) as connection:
            item = await connection.first(statement)
        return self._record(model, item) if item is not None else None

    @asynccontextmanager
    async def _transaction(self):
        try:
            # Do not borrow/commit a surrounding host transaction. Native GINO
            # methods inside this scope receive this exact connection explicitly.
            async with self.db.transaction(reuse=False) as transaction:
                yield transaction.connection
        except IntegrityConstraintViolationError as exc:
            raise Conflict("The operation conflicts with a database constraint.") from exc

    async def _persist(self, connection, model, values, *, key=None):
        if key is None:
            item = await model.create(bind=connection, **values)
        else:
            item = await connection.first(
                model.query.where(self._where(model, key)).with_for_update()
            )
            if item is None:
                raise NotFound("Record not found.")
            if values:
                await item.update(**values).apply(bind=connection)
        # Reload all scalar columns, including database-triggered/default values.
        record = self._record(model, item)
        identity = {field.name: record[field.name] for field in self.describe(model).primary_keys}
        item = await connection.first(model.query.where(self._where(model, identity)))
        if item is None:
            raise NotFound("Record not found after saving.")
        return self._record(model, item)

    async def create(self, model: type, values: Mapping[str, Any]) -> dict[str, Any]:
        self.describe(model).validate_values(values, creating=True)
        async with self._transaction() as connection:
            return await self._persist(connection, model, values)

    async def update(
        self, model: type, key: Mapping[str, Any], values: Mapping[str, Any]
    ) -> dict[str, Any]:
        schema = self.describe(model)
        schema.validate_key(key)
        schema.validate_values(values, creating=False)
        async with self._transaction() as connection:
            return await self._persist(connection, model, values, key=key)

    async def delete(self, model: type, key: Mapping[str, Any]) -> None:
        statement = model.query.where(self._where(model, key)).with_for_update()
        async with self._transaction() as connection:
            item = await connection.first(statement)
            if item is None:
                raise NotFound("Record not found.")
            await item.delete(bind=connection)
