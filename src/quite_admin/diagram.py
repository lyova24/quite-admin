"""A metadata-only graph of already authorized, registered admin resources."""

from __future__ import annotations

import inspect

from .config import is_sensitive_field
from .relations import RelationAdapter


async def schema_graph(resources, *, all_resources=None):
    resources = tuple(sorted(resources, key=lambda item: item.slug))
    all_resources = tuple(all_resources) if all_resources is not None else resources
    nodes, edges, seen, junctions = {}, [], set(), {}
    adapters = {id(resource.adapter): str(index) for index, resource in enumerate(resources)}
    visible = {}
    for resource in resources:
        fields = resource.options.visible_fields(resource.schema)
        visible[resource.slug] = {field.name for field in fields}
        nodes[resource.slug] = graph_node(
            resource.slug, resource.schema.name, resource.label, fields
        )
    for resource in resources:
        describe = getattr(resource.adapter, "schema_relations", None)
        if describe is None and isinstance(resource.adapter, RelationAdapter):
            describe = resource.adapter.relations
        if describe is None:
            continue
        relations = describe(resource.model)
        if inspect.isawaitable(relations):
            relations = await relations
        for relation in relations:
            target = next(
                (
                    item
                    for item in resources
                    if item.adapter is resource.adapter and item.model is relation.target
                ),
                None,
            )
            if target is None:
                continue
            local = (
                relation.source_key_fields
                or relation.source_fields
                or tuple(field.name for field in resource.schema.primary_keys)
            )
            remote = (
                relation.target_key_fields
                or relation.target_fields
                or tuple(field.name for field in target.schema.primary_keys)
            )
            if set(local) - visible[resource.slug] or set(remote) - visible[target.slug]:
                continue
            source, destination = (
                (resource.slug, tuple(sorted(local))),
                (target.slug, tuple(sorted(remote))),
            )
            kind = relation.kind
            flipped = False
            if kind == "many_to_one":
                source, destination = destination, source
                kind = "one_to_many"
            elif kind in {"one_to_one", "many_to_many"} and source > destination:
                source, destination = destination, source
                flipped = True
            signature = kind, source, destination, relation.through
            if signature in seen:
                continue
            seen.add(signature)
            edges.append(
                {
                    "id": "e" + str(len(edges)),
                    "source": source[0],
                    "target": destination[0],
                    "sourceFields": source[1],
                    "targetFields": destination[1],
                    "kind": {"one_to_one": "o2o", "one_to_many": "o2m", "many_to_many": "m2m"}[
                        kind
                    ],
                    "label": relation.label,
                }
            )
            junction = relation.junction
            if kind == "many_to_many" and junction is not None:
                exact = [
                    item
                    for item in all_resources
                    if item.adapter is resource.adapter and item.model is junction.model
                ]
                registered = exact or [
                    item
                    for item in all_resources
                    if item.adapter is resource.adapter
                    and item.schema.name == junction.name.split(".")[-1]
                ]
                allowed = (
                    registered[0] if len(registered) == 1 and registered[0].slug in nodes else None
                )
                # A restricted registered junction must not reappear as synthetic metadata.
                if not registered or allowed is not None:
                    junction_id = (
                        allowed.slug
                        if allowed
                        else "junction:" + adapters[id(resource.adapter)] + ":" + junction.name
                    )
                    fields = (
                        allowed.options.visible_fields(allowed.schema)
                        if allowed
                        else tuple(
                            field for field in junction.fields if not is_sensitive_field(field.name)
                        )
                    )
                    names = {field.name for field in fields}
                    if not (set(junction.source_fields) | set(junction.target_fields)) - names:
                        node = nodes.get(junction_id) or graph_node(
                            junction_id,
                            junction.name,
                            allowed.label if allowed else junction.name,
                            fields,
                            junction=True,
                        )
                        for field in node["fields"]:
                            if field["name"] in junction.source_fields + junction.target_fields:
                                field["linked"] = True
                                field["fk"] = True
                        if junction_id not in nodes:
                            junctions[junction_id] = node
                        edges[-1].update(
                            {
                                "junction": junction_id,
                                "junctionSourceFields": junction.target_fields
                                if flipped
                                else junction.source_fields,
                                "junctionTargetFields": junction.source_fields
                                if flipped
                                else junction.target_fields,
                            }
                        )
            for slug, names in (source, destination):
                for field in nodes[slug]["fields"]:
                    if field["name"] in names:
                        field["linked"] = True
    return {"nodes": list(nodes.values()), "edges": edges, "junctions": list(junctions.values())}


def graph_node(identifier, name, label, fields, *, junction=False):
    return {
        "id": identifier,
        "name": name,
        "label": label,
        "junction": junction,
        "fields": [
            {
                "name": field.name,
                "type": field.kind,
                "pk": field.primary_key,
                "fk": bool(field.foreign_key),
                "linked": bool(field.foreign_key),
                "nullable": field.nullable,
            }
            for field in sorted(fields, key=lambda field: not field.primary_key)
        ],
    }
