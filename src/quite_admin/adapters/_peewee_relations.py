from __future__ import annotations

import peewee as pw

from quite_admin.concurrency import check_record, check_relation, guarded
from quite_admin.errors import Conflict, NotFound
from quite_admin.relations import Junction, Relation
from quite_admin.schema import RecordPage

from ._queries import ordering as order_expressions
from ._queries import predicates, search_predicate


class PeeweeRelations:
    async def related_batch(self, model, name, keys, *, limit=10001, columns=None):
        from ._batch import batch_fields, finish_batch, prepare_batch

        schema, target_schema, relation = prepare_batch(self, model, name, keys, limit, columns)
        if not keys:
            return finish_batch(schema, target_schema, keys, [], limit, columns)
        source, target = model.alias("qa_source"), relation.target.alias("qa_target")
        source_columns = [getattr(source, field.name) for field in schema.primary_keys]
        expressions = [column.alias(f"qa_parent_{i}") for i, column in enumerate(source_columns)]
        expressions.extend(
            getattr(target, field.name).alias(f"qa_target_{i}")
            for i, field in enumerate(batch_fields(target_schema, columns))
        )
        statement = source.select(*expressions)
        direction, field = self._relation_fields(model)[name]
        if direction == "many":
            source_fk = field.through_model._meta.model_refs[model][0]
            target_fk = field.through_model._meta.model_refs[relation.target][0]
            through = field.through_model.alias("qa_through")
            statement = statement.join(
                through,
                on=getattr(source, source_fk.rel_field.name) == getattr(through, source_fk.name),
            ).join(
                target,
                on=getattr(through, target_fk.name) == getattr(target, target_fk.rel_field.name),
            )
        elif direction == "reverse":
            statement = statement.join(
                target, on=getattr(source, field.rel_field.name) == getattr(target, field.name)
            )
        else:
            statement = statement.join(
                target, on=getattr(source, field.name) == getattr(target, field.rel_field.name)
            )
        values = [tuple(key[field.name] for field in schema.primary_keys) for key in keys]
        condition = (
            source_columns[0].in_([value[0] for value in values])
            if len(source_columns) == 1
            else pw.Tuple(*source_columns).in_(values)
        )
        statement = (
            statement.where(condition)
            .order_by(
                *source_columns,
                *(getattr(target, field.name) for field in target_schema.primary_keys),
            )
            .limit(limit)
        )

        def operation():
            return finish_batch(
                schema, target_schema, keys, list(statement.dicts()), limit, columns
            )

        return await self._run(model, operation)

    def _relation_fields(self, model):
        result = {field.name: ("forward", field) for field in model._meta.refs}
        result.update(
            {
                field.backref: ("reverse", field)
                for field in model._meta.backrefs
                if field.backref != "!"
            }
        )
        result.update({name: ("many", field) for name, field in model._meta.manytomany.items()})
        return result

    def relations(self, model):
        result = []
        for name, (direction, field) in self._relation_fields(model).items():
            if direction == "many":
                source_fk = field.through_model._meta.model_refs[model][0]
                target_fk = field.through_model._meta.model_refs[field.rel_model][0]
                result.append(
                    Relation(
                        name,
                        field.rel_model,
                        "many_to_many",
                        source_key_fields=(source_fk.rel_field.name,),
                        target_key_fields=(target_fk.rel_field.name,),
                        through=field.through_model._meta.table_name,
                        junction=Junction(
                            field.through_model._meta.table_name,
                            self.describe(field.through_model).fields,
                            (source_fk.name,),
                            (target_fk.name,),
                            field.through_model,
                        ),
                    )
                )
                continue
            reverse = direction == "reverse"
            target = field.model if reverse else field.rel_model
            result.append(
                Relation(
                    name,
                    target,
                    "one_to_one" if field.unique else "one_to_many" if reverse else "many_to_one",
                    source_fields=() if reverse else (field.name,),
                    source_key_fields=(field.rel_field.name,) if reverse else (field.name,),
                    target_key_fields=(field.name,) if reverse else (field.rel_field.name,),
                    target_fields=(field.name,) if reverse else (),
                    can_detach=field.null,
                    mutates_target=reverse,
                    read_only=field.primary_key,
                )
            )
        return tuple(result)

    def _filter_conditions(self, model, query):
        fields = self._relation_fields(model) if query.related else {}
        for item in query.related:
            direction, field = fields[item.relation]
            target_model = field.model if direction == "reverse" else field.rel_model
            target = target_model.alias()
            statement = target.select(pw.SQL("1"))
            conditions = [getattr(target, name) == value for name, value in item.key.items()]
            if direction == "many":
                source_fk = field.through_model._meta.model_refs[model][0]
                target_fk = field.through_model._meta.model_refs[target_model][0]
                through = field.through_model.alias()
                statement = statement.join(
                    through,
                    on=(
                        getattr(through, target_fk.name)
                        == getattr(target, target_fk.rel_field.name)
                    ),
                )
                conditions.append(
                    getattr(through, source_fk.name) == getattr(model, source_fk.rel_field.name)
                )
            elif direction == "reverse":
                conditions.append(
                    getattr(target, field.name) == getattr(model, field.rel_field.name)
                )
            else:
                conditions.append(
                    getattr(target, field.rel_field.name) == getattr(model, field.name)
                )
            yield pw.fn.EXISTS(statement.where(*conditions))

    def _related_query(self, parent, name):
        direction, field = self._relation_fields(type(parent))[name]
        if direction == "many":
            return getattr(parent, name)
        if direction == "reverse":
            return field.model.select().where(field == parent.__data__[field.rel_field.name])
        value = parent.__data__.get(field.name)
        return field.rel_model.select().where(
            field.rel_field == value if value is not None else False
        )

    async def related(self, model, name, key, query):
        relation = next(item for item in self.relations(model) if item.name == name)
        self.describe(model).validate_key(key)
        query.validate(self.describe(relation.target))

        def operation():
            parent = model.get_or_none(self._where(model, key))
            if parent is None:
                raise NotFound("Record not found.")
            statement = self._related_query(parent, name)
            if query.columns:
                statement = statement.select(
                    *(getattr(relation.target, field) for field in query.columns)
                )
            if query.filters:
                statement = statement.where(
                    *predicates(query, lambda field: getattr(relation.target, field), peewee=True)
                )
            if query.search and query.search_fields:
                statement = statement.where(
                    search_predicate(
                        query, lambda field: getattr(relation.target, field), peewee=True
                    )
                )
            total = statement.count()
            statement = statement.order_by(
                *order_expressions(
                    query,
                    self.describe(relation.target),
                    lambda field: getattr(relation.target, field),
                )
            )
            return RecordPage(
                [
                    query.project(self._record(relation.target, row))
                    for row in statement.offset(query.offset).limit(query.limit)
                ],
                total,
            )

        return await self._run(model, operation)

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
        fields = self._relation_fields(model)
        if set(selections) - available.keys():
            raise Conflict("Unknown relationship.")

        def operation():
            parent = self._locked_get(model, key) if key is not None else model()
            if parent is None:
                raise NotFound("Record not found.")
            if key is not None and guarded():
                check_record(model, self._record(model, parent))
                for relation_name in selections:
                    target = available[relation_name].target
                    query = self._related_query(parent, relation_name)
                    if guarded() and not isinstance(model._meta.database, pw.SqliteDatabase):
                        query = query.for_update()
                    check_relation(
                        model,
                        relation_name,
                        self.describe(target),
                        [self._record(target, row) for row in query],
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
                    relation.target.get_or_none(self._where(relation.target, target_key))
                    for target_key in keys
                ]
                if any(target is None for target in targets):
                    raise NotFound("Related record not found.")
                selected[name] = targets
                direction, field = fields[name]
                if direction == "forward":
                    if not targets and not relation.can_detach:
                        raise Conflict("A related record is required.")
                    setattr(parent, name, targets[0] if targets else None)
            parent.save(force_insert=key is None)
            for name, targets in selected.items():
                direction, field = fields[name]
                if direction == "forward":
                    continue
                previous = list(self._related_query(parent, name))
                removed = [item for item in previous if item not in targets]
                if removed and not available[name].can_detach:
                    raise Conflict("This relationship cannot be detached.")
                if direction == "many":
                    manager = getattr(parent, name)
                    if removed:
                        manager.remove(removed)
                    added = [item for item in targets if item not in previous]
                    if added:
                        manager.add(added)
                else:
                    for item in removed:
                        setattr(item, field.name, None)
                        item.save(only=[field])
                    for item in targets:
                        setattr(item, field.name, parent)
                        item.save(only=[field])
            return self._record(model, parent)

        return await self._run(model, operation, write=True)
