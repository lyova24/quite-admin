from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import String, and_, delete, false, func, insert, or_, select, update

from quite_admin.errors import Conflict, NotFound
from quite_admin.schema import Query, RecordPage

from ._queries import ordering as order_expressions
from ._queries import predicates
from ._sql_metadata import SQLRelationMetadata


class SQLRelations(SQLRelationMetadata):
    def relations(self, model):
        return tuple(link.relation for link in self._links(model).values())

    def _linked_statement(self, link, parent):
        target = link.relation.target
        if (
            not link.reverse
            and link.through is None
            and any(parent[name] is None for name in link.local)
        ):
            return select(target).where(false())
        if link.through is not None:
            return (
                select(target)
                .join(
                    link.through,
                    and_(
                        *(
                            target.c[remote] == link.through.c[column]
                            for remote, column in zip(link.remote, link.through_remote, strict=True)
                        )
                    ),
                )
                .where(
                    and_(
                        *(
                            link.through.c[column] == parent[local]
                            for column, local in zip(link.through_local, link.local, strict=True)
                        )
                    )
                )
            )
        return select(target).where(
            and_(
                *(
                    target.c[remote] == parent[local]
                    for local, remote in zip(link.local, link.remote, strict=True)
                )
            )
        )

    async def related(self, model, name: str, key: Mapping[str, Any], query: Query):
        link = self._links(model)[name]
        target = link.relation.target
        self.describe(model).validate_key(key)
        query.validate(self.describe(target))

        def operation(connection):
            parent = (
                connection.execute(select(model).where(self._where(model, key))).mappings().first()
            )
            if parent is None:
                raise NotFound("Record not found.")
            statement = self._linked_statement(link, parent)
            statement = statement.where(*predicates(query, target.c.__getitem__))
            if query.search and query.search_fields:
                statement = statement.where(
                    or_(
                        *(
                            target.c[n].cast(String).icontains(query.search, autoescape=True)
                            for n in query.search_fields
                        )
                    )
                )
            total = connection.scalar(select(func.count()).select_from(statement.subquery())) or 0
            rows = connection.execute(
                statement.order_by(
                    *order_expressions(query, self.describe(target), target.c.__getitem__)
                )
                .offset(query.offset)
                .limit(query.limit)
            ).mappings()
            return RecordPage([query.project(row) for row in rows], total)

        return await self._run(operation)

    async def save_relations(self, model, values, selections, *, key=None):
        self.describe(model).validate_values(values, creating=key is None)
        if key is not None:
            self.describe(model).validate_key(key)
        available_targets = {item.name: item.target for item in self.relations(model)}
        for relation_name, selected_keys in selections.items():
            if relation_name in available_targets:
                target_schema = self.describe(available_targets[relation_name])
                for selected_key in selected_keys:
                    target_schema.validate_key(selected_key)
        links = self._links(model)
        if set(selections) - links.keys():
            raise Conflict("Unknown relationship.")

        def operation(connection):
            changes = dict(values)
            targets = {}
            for name, keys in selections.items():
                link = links[name]
                if link.relation.read_only:
                    raise Conflict("This relationship is read only.")
                if link.relation.kind in {"one_to_one", "many_to_one"} and len(keys) > 1:
                    raise Conflict("Choose a single related record.")
                target = link.relation.target
                rows = [
                    connection.execute(
                        select(target).where(self._where(target, target_key)).with_for_update()
                    )
                    .mappings()
                    .first()
                    for target_key in keys
                ]
                if any(row is None for row in rows):
                    raise NotFound("Related record not found.")
                targets[name] = rows
                if not link.reverse and link.through is None:
                    if not rows and not link.relation.can_detach:
                        raise Conflict("A related record is required.")
                    changes.update(
                        {
                            local: rows[0][remote] if rows else None
                            for local, remote in zip(link.local, link.remote, strict=True)
                        }
                    )
            if key is None:
                inserted = connection.execute(insert(model).values(**changes))
                parent_key = dict(
                    zip(
                        (c.name for c in model.primary_key.columns),
                        inserted.inserted_primary_key,
                        strict=True,
                    )
                )
            else:
                parent_key = dict(key)
                if (
                    connection.execute(
                        select(model).where(self._where(model, key)).with_for_update()
                    ).first()
                    is None
                ):
                    raise NotFound("Record not found.")
                if changes:
                    connection.execute(
                        update(model).where(self._where(model, key)).values(**changes)
                    )
            parent = dict(
                connection.execute(select(model).where(self._where(model, parent_key)))
                .mappings()
                .one()
            )
            for name, rows in targets.items():
                link = links[name]
                if not link.reverse and link.through is None:
                    continue
                previous = [
                    dict(row)
                    for row in connection.execute(self._linked_statement(link, parent)).mappings()
                ]
                target = link.relation.target
                keys = tuple(c.name for c in target.primary_key.columns)
                selected = {tuple(row[k] for k in keys) for row in rows}
                removed = [row for row in previous if tuple(row[k] for k in keys) not in selected]
                if removed and not link.relation.can_detach:
                    raise Conflict("This relationship cannot be detached.")
                if link.through is not None:
                    condition = and_(
                        *(
                            link.through.c[column] == parent[local]
                            for column, local in zip(link.through_local, link.local, strict=True)
                        )
                    )
                    connection.execute(delete(link.through).where(condition))
                    for row in rows:
                        data = {
                            column: parent[local]
                            for column, local in zip(link.through_local, link.local, strict=True)
                        }
                        data.update(
                            {
                                column: row[remote]
                                for column, remote in zip(
                                    link.through_remote, link.remote, strict=True
                                )
                            }
                        )
                        connection.execute(insert(link.through).values(**data))
                else:
                    for row in removed:
                        connection.execute(
                            update(target)
                            .where(self._where(target, {k: row[k] for k in keys}))
                            .values(**dict.fromkeys(link.remote))
                        )
                    for row in rows:
                        connection.execute(
                            update(target)
                            .where(self._where(target, {k: row[k] for k in keys}))
                            .values(
                                **{
                                    remote: parent[local]
                                    for local, remote in zip(link.local, link.remote, strict=True)
                                }
                            )
                        )
            return parent

        return await self._run(operation, write=True)
