from __future__ import annotations

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from quite_admin.concurrency import check_record, check_relation, guarded
from quite_admin.errors import Conflict, NotFound
from quite_admin.relations import Junction, Relation
from quite_admin.schema import Field, RecordPage

from ._queries import tortoise_filters


class TortoiseRelations:
    def relations(self, model):
        meta = model._meta
        result = []
        for name in sorted(
            meta.fk_fields
            | meta.o2o_fields
            | meta.backward_fk_fields
            | meta.backward_o2o_fields
            | meta.m2m_fields
        ):
            field = meta.fields_map[name]
            reverse = name in meta.backward_fk_fields | meta.backward_o2o_fields
            many = name in meta.m2m_fields
            local = () if reverse or many else (field.source_field,)
            result.append(
                Relation(
                    name,
                    field.related_model,
                    "many_to_many"
                    if many
                    else "one_to_one"
                    if name in meta.o2o_fields | meta.backward_o2o_fields
                    else "one_to_many"
                    if reverse
                    else "many_to_one",
                    source_fields=local,
                    source_key_fields=(meta.pk_attr,)
                    if many
                    else (field.to_field_instance.model_field_name,)
                    if reverse
                    else local,
                    target_key_fields=(field.related_model._meta.pk_attr,)
                    if many
                    else (field.relation_field,)
                    if reverse
                    else (field.to_field,),
                    through=field.through if many else None,
                    junction=Junction(
                        field.through,
                        (
                            Field(
                                field.backward_key,
                                self.describe(model).primary_keys[0].python_type,
                                foreign_key=meta.db_table + "." + meta.pk_attr,
                            ),
                            Field(
                                field.forward_key,
                                self.describe(field.related_model).primary_keys[0].python_type,
                                foreign_key=field.related_model._meta.db_table
                                + "."
                                + field.related_model._meta.pk_attr,
                            ),
                        ),
                        (field.backward_key,),
                        (field.forward_key,),
                    )
                    if many
                    else None,
                    target_fields=(field.relation_field,) if reverse else (),
                    can_detach=many or field.null,
                    read_only=bool(local and local[0] == meta.pk_attr),
                    mutates_target=reverse,
                )
            )
        return tuple(result)

    def _related_query(self, parent, name):
        meta = type(parent)._meta
        field = meta.fields_map[name]
        if name in meta.m2m_fields:
            return getattr(parent, name).all()
        if name in meta.backward_fk_fields | meta.backward_o2o_fields:
            source = field.to_field_instance.model_field_name
            return field.related_model.filter(**{field.relation_field: getattr(parent, source)})
        value = getattr(parent, field.source_field)
        if value is None:
            return field.related_model.filter(pk__in=[])
        return field.related_model.filter(**{field.to_field: value})

    async def related(self, model, name, key, query):
        from tortoise.expressions import Q

        relation = next(item for item in self.relations(model) if item.name == name)
        self.describe(model).validate_key(key)
        query.validate(self.describe(relation.target))
        parent = await model.get_or_none(**key)
        if parent is None:
            raise NotFound("Record not found.")
        statement = tortoise_filters(self._related_query(parent, name), query)
        if query.search and query.search_fields:
            statement = statement.filter(
                Q(
                    *(Q(**{f"{field}__icontains": query.search}) for field in query.search_fields),
                    join_type="OR",
                )
            )
        total = await statement.count()
        pk = relation.target._meta.pk_attr
        order = query.order_by or pk
        ordering = [("-" if query.descending else "") + order]
        if order != pk:
            ordering.append(pk)
        rows = await statement.order_by(*ordering).offset(query.offset).limit(query.limit)
        return RecordPage(
            [query.project(self._record(relation.target, item)) for item in rows], total
        )

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
        available = {item.name: item for item in self.relations(model)}
        if set(selections) - available.keys():
            raise Conflict("Unknown relationship.")
        try:
            async with in_transaction(model._meta.default_connection) as connection:
                parent = (
                    await model.filter(**key).using_db(connection).select_for_update().first()
                    if key is not None
                    else model()
                )
                if parent is None:
                    raise NotFound("Record not found.")
                if key is not None and guarded():
                    check_record(model, self._record(model, parent))
                    for relation_name in selections:
                        target = available[relation_name].target
                        previous = (
                            await self._related_query(parent, relation_name)
                            .using_db(connection)
                            .select_for_update()
                        )
                        check_relation(
                            model,
                            relation_name,
                            self.describe(target),
                            [self._record(target, row) for row in previous],
                        )
                for name, value in values.items():
                    setattr(parent, name, value)
                selected = {}
                for name, keys in selections.items():
                    relation = available[name]
                    if relation.read_only:
                        raise Conflict("This relationship is read only.")
                    if relation.kind in {"one_to_one", "many_to_one"} and len(keys) > 1:
                        raise Conflict("Choose a single related record.")
                    targets = [
                        await relation.target.filter(**target_key)
                        .using_db(connection)
                        .select_for_update()
                        .first()
                        for target_key in keys
                    ]
                    if any(item is None for item in targets):
                        raise NotFound("Related record not found.")
                    selected[name] = targets
                    if relation.source_fields:
                        if not targets and not relation.can_detach:
                            raise Conflict("A related record is required.")
                        field = model._meta.fields_map[name]
                        setattr(
                            parent,
                            field.source_field,
                            getattr(targets[0], field.to_field) if targets else None,
                        )
                await parent.save(using_db=connection)
                for name, targets in selected.items():
                    relation = available[name]
                    if relation.source_fields:
                        continue
                    previous = await self._related_query(parent, name).using_db(connection)
                    removed = [item for item in previous if item not in targets]
                    if removed and not relation.can_detach:
                        raise Conflict("This relationship cannot be detached.")
                    if relation.kind == "many_to_many":
                        manager = getattr(parent, name)
                        if removed:
                            await manager.remove(*removed, using_db=connection)
                        added = [item for item in targets if item not in previous]
                        if added:
                            await manager.add(*added, using_db=connection)
                    else:
                        field = model._meta.fields_map[name]
                        source = field.to_field_instance.model_field_name
                        for item in removed:
                            setattr(item, field.relation_field, None)
                            await item.save(
                                using_db=connection, update_fields=[field.relation_field]
                            )
                        for item in targets:
                            setattr(item, field.relation_field, getattr(parent, source))
                            await item.save(
                                using_db=connection, update_fields=[field.relation_field]
                            )
                await parent.refresh_from_db(using_db=connection)
                return self._record(model, parent)
        except IntegrityError as exc:
            raise Conflict("The operation conflicts with a database constraint.") from exc
