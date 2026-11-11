"""Presentation-only foreign-key labels using bounded adapter reads."""

from __future__ import annotations

import inspect

from ..config import FieldOptions
from ..schema import Filter, Query


class ForeignKeyViews:
    async def _foreign_key_cells(self, request, resource, columns, records, *, return_to=None):
        fields = [item for item in columns if item.foreign_key]
        if not fields or not records:
            return {}
        resources = tuple((await self.resources()).values())
        describe = getattr(resource.adapter, "schema_relations", None) or getattr(
            resource.adapter, "relations", None
        )
        relations = describe(resource.model) if describe else ()
        if inspect.isawaitable(relations):
            relations = await relations
        relations = tuple(relations)
        cells = {}
        for field in fields:
            candidates = []
            for relation in relations:
                if (
                    relation.kind not in {"many_to_one", "one_to_one"}
                    or (
                        not relation.source_fields
                        or (relation.source_key_fields or relation.source_fields) != (field.name,)
                    )
                    or len(relation.target_key_fields) != 1
                ):
                    continue
                candidates.extend(
                    (target, relation.target_key_fields[0])
                    for target in resources
                    if target.adapter is resource.adapter and target.model is relation.target
                )
            if not candidates:
                table, _, remote = field.foreign_key.rpartition(".")
                candidates = [
                    (target, remote)
                    for target in resources
                    if target.adapter is resource.adapter
                    and target.schema.name == table
                    and tuple(item.name for item in target.schema.primary_keys) == (remote,)
                ]
            # Ambiguous registrations must not guess a collection or cross data sources.
            unique = {(target.slug, remote): (target, remote) for target, remote in candidates}
            if len(unique) != 1:
                continue
            target, remote = next(iter(unique.values()))
            visible = {item.name: item for item in target.options.visible_fields(target.schema)}
            if (
                remote not in visible
                or not await self._allowed(request, target, "list")
                or not (
                    await self._allowed(request, target, "view")
                    or await self._allowed(request, target, "edit")
                )
            ):
                continue
            label = visible.get(
                resource.options.fields.get(field.name, FieldOptions()).relation_label
            )
            values = tuple(
                dict.fromkeys(row[field.name] for row in records if row.get(field.name) is not None)
            )
            if not values:
                continue
            linked = await self._read(
                target.adapter.list,
                target.model,
                Query(
                    limit=len(values),
                    filters=(Filter(remote, "in", values),),
                    columns=target._projection(
                        (remote, *((label.name,) if label else ())), labels=False
                    ),
                ),
            )
            lookup = {str(row[remote]): row for row in linked.records}
            for record in records:
                value = record.get(field.name)
                row = lookup.get(str(value)) if value is not None else None
                if row is None:
                    continue
                text = (
                    label.format(row[label.name])
                    if label and row.get(label.name) is not None
                    else field.format(value)
                )
                cells.setdefault(resource.schema.record_key(record), {})[field.name] = {
                    "text": text,
                    "href": self._navigation_url(
                        request, f"/models/{target.slug}/{target.schema.record_key(row)}", return_to
                    ),
                }
        return cells
