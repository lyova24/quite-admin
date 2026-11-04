"""Explicit, bounded record selections using existing write hooks and action handlers."""

import hmac

from itsdangerous import BadData
from starlette.exceptions import HTTPException

from ..errors import AdminError, Conflict, NotFound
from ..operations import current_operation


class BulkViews:
    def _bulk_back_url(self, request, resource):
        base = self._url(request, f"/models/{resource.slug}/")
        return base + ("?" + str(request.query_params) if request.query_params else "")

    async def _bulk_choices(self, request, resource):
        choices = []
        if resource.options.bulk_delete and await self._allowed(request, resource, "delete"):
            choices.append({"slug": "delete", "label": self.gettext("Delete selected records")})
        for action in resource.options.actions:
            if action.bulk and await self._action_allowed(request, resource, action):
                choices.append({"slug": "action:" + action.slug, "label": action.label})
        return choices

    async def _bulk_permission(self, request, resource, name):
        if not await self._allowed(request, resource, "list"):
            raise HTTPException(403, "You do not have permission to perform this action.")
        if name == "delete":
            allowed = resource.options.bulk_delete and await self._allowed(
                request, resource, "delete"
            )
        else:
            action = next(
                (
                    item
                    for item in resource.options.actions
                    if "action:" + item.slug == name and item.bulk
                ),
                None,
            )
            if action is None:
                raise NotFound("Action not found.")
            allowed = await self._action_allowed(request, resource, action)
        if not allowed:
            raise HTTPException(403, "You do not have permission to perform this action.")

    def _bulk_revision(self, resource, record):
        return self._fingerprint(
            {name: record.get(name) for name in self._revision_fields(resource)}
        )

    async def _bulk(self, request):
        await self._identity(request)
        resource = (await self.resources()).get(request.path_params["slug"])
        if resource is None:
            raise NotFound("Table not found.")
        form = await self._form(request, multi_fields=frozenset({"keys"}))
        if "__confirmation" in form:
            if set(form) != {"__csrf", "__confirmation"}:
                raise HTTPException(422, "Invalid bulk selection.")
            data = self._bulk_confirmation(request, resource, form["__confirmation"])
            return await self._bulk_execute(request, resource, data)
        if set(form) != {"__csrf", "keys", "action"}:
            raise HTTPException(422, "Select between 1 and 100 records.")
        keys = form.getlist("keys")
        if not 1 <= len(keys) <= 100 or len(set(keys)) != len(keys):
            raise HTTPException(422, "Select between 1 and 100 distinct records.")
        name = form["action"]
        await self._bulk_permission(request, resource, name)
        label = next(
            item["label"]
            for item in await self._bulk_choices(request, resource)
            if item["slug"] == name
        )
        selected = []
        previews = []
        try:
            for token in keys:
                request.path_params["key"] = token
                await self._bulk_permission(request, resource, name)
                record = await self._record(resource, token)
                selected.append((token, self._bulk_revision(resource, record)))
                previews.append(resource.record_label(record))
        finally:
            request.path_params.pop("key", None)
        confirmation = self._bulk_signer.dumps(
            {
                "collection": resource.slug,
                "subject": request.state.identity.subject,
                "session": self._fingerprint(self._csrf(request)),
                "action": name,
                "records": selected,
            }
        )
        return await self._render(
            request,
            "quite_admin/bulk.html",
            resource=resource,
            bulk_label=label,
            back_url=self._bulk_back_url(request, resource),
            selected_labels=previews,
            confirmation=confirmation,
            results=None,
        )

    def _bulk_confirmation(self, request, resource, token):
        try:
            if not isinstance(token, str) or len(token) > 131072:
                raise BadData("Invalid selection")
            data = self._bulk_signer.loads(token, max_age=900)
            if (
                data["collection"] != resource.slug
                or data["subject"] != request.state.identity.subject
                or data["session"] != self._fingerprint(self._csrf(request))
                or not isinstance(data["action"], str)
                or not 1 <= len(data["records"]) <= 100
                or len({item[0] for item in data["records"]}) != len(data["records"])
            ):
                raise BadData("Invalid selection")
            return data
        except (BadData, KeyError, TypeError, ValueError, IndexError) as exc:
            raise HTTPException(
                400, "The bulk confirmation expired or is invalid. Select records again."
            ) from exc

    async def _bulk_execute(self, request, resource, data):
        name = data["action"]
        # Resolve the command again: runtime configuration and permissions may change.
        action = next(
            (item for item in resource.options.actions if "action:" + item.slug == name), None
        )
        results = []
        try:
            for token, revision in data["records"]:
                request.path_params["key"] = token
                request.state.quite_admin_activity = (resource.slug, name)
                request.state.quite_admin_committed = False
                request.state.quite_admin_activity_details = None
                label = self.gettext("Selected record")
                status = 200
                try:
                    await self._bulk_permission(request, resource, name)
                    record = await self._record(resource, token)
                    label = resource.record_label(record)
                    if not hmac.compare_digest(revision, self._bulk_revision(resource, record)):
                        raise Conflict(
                            "The record changed. Select it again before performing this action."
                        )
                    key = resource.schema.parse_key(token)
                    await self._perform_write(
                        request,
                        resource,
                        name,
                        record,
                        {},
                        {},
                        key,
                        lambda key=key: (
                            resource.adapter.delete(resource.model, key)
                            if name == "delete"
                            else action.handler(current_operation())
                        ),
                    )
                    results.append(
                        {"label": label, "success": True, "message": self.gettext("Success")}
                    )
                except (AdminError, HTTPException) as exc:
                    status = exc.status_code
                    message = exc.detail if isinstance(exc, HTTPException) else str(exc)
                    results.append(
                        {"label": label, "success": False, "message": self.gettext(message)}
                    )
                except Exception as exc:
                    status = 500
                    await self._logging.emit(
                        "warning",
                        "quite_admin.bulk_action_failed",
                        collection=resource.slug,
                        operation=name,
                        error_type=type(exc).__name__,
                    )
                    results.append(
                        {
                            "label": label,
                            "success": False,
                            "message": self.gettext("Unable to complete this action."),
                        }
                    )
                await self._record_activity(request.scope["state"], status)
        finally:
            # Each result has its own event. Do not append an aggregate event on response.start.
            request.path_params.pop("key", None)
            request.state.quite_admin_activity = None
            request.state.quite_admin_committed = False
            request.state.quite_admin_activity_details = None
        return await self._render(
            request,
            "quite_admin/bulk.html",
            resource=resource,
            results=results,
            back_url=self._bulk_back_url(request, resource),
            succeeded=sum(item["success"] for item in results),
            failed=sum(not item["success"] for item in results),
        )
