from __future__ import annotations

from functools import reduce
from operator import or_

from quite_admin.errors import Conflict, NotFound
from quite_admin.relations import Relation
from quite_admin.schema import RecordPage


class PeeweeRelations:
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
                result.append(Relation(name, field.rel_model, "many_to_many"))
                continue
            reverse = direction == "reverse"
            target = field.model if reverse else field.rel_model
            result.append(
                Relation(
                    name,
                    target,
                    "one_to_one" if field.unique else "one_to_many" if reverse else "many_to_one",
                    source_fields=() if reverse else (field.name,),
                    target_fields=(field.name,) if reverse else (),
                    can_detach=field.null,
                    mutates_target=reverse,
                    read_only=field.primary_key,
                )
            )
        return tuple(result)

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

        def operation():
            parent = model.get_or_none(self._where(model, key))
            if parent is None:
                raise NotFound("Record not found.")
            statement = self._related_query(parent, name)
            if query.search and query.search_fields:
                statement = statement.where(
                    reduce(
                        or_,
                        (
                            getattr(relation.target, field).contains(query.search)
                            for field in query.search_fields
                        ),
                    )
                )
            total = statement.count()
            statement = statement.order_by(
                *(
                    getattr(relation.target, f.name)
                    for f in self.describe(relation.target).primary_keys
                )
            )
            return RecordPage(
                [
                    self._record(relation.target, row)
                    for row in statement.offset(query.offset).limit(query.limit)
                ],
                total,
            )

        return await self._run(model, operation)

    async def save_relations(self, model, values, selections, *, key=None):
        available = {item.name: item for item in self.relations(model)}
        fields = self._relation_fields(model)
        if set(selections) - available.keys():
            raise Conflict("Unknown relationship.")

        def operation():
            parent = model.get_or_none(self._where(model, key)) if key is not None else model()
            if parent is None:
                raise NotFound("Record not found.")
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

        return await self._run(model, operation)
