"""Record forms, atomic writes and optimistic concurrency."""

from __future__ import annotations

import hashlib
import hmac
import inspect
from copy import deepcopy
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from itsdangerous import BadData
from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..concurrency import CheckedAdapter, StaleRecord, WriteGuard, canonical
from ..config import FieldOptions
from ..errors import Conflict, NotFound, ValidationError
from ..operations import Operation, _operation

if TYPE_CHECKING:
    from ..admin import Resource


class RecordViews:
    def _inline_fields(self, resource):
        visible = resource.options.visible_fields(resource.schema)
        listed = resource.options.list_fields
        listed = set(listed if listed is not None else [item.name for item in visible[:6]])
        configured = resource.options.list_editable
        writable = resource.options.writable_fields(resource.schema, False)
        return {
            name: item
            for name, item in writable.items()
            if name in listed
            and (configured is None or name in configured)
            and item.kind not in {"binary", "unsupported"}
            and not item.foreign_key
            and not resource.options.fields.get(name, FieldOptions()).template
        }

    async def _inline_edit(self, request):
        resource = await self._resource(request, "edit")
        request.state.quite_admin_activity = (
            resource.slug,
            "inline_edit" if request.method == "POST" else "view",
        )
        if not await self._allowed(request, resource, "list"):
            raise HTTPException(403, "Permission denied.")
        name = request.path_params["field"]
        field = self._inline_fields(resource).get(name)
        if field is None:
            raise HTTPException(403, "This field is not writable in the listing.")
        record = await self._record(resource, request.path_params["key"])
        if request.method == "POST":
            form = await self._form(request)
            if set(form) != {"__csrf", "__revision", name}:
                raise HTTPException(422, "Submit exactly one editable field.")
            try:
                changes = resource.options.parse_values(resource.schema, {name: form[name]}, False)
                guard = (
                    self._write_guard(request, resource, form["__revision"], {})
                    if isinstance(resource.adapter, CheckedAdapter)
                    else None
                )
                key = resource.schema.parse_key(request.path_params["key"])

                async def execute():
                    if guard is not None:
                        return await resource.adapter.save_checked(
                            resource.model, key, changes, {}, guard=guard
                        )
                    return await resource.adapter.update(resource.model, key, changes)

                record = await self._perform_write(
                    request, resource, "edit", record, changes, {}, key, execute
                )
                await self._logging.emit(
                    "info", "quite_admin.record_updated", collection=resource.slug, status_code=200
                )
            except ValidationError as exc:
                return JSONResponse(
                    {"errors": {k: self.gettext(v) for k, v in exc.errors.items()}}, status_code=422
                )
            except Conflict as exc:
                return JSONResponse(
                    {"errors": {"__all__": self.gettext(str(exc))}}, status_code=409
                )
        visible = resource.options.visible_fields(resource.schema)
        listed = resource.options.list_fields or tuple(item.name for item in visible[:6])
        return JSONResponse(
            {
                "name": name,
                "label": field.label,
                "kind": field.kind,
                "multiline": field.multiline,
                "nullable": field.nullable,
                "choices": field.choices,
                "max_length": field.max_length,
                "value": field.format(record.get(name)),
                "raw_boolean": record.get(name) if field.kind == "boolean" else None,
                "csrf": self._csrf(request),
                "revision": self._revision_token(request, resource, record, []),
                "label_record": resource.record_label(record),
                "cells": {
                    item.name: {
                        "text": self.gettext("True" if record[item.name] else "False")
                        if item.kind == "boolean" and record.get(item.name) is not None
                        else item.format(record.get(item.name))
                        if record.get(item.name) is not None
                        else "—",
                        "null": record.get(item.name) is None,
                        "kind": item.kind,
                        "boolean": record.get(item.name) is True,
                    }
                    for item in visible
                    if item.name in listed
                },
            }
        )

    async def _record(self, resource: Resource, token: str) -> dict[str, Any]:
        record = await resource.adapter.get(resource.model, resource.schema.parse_key(token))
        if record is None:
            raise NotFound("Record not found.")
        return record

    async def _record_page(self, request: Request) -> Response:
        resource = await self._resource(
            request,
            "edit" if request.method == "POST" else "view",
            alternatives=() if request.method == "POST" else ("edit",),
        )
        return await self._edit_form(
            request,
            resource,
            creating=False,
            editable=await self._allowed(request, resource, "edit"),
        )

    async def _create(self, request: Request) -> Response:
        resource = await self._resource(request, "create")
        return await self._edit_form(request, resource, creating=True)

    async def _edit(self, request: Request) -> Response:
        resource = await self._resource(request, "edit")
        if request.method == "POST":
            return await self._edit_form(request, resource, creating=False)
        return self._redirect(request, f"/models/{resource.slug}/{request.path_params['key']}")

    def _fingerprint(self, value):
        return hmac.new(
            self._revision_secret, canonical(value).encode(), hashlib.sha256
        ).hexdigest()

    def _revision_fields(self, resource):
        return tuple(f.name for f in resource.schema.fields if f.kind != "unsupported")

    def _revision_token(self, request, resource, record, editors):
        if not record or not isinstance(resource.adapter, CheckedAdapter):
            return ""
        return self._revision_signer.dumps(
            {
                "resource": resource.slug,
                "subject": request.state.identity.subject,
                "key": resource.schema.record_key(record),
                "record": self._fingerprint(
                    {name: record.get(name) for name in self._revision_fields(resource)}
                ),
                "relations": {
                    editor["relation"].name: self._fingerprint(sorted(editor["selected"]))
                    for editor in editors
                    if editor["editable"]
                },
            }
        )

    def _write_guard(self, request, resource, token, selections):
        try:
            if not token or len(token) > 65536:
                raise StaleRecord()
            data = self._revision_signer.loads(token, max_age=self._revision_max_age)
            if (
                data["resource"] != resource.slug
                or data["subject"] != request.state.identity.subject
                or data["key"] != request.path_params["key"]
                or set(selections) - data["relations"].keys()
            ):
                raise StaleRecord()
            return WriteGuard(
                data["record"],
                {name: data["relations"][name] for name in selections},
                self._revision_fields(resource),
                self._fingerprint,
            )
        except (BadData, KeyError, TypeError, AttributeError) as exc:
            raise StaleRecord() from exc

    async def _edit_form(
        self, request: Request, resource: Resource, *, creating: bool, editable: bool = True
    ) -> Response:
        record = {} if creating else await self._record(resource, request.path_params["key"])
        editors = await self._relation_editors(
            request, resource, record, creating=creating, allow_edit=editable
        )
        history_editors = (
            tuple({**editor, "selected": tuple(editor["selected"])} for editor in editors)
            if self.history_enabled
            else ()
        )
        managed = frozenset(name for editor in editors for name in editor["relation"].source_fields)
        ordered = resource.options.form_fields(resource.schema, creating)
        if not creating:
            selected = {item.name for item in ordered}
            ordered += tuple(
                item
                for item in resource.options.visible_fields(resource.schema)
                if item.name not in selected
            )
        fields = tuple(item for item in ordered if item.name not in managed)
        values = {item.name: item.format(record.get(item.name)) for item in fields}
        errors = {}
        defaults = {item.name for item in fields if creating and item.has_default}
        status = 200
        revision_token = self._revision_token(request, resource, record, editors)
        stale = False
        if request.method == "POST":
            if not editable:
                raise HTTPException(403, "You do not have permission to perform this action.")
            multi = frozenset(
                "__relation__" + editor["relation"].name
                for editor in editors
                if editor["editable"] and editor["multiple"]
            )
            form = await self._form(request, multi_fields=multi)
            if not creating:
                revision_token = str(form.get("__revision", ""))
            form = FormData(
                (name, value) for name, value in form.multi_items() if name != "__revision"
            )
            values.update({name: str(value) for name, value in form.items() if name in values})
            defaults = {
                name.removeprefix("__default__")
                for name in form
                if name.startswith("__default__") and form[name] == "true"
            }
            try:
                selections, scalar = self._relation_selections(editors, form)
                changes = resource.options.parse_values(
                    resource.schema, scalar, creating, managed_fields=managed
                )
                key = None if creating else resource.schema.parse_key(request.path_params["key"])

                guard = (
                    self._write_guard(request, resource, revision_token, selections)
                    if not creating and isinstance(resource.adapter, CheckedAdapter)
                    else None
                )

                async def execute():
                    if guard is not None:
                        return await resource.adapter.save_checked(
                            resource.model, key, changes, selections, guard=guard
                        )
                    if selections:
                        return await resource.adapter.save_relations(
                            resource.model, changes, selections, key=key
                        )
                    if creating:
                        return await resource.adapter.create(resource.model, changes)
                    return await resource.adapter.update(resource.model, key, changes)

                saved = await self._perform_write(
                    request,
                    resource,
                    "create" if creating else "edit",
                    record,
                    changes,
                    selections,
                    key,
                    execute,
                    relation_editors=history_editors,
                )
                await self._logging.emit(
                    "info",
                    "quite_admin.record_created" if creating else "quite_admin.record_updated",
                    collection=resource.slug,
                    status_code=303,
                )
                if await self._allowed(request, resource, "view") or await self._allowed(
                    request, resource, "edit"
                ):
                    return self._redirect(
                        request, f"/models/{resource.slug}/" + resource.schema.record_key(saved)
                    )
                return self._redirect(request, f"/models/{resource.slug}/")
            except ValidationError as exc:
                await self._logging.emit(
                    "debug",
                    "quite_admin.validation_failed",
                    collection=resource.slug,
                    status_code=422,
                )
                errors, status = exc.errors, 422
            except Conflict as exc:
                await self._logging.emit(
                    "warning",
                    "quite_admin.record_conflict",
                    collection=resource.slug,
                    status_code=409,
                )
                errors, status = {"__all__": str(exc)}, 409
                stale = isinstance(exc, StaleRecord)
        if request.method == "POST":
            await self._restore_relation_labels(editors)
        writable = resource.options.writable_fields(resource.schema, creating) if editable else {}
        return await self._render(
            request,
            "quite_admin/form.html",
            trusted_scripts=(
                (("relations.js",) if any(item["editable"] for item in editors) else ())
                + (
                    ("forms.js",)
                    if editable
                    and any(
                        item.name in writable
                        and item.kind in {"json", "date", "datetime", "time", "boolean"}
                        for item in fields
                    )
                    else ()
                )
            ),
            form_messages=self._form_messages(),
            status=status,
            resource=resource,
            fields=fields,
            values=values,
            errors=errors,
            defaults=defaults,
            creating=creating,
            writable=writable,
            relation_editors=editors,
            picker_messages=self._picker_messages(),
            revision_token=revision_token,
            stale=stale,
            editable=editable,
            record=record,
            can_delete=not creating and await self._allowed(request, resource, "delete"),
            form_action=self._url(
                request,
                f"/models/{resource.slug}/new"
                if creating
                else f"/models/{resource.slug}/{resource.schema.record_key(record)}",
            ),
            record_actions=[]
            if creating
            else [
                action
                for action in resource.options.actions
                if await self._action_allowed(request, resource, action)
            ],
        )

    async def _perform_write(
        self,
        request,
        resource,
        action,
        record,
        values,
        relations,
        key,
        execute,
        *,
        relation_editors=(),
    ):
        def snapshot(value):
            return MappingProxyType(deepcopy(dict(value)))

        operation = Operation(
            request=request,
            identity=request.state.identity,
            collection=resource.slug,
            model=resource.model,
            action=action,
            key=snapshot(key) if key is not None else None,
            values=snapshot(values),
            record=snapshot(record),
            relations=MappingProxyType(
                {name: tuple(snapshot(item) for item in keys) for name, keys in relations.items()}
            ),
        )
        token = _operation.set(operation)
        try:
            if self.hooks.before_write is not None:
                result = self.hooks.before_write(operation)
                if inspect.isawaitable(result):
                    await result
            saved = execute()
            if inspect.isawaitable(saved):
                saved = await saved
            request.state.quite_admin_committed = True
            if self.history_enabled:
                try:
                    await self._capture_activity_details(
                        request,
                        resource,
                        action,
                        operation.record,
                        saved,
                        key,
                        relations,
                        relation_editors,
                    )
                except Exception as exc:
                    await self._logging.emit(
                        "warning",
                        "quite_admin.activity_details_failed",
                        error_type=type(exc).__name__,
                    )
            if self.hooks.after_write is not None:
                try:
                    result = self.hooks.after_write(
                        operation, snapshot(saved) if saved is not None else None
                    )
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    await self._logging.emit(
                        "warning",
                        "quite_admin.after_write_failed",
                        collection=resource.slug,
                        operation=action,
                        error_type=type(exc).__name__,
                    )
            return saved
        finally:
            _operation.reset(token)

    async def _action_allowed(self, request, resource, action):
        if not await self._allowed(request, resource, action.required_permission):
            return False
        return await self._permission_allowed(
            request, action.permission, action.required_permission
        )

    async def _record_action(self, request):
        await self._identity(request)
        resource = (await self.resources()).get(request.path_params["slug"])
        if resource is None:
            raise NotFound("Table not found.")
        action = next(
            (
                action
                for action in resource.options.actions
                if action.slug == request.path_params["action"]
            ),
            None,
        )
        if action is None:
            raise NotFound("Action not found.")
        request.state.quite_admin_activity = (resource.slug, "action:" + action.slug)
        if not await self._action_allowed(request, resource, action):
            raise HTTPException(403, "You do not have permission to perform this action.")
        await self._form(request)
        key = resource.schema.parse_key(request.path_params["key"])
        record = await self._record(resource, request.path_params["key"])
        await self._perform_write(
            request,
            resource,
            "action:" + action.slug,
            record,
            {},
            {},
            key,
            lambda: action.handler(_operation.get()),
        )
        await self._logging.emit(
            "info",
            "quite_admin.record_action",
            collection=resource.slug,
            operation=action.slug,
            status_code=303,
        )
        return self._redirect(request, f"/models/{resource.slug}/{request.path_params['key']}")

    async def _delete(self, request: Request) -> Response:
        resource = await self._resource(request, "delete")
        token = request.path_params["key"]
        record = await self._record(resource, token)
        if request.method == "POST":
            await self._form(request)
            key = resource.schema.parse_key(token)
            await self._perform_write(
                request,
                resource,
                "delete",
                record,
                {},
                {},
                key,
                lambda: resource.adapter.delete(resource.model, key),
            )
            await self._logging.emit(
                "info", "quite_admin.record_deleted", collection=resource.slug, status_code=303
            )
            return self._redirect(request, f"/models/{resource.slug}/")
        return await self._render(
            request, "quite_admin/delete.html", resource=resource, record=record
        )
