"""Permission-aware relationship editors and pickers."""

from __future__ import annotations

import inspect
import json

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from ..errors import NotFound, ValidationError
from ..relations import RelationAdapter
from ..schema import Query


class RelationViews:
    async def _list_relation_filters(self, request, resource):
        if not getattr(resource.adapter, "supports_related_filters", False):
            return []
        editors = await self._available_relations(
            request, resource, creating=False, allow_edit=False
        )
        for editor in editors:
            editor.update(
                {
                    "selected": [],
                    "choices": [],
                    "multiple": False,
                    "endpoint": self._url(
                        request,
                        f"/models/{resource.slug}/relationships/{editor['relation'].name}/options",
                    )
                    + "?purpose=filter",
                }
            )
        return editors

    async def _available_relations(self, request, resource, *, creating, allow_edit=True):
        if not isinstance(resource.adapter, RelationAdapter):
            return []
        relations = resource.adapter.relations(resource.model)
        if inspect.isawaitable(relations):
            relations = await relations
        relations = tuple(relations)
        names = {relation.name for relation in relations}
        configured = set(resource.options.relations or ()) | set(
            resource.options.readonly_relations
        )
        if configured - names:
            raise ValueError(
                "Unknown relationship configuration: " + ", ".join(sorted(configured - names))
            )
        targets = {
            (id(item.adapter), id(item.model)): item for item in (await self.resources()).values()
        }
        writable = resource.options.writable_fields(resource.schema, creating)
        source_visible = {item.name for item in resource.options.visible_fields(resource.schema)}
        editors = []
        for relation in relations:
            if (
                resource.options.relations is not None
                and relation.name not in resource.options.relations
            ):
                continue
            if set(relation.source_fields) - source_visible:
                continue
            target = targets.get((id(resource.adapter), id(relation.target)))
            if (
                target is None
                or not await self._allowed(request, target, "list")
                or not await self._allowed(request, target, "view")
            ):
                continue
            if set(relation.target_fields) - {
                item.name for item in target.options.visible_fields(target.schema)
            }:
                continue
            editable = allow_edit and (
                not relation.read_only and relation.name not in resource.options.readonly_relations
            )
            editable = editable and all(name in writable for name in relation.source_fields)
            if relation.mutates_target:
                editable = editable and await self._allowed(request, target, "edit")
                target_writable = target.options.writable_fields(target.schema, False)
                editable = editable and all(
                    name in target_writable for name in relation.target_fields
                )
            editors.append(
                {
                    "relation": relation,
                    "target": target,
                    "editable": editable,
                    "multiple": relation.kind in {"one_to_many", "many_to_many"},
                }
            )
        return editors

    async def _relation_editors(self, request, resource, record, *, creating, allow_edit=True):
        editors = await self._available_relations(
            request, resource, creating=creating, allow_edit=allow_edit
        )
        for editor in editors:
            relation, target, editable = editor["relation"], editor["target"], editor["editable"]
            linked = (
                None
                if creating
                else await resource.adapter.related(
                    resource.model,
                    relation.name,
                    resource.schema.parse_key(resource.schema.record_key(record)),
                    Query(limit=1001, columns=target._projection()),
                )
            )
            selected = [] if linked is None else linked.records[:1000]
            truncated = linked is not None and linked.total > 1000
            editable = editable and not truncated
            candidates = (
                await target.adapter.list(
                    target.model, Query(limit=25, columns=target._projection())
                )
                if editable
                else None
            )
            records = {target.schema.record_key(item): item for item in selected}
            if candidates is not None:
                records.update(
                    {target.schema.record_key(item): item for item in candidates.records}
                )
            editor.update(
                {
                    "editable": editable,
                    "selected": [target.schema.record_key(item) for item in selected],
                    "choices": [(key, target.record_label(item)) for key, item in records.items()],
                    "truncated": truncated,
                    "endpoint": self._url(
                        request, f"/models/{resource.slug}/relationships/{relation.name}/options"
                    )
                    + "?"
                    + str(
                        request.query_params.__class__(
                            {"record": resource.schema.record_key(record)} if not creating else {}
                        )
                    ),
                }
            )
        return editors

    async def _relation_options(self, request):
        filtering = request.query_params.get("purpose") == "filter"
        creating = not request.query_params.get("record")
        resource = await self._resource(
            request, "list" if filtering else "create" if creating else "edit"
        )
        if filtering:
            available = await self._list_relation_filters(request, resource)
        else:
            if not creating:
                await self._record(resource, request.query_params["record"])
            available = await self._available_relations(request, resource, creating=creating)
        editor = next(
            (
                item
                for item in available
                if item["relation"].name == request.path_params["relation"]
                and (filtering or item["editable"])
            ),
            None,
        )
        if editor is None:
            raise HTTPException(403, "This relationship is not writable.")
        try:
            page = int(request.query_params.get("page", "1"))
            if not 1 <= page <= 10**7:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(400, "Invalid pagination.") from exc
        search = request.query_params.get("q", "")
        if len(search) > 500:
            raise HTTPException(400, "Search is too long.")
        target = editor["target"]
        visible = {item.name: item for item in target.options.visible_fields(target.schema)}
        searchable = target.options.search_fields
        if searchable is None:
            searchable = tuple(name for name, item in visible.items() if item.kind == "string")
        key_search = None
        if (
            search
            and getattr(target.adapter, "supports_key_search", False)
            and all(item.name in visible for item in target.schema.primary_keys)
        ):
            try:
                keys = target.schema.primary_keys
                raw = {keys[0].name: search} if len(keys) == 1 else json.loads(search)
                if not isinstance(raw, dict) or set(raw) != {item.name for item in keys}:
                    raise ValueError
                key_search = {item.name: item.parse(raw[item.name]) for item in keys}
                target.schema.validate_key(key_search)
            except (ValueError, TypeError):
                key_search = None
        query = Query(
            offset=(page - 1) * 25,
            limit=25,
            search=search,
            search_key=key_search,
            search_fields=tuple(name for name in searchable if name in visible),
            columns=target._projection(name for name in searchable if name in visible),
        )
        result = await target.adapter.list(target.model, query)
        return JSONResponse(
            {
                "items": [
                    {
                        "key": target.schema.record_key(row),
                        "label": target.record_label(row),
                        "identity": " · ".join(
                            item.format(row[item.name])
                            for item in target.schema.primary_keys
                            if item.name in visible
                        ),
                        "description": " · ".join(
                            visible[name].format(row.get(name))[:120]
                            for name in searchable
                            if name in visible and row.get(name) is not None
                        )[:300],
                    }
                    for row in result.records
                ],
                "page": page,
                "total": result.total,
                "has_next": page * 25 < result.total,
            }
        )

    async def _restore_relation_labels(self, editors):
        for editor in editors:
            known = dict(editor["choices"])
            for token in editor["selected"][:1000]:
                if token in known:
                    continue
                try:
                    record = await self._record(editor["target"], token)
                    known[token] = editor["target"].record_label(record)
                except NotFound:
                    known[token] = self.gettext("Unavailable record")
            editor["choices"] = list(known.items())

    def _relation_selections(self, editors, form):
        writable = {editor["relation"].name: editor for editor in editors if editor["editable"]}
        selections = {}
        errors = {}
        scalar = {}
        for name, value in form.items():
            if not name.startswith(("__relation__", "__relation_present__")):
                scalar[name] = value
                continue
            relation_name = name.removeprefix("__relation_present__").removeprefix("__relation__")
            if relation_name not in writable:
                errors[name] = "This relationship is not writable."
                continue
            if form.get("__relation_present__" + relation_name) != "true":
                errors[name] = "Invalid relationship selection."
                continue
            editor = writable[relation_name]
            tokens = [token for token in form.getlist("__relation__" + relation_name) if token]
            editor["selected"] = tokens
            if (
                len(tokens) > 1000
                or len(tokens) != len(set(tokens))
                or not editor["multiple"]
                and len(tokens) > 1
            ):
                errors["__relation__" + relation_name] = "Invalid relationship selection."
                continue
            try:
                selections[relation_name] = [
                    editor["target"].schema.parse_key(token) for token in tokens
                ]
            except NotFound:
                errors["__relation__" + relation_name] = "Related record not found."
        if errors:
            raise ValidationError(errors)
        return selections, scalar
