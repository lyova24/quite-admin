from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from anyio import Lock, to_thread
from sqlalchemy import JSON, MetaData, Table, and_, delete, func, insert, or_, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import TypeEngine

from quite_admin.concurrency import CheckedWrites, check_record, guarded
from quite_admin.errors import Conflict, NotFound
from quite_admin.schema import Field, ModelSchema, Query, RecordPage

from ._queries import ordering as order_expressions
from ._queries import predicates, validate_query
from ._sql_metadata import related_predicates
from ._sql_relations import SQLRelations


class SQLAdapter(CheckedWrites, SQLRelations):
    """Reflect SQL tables without importing any ORM models.

    Works with any ORM's database, using a separate SQLAlchemy Engine for access.
    Writes use database defaults and constraints; Python-side ORM hooks don't run.
    """

    supports_related_filters = True

    def __init__(
        self,
        engine: Engine | AsyncEngine,
        *,
        include_tables: Iterable[str] | None = None,
        exclude_tables: Iterable[str] = (),
        schema: str | None = None,
        column_types: Mapping[str, Mapping[str, TypeEngine[Any]]] | None = None,
    ) -> None:
        self.engine = engine
        self.include_tables = tuple(include_tables) if include_tables is not None else None
        self.exclude_tables = frozenset(exclude_tables)
        self.schema = schema
        self.column_types = {name: dict(columns) for name, columns in (column_types or {}).items()}
        if any(
            not isinstance(type_, TypeEngine)
            for columns in self.column_types.values()
            for type_ in columns.values()
        ):
            raise TypeError("column_types values must be SQLAlchemy type instances.")
        self._metadata: MetaData | None = None
        self._lock = Lock()

    async def _run(self, operation: Callable[[Connection], Any], *, write: bool = False) -> Any:
        try:
            if isinstance(self.engine, AsyncEngine):
                async with self.engine.begin() if write else self.engine.connect() as connection:

                    def execute(sync_connection):
                        if write and guarded() and sync_connection.dialect.name == "sqlite":
                            sync_connection.exec_driver_sql("BEGIN IMMEDIATE")
                        return operation(sync_connection)

                    return await connection.run_sync(execute)

            def run() -> Any:
                with self.engine.begin() if write else self.engine.connect() as connection:
                    if write and guarded() and connection.dialect.name == "sqlite":
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
                    return operation(connection)

            return await to_thread.run_sync(run)
        except IntegrityError as exc:
            raise Conflict("The operation conflicts with a database constraint.") from exc

    async def refresh(self) -> None:
        """Atomically replace cached metadata, e.g. after a host-managed migration."""
        async with self._lock:
            await self._reflect()

    async def _reflect(self) -> None:
        metadata = MetaData(schema=self.schema)

        def reflect(connection: Connection) -> None:
            metadata.reflect(
                bind=connection,
                views=False,
                resolve_fks=False,
                only=lambda name, meta: (
                    name not in self.exclude_tables
                    and (self.include_tables is None or name in self.include_tables)
                ),
            )

        await self._run(reflect)
        for name, columns in self.column_types.items():
            if name not in metadata.tables:
                raise ValueError(f"Unknown table in column_types: {name}")
            table = metadata.tables[name]
            for column, type_ in columns.items():
                if column not in table.c:
                    raise ValueError(f"Unknown column in column_types: {name}.{column}")
                table.c[column].type = type_
        self._metadata = metadata

    async def discover(self) -> Iterable[Table]:
        if self._metadata is None:
            async with self._lock:
                if self._metadata is None:
                    await self._reflect()
        return tuple(self._metadata.tables.values())

    def describe(self, model: Table) -> ModelSchema:
        fields = []
        for column in model.columns:
            try:
                python_type = column.type.python_type
            except (NotImplementedError, AttributeError):
                python_type = object
            default = column.server_default is not None
            generated = (
                column.computed is not None
                or column.identity is not None
                or (
                    column.primary_key
                    and (
                        default
                        or (
                            python_type is int
                            and len(model.primary_key.columns) == 1
                            and column.autoincrement is not False
                        )
                    )
                )
            )
            enum_class = getattr(column.type, "enum_class", None)
            is_json = isinstance(column.type, JSON)
            fields.append(
                Field(
                    name=column.name,
                    python_type=object if is_json else enum_class or python_type,
                    kind="json" if is_json else None,
                    nullable=column.nullable,
                    primary_key=column.primary_key,
                    generated=generated,
                    read_only=column.computed is not None or column.identity is not None,
                    has_default=default,
                    max_length=getattr(column.type, "length", None),
                    choices=() if enum_class else tuple(getattr(column.type, "enums", ()) or ()),
                    foreign_key=next((fk.target_fullname for fk in column.foreign_keys), None),
                )
            )
        return ModelSchema(model.name, tuple(fields))

    @staticmethod
    def _where(model: Table, key: Mapping[str, Any]) -> Any:
        return and_(*(model.c[name] == value for name, value in key.items()))

    async def list(self, model: Table, query: Query) -> RecordPage:
        validate_query(self, model, query)

        def operation(connection: Connection) -> RecordPage:
            statement = select(model)
            statement = statement.where(*predicates(query, model.c.__getitem__))
            if query.related:
                statement = statement.where(*related_predicates(model, query, self._links(model)))
            if query.search and query.search_fields:
                statement = statement.where(
                    or_(
                        *(
                            model.c[name].icontains(query.search, autoescape=True)
                            for name in query.search_fields
                        )
                    )
                )
            total = connection.scalar(select(func.count()).select_from(statement.subquery()))
            ordering = tuple(order_expressions(query, self.describe(model), model.c.__getitem__))
            rows = connection.execute(
                statement.order_by(*ordering).offset(query.offset).limit(query.limit)
            ).mappings()
            return RecordPage([query.project(row) for row in rows], total or 0)

        return await self._run(operation)

    async def get(self, model: Table, key: Mapping[str, Any]) -> dict[str, Any] | None:
        self.describe(model).validate_key(key)

        def operation(connection: Connection) -> dict[str, Any] | None:
            row = (
                connection.execute(select(model).where(self._where(model, key))).mappings().first()
            )
            return dict(row) if row is not None else None

        return await self._run(operation)

    async def create(self, model: Table, values: Mapping[str, Any]) -> dict[str, Any]:
        self.describe(model).validate_values(values, creating=True)

        def operation(connection: Connection) -> dict[str, Any]:
            result = connection.execute(insert(model).values(**values))
            key = dict(
                zip(
                    (column.name for column in model.primary_key.columns),
                    result.inserted_primary_key,
                    strict=True,
                )
            )
            row = connection.execute(select(model).where(self._where(model, key))).mappings().one()
            return dict(row)

        return await self._run(operation, write=True)

    async def update(
        self, model: Table, key: Mapping[str, Any], values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.describe(model).validate_key(key)
        self.describe(model).validate_values(values, creating=False)

        def operation(connection: Connection) -> dict[str, Any]:
            statement = select(model).where(self._where(model, key))
            current = connection.execute(statement.with_for_update()).mappings().first()
            if current is None:
                raise NotFound("Record not found.")
            check_record(model, current)
            if values:
                connection.execute(update(model).where(self._where(model, key)).values(**values))
            return dict(connection.execute(statement).mappings().one())

        return await self._run(operation, write=True)

    async def delete(self, model: Table, key: Mapping[str, Any]) -> None:
        self.describe(model).validate_key(key)

        def operation(connection: Connection) -> None:
            found = connection.execute(
                select(model).where(self._where(model, key)).with_for_update()
            ).first()
            if found is None:
                raise NotFound("Record not found.")
            connection.execute(delete(model).where(self._where(model, key)))

        await self._run(operation, write=True)
