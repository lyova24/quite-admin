"""Bounded exports of visible scalar and related fields."""

from __future__ import annotations

from dataclasses import replace

from anyio import to_thread
from starlette.exceptions import HTTPException

from .. import exports
from ..relations import BatchRelationAdapter


class ExportViews:
    async def _export_columns(self, request, resource):
        columns = [
            {"name": item.name, "label": item.label, "field": item, "editor": None}
            for item in resource.options.visible_fields(resource.schema)
        ]
        if not isinstance(resource.adapter, BatchRelationAdapter):
            return columns
        for editor in await self._available_relations(
            request, resource, creating=False, allow_edit=False
        ):
            for item in editor["target"].options.visible_fields(editor["target"].schema):
                columns.append(
                    {
                        "name": editor["relation"].name + "." + item.name,
                        "label": editor["relation"].label + " / " + item.label,
                        "field": item,
                        "editor": editor,
                    }
                )
        return columns

    async def _export(self, request, resource, query):
        request.state.quite_admin_activity = (resource.slug, "export")
        if not await self._allowed(request, resource, "view"):
            raise HTTPException(403, "Permission denied.")
        format = request.query_params.get("export")
        if format not in exports.FORMATS or len(request.query_params.getlist("export")) != 1:
            raise HTTPException(400, "Invalid export format.")
        available = {item["name"]: item for item in await self._export_columns(request, resource)}
        selected = request.query_params.getlist("columns")
        if not selected or len(selected) > 100 or len(set(selected)) != len(selected):
            raise HTTPException(400, "Select between 1 and 100 unique export columns.")
        if any(name not in available for name in selected):
            raise HTTPException(400, "Invalid export column.")
        columns = [available[name] for name in selected]
        editors = {
            item["editor"]["relation"].name: item["editor"]
            for item in columns
            if item["editor"] is not None
        }
        cap = exports.MAX_JOIN_ROWS if editors else exports.MAX_ROWS
        source_columns = {item["field"].name for item in columns if item["editor"] is None}
        if editors:
            source_columns.update(item.name for item in resource.schema.primary_keys)
        result = await resource.adapter.list(
            resource.model,
            replace(
                query,
                offset=0,
                limit=cap,
                columns=tuple(name for name in resource.schema.by_name if name in source_columns),
            ),
        )
        if result.total > cap:
            raise HTTPException(413, f"Export exceeds {cap} records. Narrow the filters.")
        rows = []
        links = 0
        size = 0
        batches = {}
        if editors:
            keys = [
                {field.name: record[field.name] for field in resource.schema.primary_keys}
                for record in result.records
            ]
            for name in editors:
                batch = await resource.adapter.related_batch(
                    resource.model,
                    name,
                    keys,
                    limit=exports.MAX_LINKS - links + 1,
                    columns=tuple(
                        dict.fromkeys(
                            item["field"].name
                            for item in columns
                            if item["editor"] is not None
                            and item["editor"]["relation"].name == name
                        )
                    ),
                )
                count = sum(len(records) for records in batch.records.values())
                if (
                    batch.truncated
                    or count + links > exports.MAX_LINKS
                    or any(len(records) > 1000 for records in batch.records.values())
                ):
                    raise HTTPException(413, "Too many related records. Narrow the filters.")
                links += count
                batches[name] = batch.records
        for record in result.records:
            related = {
                name: batches[name].get(resource.schema.record_key(record), []) for name in editors
            }
            row = []
            for column in columns:
                field = column["field"]
                editor = column["editor"]
                if editor is None:
                    value = record.get(field.name)
                    cell = None if value is None else field.format(value)
                else:
                    values = related[editor["relation"].name]
                    formatted = [
                        None if item.get(field.name) is None else field.format(item[field.name])
                        for item in values
                    ]
                    if editor["multiple"]:
                        cell = "\n".join(value or "" for value in formatted)
                    else:
                        cell = formatted[0] if formatted else None
                size += len((cell or "").encode("utf-8"))
                if size > exports.MAX_BYTES:
                    raise HTTPException(413, "Export is too large. Narrow the filters.")
                row.append(cell)
            rows.append(row)
        return await to_thread.run_sync(exports.download, resource.slug, format, selected, rows)
