from __future__ import annotations

from dataclasses import replace

from sqlalchemy import and_, exists, false, select

from quite_admin.concurrency import check_record, check_relation, guarded
from quite_admin.errors import Conflict, NotFound

from ._sql_metadata import SQLRelationMetadata


class GinoRelations:
    def _links(self, model):
        models = {self._table(item): item for item in self.discover()}
        links = SQLRelationMetadata()._links(self._table(model))
        result = {}
        for name, link in links.items():
            target = models.get(link.relation.target)
            if target is None:
                continue
            local = tuple(self._attribute(model, column) for column in link.local)
            remote = tuple(self._attribute(target, column) for column in link.remote)
            relation = replace(
                link.relation,
                target=target,
                source_fields=local if link.relation.source_fields else (),
                target_fields=remote if link.relation.target_fields else (),
            )
            result[name] = replace(link, relation=relation, local=local, remote=remote)
        return result

    def relations(self, model):
        return tuple(link.relation for link in self._links(model).values())

    def _condition(self, link, parent):
        target = link.relation.target
        if not link.reverse and link.through is None:
            if any(parent[name] is None for name in link.local):
                return false()
        if link.through is not None:
            # Correlated EXISTS preserves cardinality, including composite/self junctions.
            return self._composite_through(link, parent, link.through.alias())
        return and_(
            *(
                getattr(target, remote) == parent[local]
                for local, remote in zip(link.local, link.remote, strict=True)
            )
        )

    def _composite_through(self, link, parent, through):
        return exists(
            select([1])
            .select_from(through)
            .where(
                and_(
                    *(
                        through.c[column] == parent[local]
                        for column, local in zip(link.through_local, link.local, strict=True)
                    ),
                    *(
                        through.c[column] == getattr(link.relation.target, remote)
                        for column, remote in zip(link.through_remote, link.remote, strict=True)
                    ),
                )
            )
            .correlate(self._table(link.relation.target))
        )

    async def related(self, model, name, key, query):
        links = self._links(model)
        if name not in links:
            raise Conflict("Unknown relationship.")
        parent = await self.get(model, key)
        if parent is None:
            raise NotFound("Record not found.")
        link = links[name]
        return await self._page(
            link.relation.target, query, condition=self._condition(link, parent)
        )

    async def save_relations(self, model, values, selections, *, key=None):
        schema = self.describe(model)
        schema.validate_values(values, creating=key is None)
        if key is not None:
            schema.validate_key(key)
        links = self._links(model)
        if set(selections) - links.keys():
            raise Conflict("Unknown relationship.")
        for name, keys in selections.items():
            link = links[name]
            if link.relation.read_only:
                raise Conflict("This relationship is read only.")
            if link.relation.kind in {"one_to_one", "many_to_one"} and len(keys) > 1:
                raise Conflict("Choose a single related record.")
            for target_key in keys:
                self.describe(link.relation.target).validate_key(target_key)

        async with self._transaction() as connection:
            if key is not None and guarded():
                original = await connection.first(
                    model.query.where(self._where(model, key)).with_for_update()
                )
                if original is None:
                    raise NotFound("Record not found.")
                check_record(model, self._record(model, original))
                for relation_name in selections:
                    link = links[relation_name]
                    target = link.relation.target
                    previous = await connection.all(
                        target.query.where(
                            self._condition(link, self._record(model, original))
                        ).with_for_update()
                    )
                    check_relation(
                        model,
                        relation_name,
                        self.describe(target),
                        [self._record(target, row) for row in previous],
                    )
            changes = dict(values)
            targets = {}
            for name, keys in selections.items():
                link = links[name]
                target = link.relation.target
                # Deduplicate selections without relying on driver-specific keys.
                unique = {tuple(sorted(target_key.items())): target_key for target_key in keys}
                rows = [
                    await connection.first(
                        target.query.where(self._where(target, target_key)).with_for_update()
                    )
                    for target_key in unique.values()
                ]
                if any(row is None for row in rows):
                    raise NotFound("Related record not found.")
                targets[name] = [self._record(target, row) for row in rows]
                if not link.reverse and link.through is None:
                    if not rows and not link.relation.can_detach:
                        raise Conflict("A related record is required.")
                    changes.update(
                        {
                            local: getattr(rows[0], remote) if rows else None
                            for local, remote in zip(link.local, link.remote, strict=True)
                        }
                    )
            parent = await self._persist(connection, model, changes, key=key)
            for name, rows in targets.items():
                link = links[name]
                if not link.reverse and link.through is None:
                    continue
                target = link.relation.target
                keys = tuple(field.name for field in self.describe(target).primary_keys)
                previous = await connection.all(
                    target.query.where(self._condition(link, parent)).with_for_update()
                )
                selected = {tuple(row[k] for k in keys) for row in rows}
                removed = [
                    row for row in previous if tuple(getattr(row, k) for k in keys) not in selected
                ]
                if removed and not link.relation.can_detach:
                    raise Conflict("This relationship cannot be detached.")
                if link.through is not None:
                    await connection.status(
                        link.through.delete().where(
                            and_(
                                *(
                                    link.through.c[column] == parent[local]
                                    for column, local in zip(
                                        link.through_local, link.local, strict=True
                                    )
                                )
                            )
                        )
                    )
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
                        await connection.status(link.through.insert().values(**data))
                else:
                    # Release a unique 1:1 FK before assigning its replacement.
                    for row in removed:
                        await row.update(**dict.fromkeys(link.remote)).apply(bind=connection)
                    for row in rows:
                        await self._persist(
                            connection,
                            target,
                            {
                                remote: parent[local]
                                for local, remote in zip(link.local, link.remote, strict=True)
                            },
                            key={field: row[field] for field in keys},
                        )
            identity = {field.name: parent[field.name] for field in schema.primary_keys}
            return await self._persist(connection, model, {}, key=identity)
