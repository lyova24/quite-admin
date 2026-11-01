from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from anyio import to_thread
from sqlalchemy import JSON, Column, String, Text, and_, func, inspect, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from quite_admin.concurrency import CheckedWrites, check_record, sqlite_session_lock
from quite_admin.errors import Conflict, NotFound, ValidationError
from quite_admin.pagination import (
    WindowReads,
    finish_window,
    validate_window,
)
from quite_admin.schema import FILTER_OPERATORS, Field, ModelSchema, Query, RecordPage

from ._queries import paginate, predicates, search_predicate, validate_query
from ._sql_timeout import read_timeout, validate_timeout
from ._sql_types import integer_bounds
from ._sqlalchemy_relations import SQLAlchemyRelations


class SQLAlchemyAdapter(CheckedWrites, SQLAlchemyRelations, WindowReads):
    """SQLAlchemy 2.x / SQLModel, sync or async. Pass a session *factory*, not a session."""

    supports_related_filters = True
    supports_key_search = True
    supported_filter_operators = FILTER_OPERATORS

    def __init__(
        self,
        session_factory: Callable,
        *,
        base: Any = None,
        models: Iterable[type] = (),
        async_mode: bool | None = None,
        query_timeout: float | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.query_timeout = validate_timeout(query_timeout)
        self.base = base
        self.models = tuple(models)
        session_class = getattr(session_factory, "class_", Session)
        self.async_mode = (
            async_mode
            if async_mode is not None
            else (
                isinstance(session_factory, async_sessionmaker)
                or (isinstance(session_class, type) and issubclass(session_class, AsyncSession))
            )
        )

    def discover(self) -> Iterable[type]:
        discovered = set(self.models)
        if self.base is not None:
            registry = getattr(self.base, "registry", self.base)
            # SQLModel exposes _sa_registry instead of DeclarativeBase.registry.
            registry = getattr(self.base, "_sa_registry", registry)
            discovered.update(mapper.class_ for mapper in registry.mappers)
        return sorted(discovered, key=lambda model: (model.__module__, model.__name__))

    def describe(self, model: type) -> ModelSchema:
        mapper = inspect(model)
        fields = []
        for attribute in mapper.column_attrs:
            column = attribute.columns[0]
            try:
                python_type = column.type.python_type
            except (NotImplementedError, AttributeError):
                python_type = object
                # SQLModel's native string decorator does not expose python_type.
                # Do not infer arbitrary TypeDecorator codecs from their SQL impl.
                try:
                    from sqlmodel.sql.sqltypes import AutoString
                except ImportError:
                    pass
                else:
                    if isinstance(column.type, AutoString):
                        python_type = str
            is_column = isinstance(column, Column)
            pk = bool(is_column and column.primary_key)
            default = bool(
                is_column and (column.default is not None or column.server_default is not None)
            )
            computed = bool(
                is_column and (column.computed is not None or column.identity is not None)
            )
            generated = computed or (
                pk
                and (
                    default
                    or (
                        python_type is int
                        and len(mapper.primary_key) == 1
                        and column.autoincrement is not False
                    )
                )
            )
            # String-based Enum columns need choices without a Python enum class.
            choices = tuple(getattr(column.type, "enums", ()) or ())
            if getattr(column.type, "enum_class", None) is not None:
                python_type = column.type.enum_class
                choices = ()
            is_json = isinstance(column.type, JSON)
            if is_json:
                python_type = object
            fields.append(
                Field(
                    name=attribute.key,
                    python_type=python_type,
                    kind="json" if is_json else None,
                    nullable=bool(getattr(column, "nullable", True)),
                    primary_key=pk,
                    generated=generated,
                    read_only=computed or not is_column,
                    has_default=default,
                    max_length=getattr(column.type, "length", None),
                    multiline=isinstance(column.type, Text),
                    choices=choices,
                    foreign_key=next((fk.target_fullname for fk in column.foreign_keys), None)
                    if is_column
                    else None,
                    **integer_bounds(column.type),
                )
            )
        return ModelSchema(name=mapper.local_table.name, fields=tuple(fields))

    async def _run(self, operation: Callable[[Session], Any], *, read: bool = False) -> Any:
        def execute(session):
            if read and self.query_timeout is not None:
                with read_timeout(session.connection(), self.query_timeout):
                    return operation(session)
            return operation(session)

        try:
            if self.async_mode:
                async with self.session_factory() as session:
                    return await session.run_sync(execute)

            def run() -> Any:
                with self.session_factory() as session:
                    return execute(session)

            return await to_thread.run_sync(run)
        except IntegrityError as exc:
            raise Conflict("The operation conflicts with a database constraint.") from exc
        except (DataError, OverflowError) as exc:
            raise ValidationError({"__all__": "The database rejected these values."}) from exc

    def _record(self, model: type, instance: Any, *, schema=None) -> dict[str, Any]:
        return {
            field.name: getattr(instance, field.name)
            for field in (schema or self.describe(model)).fields
        }

    async def list(self, model: type, query: Query) -> RecordPage:
        return await self._list(model, query)

    async def _list(self, model, query, *, after=None, before=None, window=False):
        schema = validate_query(self, model, query)
        if window:
            validate_window(schema, query, after, before)

        def operation(session: Session) -> RecordPage:
            statement = (
                select(*(getattr(model, name).label(name) for name in query.columns))
                if query.columns
                else select(model)
            )
            statement = statement.where(
                *predicates(
                    query,
                    lambda name: getattr(model, name),
                    text_column=lambda name: getattr(model, name).cast(String),
                )
            )
            for item in query.related:
                prop = inspect(model).relationships[item.relation]
                condition = and_(
                    *(
                        getattr(prop.mapper.class_, name) == value
                        for name, value in item.key.items()
                    )
                )
                relation = getattr(model, item.relation)
                statement = statement.where(
                    relation.any(condition) if prop.uselist else relation.has(condition)
                )
            search = search_predicate(
                query,
                lambda name: getattr(model, name),
                text_column=lambda name: getattr(model, name).cast(String),
            )
            if search is not None:
                statement = statement.where(search)
            count = (
                None
                if window
                else session.scalar(select(func.count()).select_from(statement.subquery()))
            )

            def column(name):
                return getattr(model, name)

            statement = paginate(
                statement, query, schema, column, after=after, before=before, window=window
            )
            if query.columns:
                records = [dict(row) for row in session.execute(statement).mappings()]
            else:
                records = [
                    self._record(model, item, schema=schema)
                    for item in session.scalars(statement).unique().all()
                ]
            return (
                finish_window(schema, query, records, after, before)
                if window
                else RecordPage(records, count or 0)
            )

        return await self._run(operation, read=True)

    async def get(self, model: type, key: Mapping[str, Any]) -> dict[str, Any] | None:
        self.describe(model).validate_key(key)

        def operation(session: Session) -> dict[str, Any] | None:
            item = session.get(model, dict(key))
            return self._record(model, item) if item is not None else None

        return await self._run(operation, read=True)

    async def create(self, model: type, values: Mapping[str, Any]) -> dict[str, Any]:
        self.describe(model).validate_values(values, creating=True)

        def operation(session: Session) -> dict[str, Any]:
            with session.begin():
                item = model(**values)
                session.add(item)
                session.flush()
                session.refresh(item)
                return self._record(model, item)

        return await self._run(operation)

    async def update(
        self, model: type, key: Mapping[str, Any], values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.describe(model).validate_key(key)
        self.describe(model).validate_values(values, creating=False)

        def operation(session: Session) -> dict[str, Any]:
            with session.begin():
                sqlite_session_lock(session)
                item = session.get(model, dict(key), with_for_update=True)
                if item is None:
                    raise NotFound("Record not found.")
                check_record(model, self._record(model, item))
                for name, value in values.items():
                    setattr(item, name, value)
                session.flush()
                session.refresh(item)
                return self._record(model, item)

        return await self._run(operation)

    async def delete(self, model: type, key: Mapping[str, Any]) -> None:
        self.describe(model).validate_key(key)

        def operation(session: Session) -> None:
            with session.begin():
                sqlite_session_lock(session)
                item = session.get(model, dict(key), with_for_update=True)
                if item is None:
                    raise NotFound("Record not found.")
                session.delete(item)
                session.flush()

        await self._run(operation)
