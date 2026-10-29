from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import String, func, inspect, or_, select
from sqlalchemy.orm import with_parent

from quite_admin.errors import Conflict, NotFound
from quite_admin.relations import Relation
from quite_admin.schema import Query, RecordPage

from ._queries import ordering as order_expressions
from ._queries import predicates
from ._sql_relations import _unique


class SQLAlchemyRelations:
    def relations(self, model: type) -> tuple[Relation, ...]:
        result = []
        for item in inspect(model).relationships:
            reverse = item.direction.name == "ONETOMANY"
            source = (
                tuple(
                    attribute.key
                    for column in item.local_columns
                    for attribute in inspect(model).column_attrs
                    if column in attribute.columns
                )
                if not reverse and item.secondary is None
                else ()
            )
            target = (
                tuple(
                    attribute.key
                    for column in item.remote_side
                    for attribute in inspect(item.mapper.class_).column_attrs
                    if column in attribute.columns
                )
                if reverse
                else ()
            )
            nullable = all(
                column.nullable for column in (item.remote_side if reverse else item.local_columns)
            )
            result.append(
                Relation(
                    item.key,
                    item.mapper.class_,
                    "many_to_many"
                    if item.secondary is not None
                    else "one_to_many"
                    if reverse and item.uselist
                    else "one_to_one"
                    if not item.uselist and (reverse or source and self._unique_fk(model, source))
                    else "many_to_one",
                    source_fields=source,
                    target_fields=target,
                    can_detach=(item.secondary is not None or nullable)
                    and "delete-orphan" not in item.cascade,
                    read_only=item.viewonly or item.lazy in {"dynamic", "write_only"},
                    mutates_target=reverse,
                )
            )
        return tuple(result)

    def _unique_fk(self, model: type, names: tuple[str, ...]) -> bool:
        table = inspect(model).local_table
        columns = {inspect(model).column_attrs[name].columns[0].name for name in names}
        return _unique(table, columns)

    async def related(
        self, model: type, name: str, key: Mapping[str, Any], query: Query
    ) -> RecordPage:
        prop = inspect(model).relationships[name]
        target = prop.mapper.class_
        self.describe(model).validate_key(key)
        query.validate(self.describe(target))

        def operation(session):
            parent = session.get(model, dict(key))
            if parent is None:
                raise NotFound("Record not found.")
            statement = select(target).where(with_parent(parent, getattr(model, name)))
            statement = statement.where(*predicates(query, lambda field: getattr(target, field)))
            if query.search and query.search_fields:
                statement = statement.where(
                    or_(
                        *(
                            getattr(target, field)
                            .cast(String)
                            .icontains(query.search, autoescape=True)
                            for field in query.search_fields
                        )
                    )
                )
            total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
            statement = statement.order_by(
                *order_expressions(
                    query, self.describe(target), lambda field: getattr(target, field)
                )
            )
            rows = session.scalars(statement.offset(query.offset).limit(query.limit)).unique().all()
            return RecordPage([query.project(self._record(target, row)) for row in rows], total)

        return await self._run(operation)

    async def save_relations(
        self,
        model: type,
        values: Mapping[str, Any],
        selections: Mapping[str, list[Mapping[str, Any]]],
        *,
        key: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.describe(model).validate_values(values, creating=key is None)
        if key is not None:
            self.describe(model).validate_key(key)
        available_targets = {item.name: item.target for item in self.relations(model)}
        for relation_name, selected_keys in selections.items():
            if relation_name in available_targets:
                target_schema = self.describe(available_targets[relation_name])
                for selected_key in selected_keys:
                    target_schema.validate_key(selected_key)
        available = {item.name: item for item in self.relations(model)}
        if set(selections) - available.keys():
            raise Conflict("Unknown relationship.")

        def operation(session):
            with session.begin():
                parent = (
                    session.get(model, dict(key), with_for_update=True)
                    if key is not None
                    else model()
                )
                if parent is None:
                    raise NotFound("Record not found.")
                session.add(parent)
                with session.no_autoflush:
                    for name, value in values.items():
                        setattr(parent, name, value)
                    for name, keys in selections.items():
                        relation = available[name]
                        if relation.read_only:
                            raise Conflict("This relationship is read only.")
                        prop = inspect(model).relationships[name]
                        if not prop.uselist and len(keys) > 1:
                            raise Conflict("Choose a single related record.")
                        targets = [
                            session.get(relation.target, dict(target_key), with_for_update=True)
                            for target_key in keys
                        ]
                        if any(target is None for target in targets):
                            raise NotFound("Related record not found.")
                        current = getattr(parent, name)
                        previous = (
                            list(current)
                            if prop.uselist
                            else [current]
                            if current is not None
                            else []
                        )
                        if not relation.can_detach and any(
                            item not in targets for item in previous
                        ):
                            raise Conflict("This relationship cannot be detached.")
                        if (
                            not prop.uselist
                            and not targets
                            and not relation.can_detach
                            and not relation.mutates_target
                        ):
                            raise Conflict("A related record is required.")
                        if (
                            relation.mutates_target
                            and not prop.uselist
                            and current is not None
                            and current not in targets
                        ):
                            # Release a unique child FK before assigning the replacement.
                            # Both flushes remain inside the same transaction.
                            setattr(parent, name, None)
                            session.flush()
                        setattr(
                            parent,
                            name,
                            targets if prop.uselist else targets[0] if targets else None,
                        )
                session.flush()
                session.refresh(parent)
                return self._record(model, parent)

        return await self._run(operation)
