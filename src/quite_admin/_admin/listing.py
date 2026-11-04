"""Filtered listings and signed pagination cursors."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from itsdangerous import BadData
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from .. import filters as list_filters
from ..errors import NotFound
from ..pagination import WindowAdapter
from ..schema import Query, RecordPage, RelatedFilter


class ListingViews:
    async def _list(self, request: Request) -> Response:
        resource = await self._resource(request, "list")
        cursor_mode = resource.options.pagination == "cursor"
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            limit = min(100, max(1, int(request.query_params.get("limit", "25"))))
            if page > 10**7:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(400, "Invalid pagination.") from exc
        fields = resource.options.visible_fields(resource.schema)
        visible = {item.name: item for item in fields}
        selected = resource.options.list_fields
        columns = (
            tuple(visible[name] for name in selected if name in visible)
            if selected is not None
            else fields[:6]
        )
        order = request.query_params.get("sort")
        if order is not None and order not in visible:
            raise HTTPException(400, "Invalid sort field.")
        if cursor_mode and (page != 1 or order not in {None, resource.schema.primary_keys[0].name}):
            raise HTTPException(
                400, "Cursor pagination requires primary-key ordering and no page number."
            )
        search = request.query_params.get("q", "")[:500]
        search_fields = resource.options.search_fields
        if search_fields is None:
            search_fields = tuple(item.name for item in fields if item.kind == "string")
        search_fields = tuple(name for name in search_fields if name in visible)
        filter_fields = list_filters.controls(resource)
        try:
            filters, filter_errors, active = list_filters.parse(
                resource, filter_fields, request.query_params
            )
        except ValueError as exc:
            raise HTTPException(400, "Invalid filter.") from exc
        relation_filters = await self._list_relation_filters(request, resource)
        related = []
        allowed_relations = {"r." + item["relation"].name: item for item in relation_filters}
        for name, token in request.query_params.items():
            if not name.startswith("r."):
                continue
            if name not in allowed_relations or len(request.query_params.getlist(name)) != 1:
                raise HTTPException(400, "Invalid filter.")
            if not token:
                continue
            editor = allowed_relations[name]
            try:
                selected_record = await self._record(editor["target"], token)
                label = editor["target"].record_label(selected_record)
                editor["selected"] = [token]
                editor["choices"] = [(token, label)]
                related.append(
                    RelatedFilter(editor["relation"].name, editor["target"].schema.parse_key(token))
                )
                active.append(
                    {
                        "parameter": name,
                        "value": token,
                        "label": editor["relation"].label + ": " + label,
                    }
                )
            except NotFound as exc:
                raise HTTPException(400, "Invalid filter.") from exc
        if len(related) > 10:
            filter_errors["__all__"] = "At most 10 relationship filters are supported."
        if not filter_errors and any(
            not value and name.startswith(("f.", "r."))
            for name, value in request.query_params.items()
        ):
            params = request.query_params.__class__(
                [
                    (name, value)
                    for name, value in request.query_params.multi_items()
                    if value or not name.startswith(("f.", "r."))
                ]
            )
            return self._redirect(request, f"/models/{resource.slug}/?{params}")
        query = Query(
            offset=0 if cursor_mode else (page - 1) * limit,
            limit=limit,
            search=search,
            search_fields=search_fields,
            order_by=order,
            descending=request.query_params.get("direction") == "desc",
            filters=filters,
            related=tuple(related),
            columns=resource._projection(item.name for item in columns),
        )
        if "export" in request.query_params:
            if filter_errors:
                raise HTTPException(422, "Correct the filters before exporting.")
            return await self._export(request, resource, query)
        window = None
        if filter_errors:
            result = RecordPage([], 0)
        elif cursor_mode:
            if not isinstance(resource.adapter, WindowAdapter):
                raise HTTPException(400, "This adapter does not support cursor pagination.")
            after, before = self._window_boundaries(request, resource)
            window = await self._read(
                resource.adapter.list_window, resource.model, query, after=after, before=before
            )
            result = window
        else:
            if "after" in request.query_params or "before" in request.query_params:
                raise HTTPException(400, "Cursor parameters require cursor pagination.")
            result = await self._read(resource.adapter.list, resource.model, query)
        permissions = {
            action: await self._allowed(request, resource, action)
            for action in ("view", "create", "edit", "delete")
        }
        base = self._url(request, f"/models/{resource.slug}/")

        def query_url(**updates: Any) -> str:
            if cursor_mode and any(name not in {"after", "before", "page"} for name in updates):
                updates.setdefault("after", None)
                updates.setdefault("before", None)
            params = [
                (key, value)
                for key, value in request.query_params.multi_items()
                if key not in updates and (value or not key.startswith(("f.", "r.")))
            ]
            params.extend((key, value) for key, value in updates.items() if value is not None)
            return base + "?" + str(request.query_params.__class__(params))

        clear = {item["parameter"]: None for item in active}
        clear.update(q=None, page=1)
        filter_descriptors, active = list_filters.presentation(
            filter_fields, relation_filters, active, self.gettext, list_filters.supported(resource)
        )
        for item in active:
            item["remove_url"] = query_url(**{**dict.fromkeys(item["parameters"]), "page": 1})

        export_columns = []
        if permissions["view"]:
            export_columns = await self._export_columns(request, resource)
        inline_fields = self._inline_fields(resource) if permissions["edit"] else {}
        bulk_actions = await self._bulk_choices(request, resource)
        return await self._render(
            request,
            "quite_admin/list.html",
            listing_page=True,
            inline_fields=inline_fields,
            bulk_actions=bulk_actions,
            inline_endpoint=lambda record, name: self._url(
                request,
                f"/models/{resource.slug}/{resource.schema.record_key(record)}/inline/"
                + quote(name, safe=""),
            ),
            form_messages=self._form_messages(),
            export_columns=export_columns,
            export_params=[
                (key, value)
                for key, value in request.query_params.multi_items()
                if key not in {"page", "export", "columns", "after", "before"}
            ],
            status=422 if filter_errors else 200,
            trusted_scripts=("listing.js",)
            + (("forms.js",) if inline_fields or filter_descriptors else ())
            + (("filters.js",) if filter_descriptors else ())
            + (("inline.js",) if inline_fields else ()),
            filter_descriptors=filter_descriptors,
            filter_messages=list_filters.messages(self.gettext),
            filter_errors_json={key: self.gettext(value) for key, value in filter_errors.items()},
            filter_fields=filter_fields,
            filter_parameters=list_filters.parameters(
                filter_fields, list_filters.supported(resource), request.query_params
            ),
            filter_values=dict(request.query_params),
            filter_errors=filter_errors,
            active_filters=active,
            clear_filters_url=query_url(**clear),
            relation_filters=relation_filters,
            picker_messages=self._picker_messages(),
            resource=resource,
            columns=columns,
            result=result,
            cursor_mode=cursor_mode,
            cursor_sortable={resource.schema.primary_keys[0].name},
            cursor_next_url=query_url(
                after=self._window_token(request, resource, window.next_key), before=None, page=None
            )
            if window and window.next_key is not None
            else None,
            cursor_previous_url=query_url(
                before=self._window_token(request, resource, window.previous_key),
                after=None,
                page=None,
            )
            if window and window.previous_key is not None
            else None,
            page_number=page,
            limit=limit,
            query=query,
            query_url=query_url,
            permissions=permissions,
        )

    def _window_shape(self, request):
        return self._fingerprint(
            sorted(
                (name, value)
                for name, value in request.query_params.multi_items()
                if name not in {"after", "before", "page", "export", "columns"}
            )
        )

    def _window_token(self, request, resource, key):
        return self._cursor_signer.dumps(
            {
                "collection": resource.slug,
                "subject": request.state.identity.subject,
                "shape": self._window_shape(request),
                "key": resource.schema.record_key(dict(key)),
            }
        )

    def _window_boundaries(self, request, resource):
        result = []
        for name in ("after", "before"):
            values = request.query_params.getlist(name)
            if len(values) > 1:
                raise HTTPException(400, "Invalid pagination cursor.")
            if not values or not values[0]:
                result.append(None)
                continue
            try:
                if len(values[0]) > 16384:
                    raise ValueError
                data = self._cursor_signer.loads(values[0], max_age=self._revision_max_age)
                if (
                    data["collection"] != resource.slug
                    or data["subject"] != request.state.identity.subject
                    or data["shape"] != self._window_shape(request)
                ):
                    raise ValueError
                result.append(resource.schema.parse_key(data["key"]))
            except (BadData, KeyError, TypeError, ValueError, NotFound) as exc:
                raise HTTPException(400, "Invalid pagination cursor.") from exc
        if all(boundary is not None for boundary in result):
            raise HTTPException(400, "Choose either after or before.")
        return tuple(result)
