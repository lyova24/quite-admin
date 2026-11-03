"""Activity recording and history views."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from itsdangerous import BadData
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .. import filters as list_filters
from ..activity import (
    FieldChange,
    activity_allowed,
    bounded_details,
    clip_text,
    safe_record_key,
    scalar_changes,
    sensitive_name,
)
from ..concurrency import canonical
from ..errors import NotFound
from ..schema import Query
from ..storage import Activity, ActivityPage, StorageError
from .web import SLUG


class HistoryViews:
    async def _record_activity(self, state, status):
        if not self.history_enabled:
            return
        identity = state.get("identity")
        target = state.get("quite_admin_activity")
        if identity is None or target is None:
            return
        outcome = "success" if state.get("quite_admin_committed") or status < 400 else "failure"
        if not activity_allowed(self.history_level, target[1], outcome):
            return
        if self.history_level == "changes" and not state.get("quite_admin_committed"):
            return
        event = Activity.new(
            subject=identity.subject,
            display_name=identity.display_name,
            collection=target[0],
            action=target[1],
            outcome=outcome,
            status_code=status,
            details=state.get("quite_admin_activity_details"),
        )
        try:
            await self.storage.append_activity(event)
        except Exception as exc:
            # A separate store cannot roll back a committed business transaction.
            # Do not turn success into a retryable write or expose identity/data in logs.
            await self._logging.emit(
                "warning", "quite_admin.activity_failed", error_type=type(exc).__name__
            )

    def _store_supports_history_level(self, method):
        if not getattr(self.storage, "supports_history_levels", False):
            return False
        # Older subclasses/proxies may inherit the new capability flag while
        # retaining the original public method signatures.
        try:
            return "history_level" in inspect.signature(getattr(self.storage, method)).parameters
        except (TypeError, ValueError):
            return False

    async def _history_events(self, **filters):
        if self._store_supports_history_level("activities"):
            return await self.storage.activities(history_level=self.history_level, **filters)
        if self.history_level == "all":
            return await self.storage.activities(**filters)
        # Keep the original AdminStore protocol usable. The light level can use
        # its existing indexed filters; audit fills a page from allowed events.
        if self.history_level == "changes":
            if filters.get("outcome") == "failure":
                return ActivityPage((), False)
            return await self.storage.activities(
                **{**filters, "changes_only": True, "outcome": "success"}
            )
        limit = filters.pop("limit", 50)
        before = filters.pop("before", None)
        events = []
        while len(events) <= limit:
            page = await self.storage.activities(**filters, limit=limit, before=before)
            events.extend(
                item
                for item in page.events
                if activity_allowed(self.history_level, item.action, item.outcome)
            )
            if not page.has_more:
                break
            if not page.events:
                raise StorageError()
            cursor = (page.events[-1].occurred_at, page.events[-1].id)
            if cursor == before:
                raise StorageError()
            before = cursor
        return ActivityPage(tuple(events[:limit]), len(events) > limit)

    async def _history_actors(self, *, collections, search="", limit=50):
        if self._store_supports_history_level("actors"):
            return await self.storage.actors(
                collections=collections,
                search=search,
                limit=limit,
                history_level=self.history_level,
            )
        if self.history_level == "all":
            return await self.storage.actors(collections=collections, search=search, limit=limit)
        # Legacy stores need no new methods. Derive autocomplete from the same
        # allowed stream, excluding actors whose only events are hidden.
        actors = {}
        before = None
        while True:
            page = await self._history_events(collections=collections, before=before)
            for item in page.events:
                if search.casefold() in (item.subject + " " + item.display_name).casefold():
                    actors.setdefault(item.subject, item.display_name)
            if not page.has_more:
                break
            before = (page.events[-1].occurred_at, page.events[-1].id)
        return tuple(sorted(actors.items())[:limit])

    async def _history_resources(self, request):
        if not self.history_enabled:
            raise NotFound("Page not found.")
        await self._identity(request)
        if not await self._history_allowed(request):
            raise HTTPException(403, "You do not have permission to view this page.")
        return {
            slug: resource
            for slug, resource in (await self.resources()).items()
            if await self._allowed(request, resource, "list")
            and await self._allowed(request, resource, "view")
        }

    async def _history_users(self, request):
        resources = await self._history_resources(request)
        search = request.query_params.get("q", "")
        if len(search) > 200:
            raise HTTPException(400, "Search text is too long.")
        try:
            users = await self._history_actors(collections=("", *resources), search=search)
        except StorageError as exc:
            raise HTTPException(503, "The admin storage is unavailable.") from exc
        return JSONResponse(
            [{"subject": subject, "label": label or subject} for subject, label in users]
        )

    async def _history(self, request):
        resources = await self._history_resources(request)
        actions = {
            "changes": "Changes only",
            "list": "Browse records",
            "view": "View",
            "create": "Create",
            "edit": "Update",
            "inline_edit": "Inline update",
            "delete": "Delete",
            "export": "Export",
            "login": "Sign in",
            "logout": "Sign out",
        }
        for resource in resources.values():
            for action in resource.options.actions:
                actions["action:" + action.slug] = (
                    self.gettext("Custom action") + ": " + action.label
                )
        params = request.query_params
        names = (
            "subject",
            "collection",
            "action",
            "outcome",
            "before",
            "view",
            "date_from",
            "date_to",
            "date_mode",
            "date",
        )
        if any(len(params.getlist(name)) > 1 for name in names):
            raise HTTPException(400, "Invalid history filters.")
        subject, collection, action, outcome = (params.get(name, "") for name in names[:4])
        history_view = params.get("view", "journal")
        date_from, date_to = params.get("date_from", ""), params.get("date_to", "")
        day = params.get("date", "")
        date_mode = params.get(
            "date_mode", "day" if day else "range" if date_from or date_to else "all"
        )
        try:
            if date_mode not in {"all", "day", "range"}:
                raise ValueError
            if date_mode == "day":
                if not day:
                    raise ValueError
                date_from = date_to = day
            elif date_mode == "all":
                date_from = date_to = ""
            if any(
                value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
                for value in (date_from, date_to)
            ):
                raise ValueError
            start = date.fromisoformat(date_from) if date_from else None
            end = date.fromisoformat(date_to) if date_to else None
            if start is not None and end is not None and start > end:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(400, "Invalid history date range.") from exc
        if "action" not in params:
            action = "changes"
        if (
            len(subject) > 1000
            or collection not in {"", "__auth__", *resources}
            or (
                action
                and action not in actions
                and not (action.startswith("action:") and SLUG.fullmatch(action[7:]))
            )
            or len(action) > 100
            or outcome not in {"", "success", "failure"}
            or history_view not in {"journal", "table"}
        ):
            raise HTTPException(400, "Invalid history filters.")
        collections = ("", *resources)
        shape = self._fingerprint(
            [
                subject,
                collection,
                action,
                outcome,
                collections,
                date_from,
                date_to,
                self.history_level,
            ]
        )
        before = None
        token = params.get("before", "")
        if token:
            try:
                if len(token) > 4096:
                    raise ValueError
                data = self._history_signer.loads(token, max_age=self._revision_max_age)
                before = data["before"]
                if (
                    data["subject"] != request.state.identity.subject
                    or data["shape"] != shape
                    or not isinstance(before, list)
                    or len(before) != 2
                    or not all(isinstance(value, str) for value in before)
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", before[0])
                    or not re.fullmatch(r"[0-9a-f]{32}", before[1])
                ):
                    raise ValueError
            except (BadData, ValueError, KeyError, TypeError) as exc:
                raise HTTPException(400, "Invalid history cursor.") from exc
        try:
            result = await self._history_events(
                collections=collections,
                subject=subject,
                collection="" if collection == "__auth__" else collection or None,
                action="" if action == "changes" else action,
                changes_only=action == "changes",
                outcome=outcome,
                before=before,
                date_from=start,
                date_to=end,
            )
            users = await self._history_actors(collections=collections)
        except StorageError as exc:
            raise HTTPException(503, "The admin storage is unavailable.") from exc
        next_url = None
        if result.has_more and result.events:
            last = result.events[-1]
            token = self._history_signer.dumps(
                {
                    "subject": request.state.identity.subject,
                    "shape": shape,
                    "before": [last.occurred_at, last.id],
                }
            )
            next_url = (
                self._url(request, "/history")
                + "?"
                + str(params.__class__({**dict(params), "before": token}))
            )
        today = datetime.now(UTC).date()
        period_label = self.gettext("Any date")
        if date_mode == "day":
            period_label = (
                self.gettext("Today")
                if start == today
                else self.gettext("Yesterday")
                if start == today - timedelta(days=1)
                else start.strftime("%d.%m.%Y")
            )
        elif start is not None and end is not None:
            period_label = start.strftime("%d.%m.%Y") + " → " + end.strftime("%d.%m.%Y")
        elif start is not None:
            period_label = self.gettext("From {date}", date=start.strftime("%d.%m.%Y"))
        elif end is not None:
            period_label = self.gettext("To {date}", date=end.strftime("%d.%m.%Y"))
        filter_choices = {
            "subject": users,
            "collection": (
                []
                if self.history_level == "changes"
                else [("__auth__", self.gettext("Authentication"))]
            )
            + [(slug, resource.label) for slug, resource in resources.items()],
            "action": [
                (name, self.gettext(label))
                for name, label in actions.items()
                if name == "changes" or activity_allowed(self.history_level, name, "success")
            ],
            "outcome": [("success", self.gettext("Success"))]
            + ([] if self.history_level == "changes" else [("failure", self.gettext("Failure"))]),
        }
        filter_values = dict(subject=subject, collection=collection, action=action, outcome=outcome)
        filter_labels = dict(
            subject="User", collection="Collection", action="Action", outcome="Result"
        )

        def filter_url(remove):
            values = {key: value for key, value in params.items() if key not in {*remove, "before"}}
            if "action" in remove:
                values["action"] = ""
            return self._url(request, "/history") + "?" + str(params.__class__(values))

        active_filters = [
            {
                "id": name,
                "parameters": [name],
                "operator": "eq",
                "values": [value],
                "label": self.gettext(filter_labels[name])
                + ": "
                + (dict(filter_choices[name]).get(value) or value),
                "remove_url": filter_url((name,)),
            }
            for name, value in filter_values.items()
            if value
        ]
        return await self._render(
            request,
            "quite_admin/history.html",
            history_page=True,
            history_level=self.history_level,
            events=result.events,
            activity_groups=await self._history_groups(request, result.events, resources),
            history_resources=resources,
            history_users=users,
            history_filters={
                "subject": subject,
                "collection": collection,
                "action": action,
                "outcome": outcome,
                "date_from": date_from,
                "date_to": date_to,
                "date_mode": date_mode,
                "date": day if date_mode == "day" else "",
            },
            history_actions={
                name: label
                for name, label in actions.items()
                if name == "changes" or activity_allowed(self.history_level, name, "success")
            },
            history_filter_descriptors=[
                {
                    "id": name,
                    "label": self.gettext(label),
                    "kind": "relation",
                    "operators": ["eq"],
                    "choices": filter_choices[name],
                    "endpoint": self._url(request, "/history/users") if name == "subject" else "",
                    "key_search": name == "subject",
                }
                for name, label in filter_labels.items()
            ],
            active_filters=active_filters,
            filter_messages={
                **list_filters.messages(self.gettext),
                "type_relation": self.gettext("Choice"),
                "search": self.gettext("Search values"),
                "search_id": self.gettext("Search by name or identifier."),
                "search_text": self.gettext("Search values"),
            },
            history_today=today.isoformat(),
            history_period_label=period_label,
            history_period_messages={
                name: self.gettext(name)
                for name in (
                    "Previous month",
                    "Next month",
                    "Month",
                    "Year",
                    "Choose date",
                    "Date (UTC)",
                    "Date from (UTC)",
                    "Date to (UTC)",
                    "Invalid history date range.",
                )
            },
            history_view=history_view,
            history_view_urls={
                view: self._url(request, "/history")
                + "?"
                + str(params.__class__({**dict(params), "view": view}))
                for view in ("journal", "table")
            },
            history_clear_url=filter_url(filter_labels),
            all_activity_url=self._url(request, "/history")
            + "?"
            + str(
                params.__class__(
                    {
                        key: value
                        for key, value in {**dict(params), "action": ""}.items()
                        if key != "before"
                    }
                )
            ),
            next_url=next_url,
            latest_url=self._url(request, "/history")
            + "?"
            + str(
                params.__class__({key: value for key, value in params.items() if key != "before"})
            ),
            trusted_scripts=("history.js", "filters.js"),
        )

    async def _history_groups(self, request, events, resources):
        """Reapply current field/relation visibility to stored historical snapshots."""
        groups = {}
        relation_cache = {}
        field_cache = {}

        def visible_fields(resource):
            if resource is None:
                return {}
            if resource.slug not in field_cache:
                field_cache[resource.slug] = {
                    field.name: field
                    for field in resource.options.visible_fields(resource.schema)
                    if not sensitive_name(field.name)
                }
            return field_cache[resource.slug]

        today = datetime.now(UTC).date()
        first_changes = True
        for event in events:
            resource = resources.get(event.collection)
            fields = visible_fields(resource)
            details = event.details
            changes = []
            if details is not None and resource is not None:
                for change in details.changes:
                    if change.kind == "relation":
                        if resource.slug not in relation_cache:
                            relation_cache[resource.slug] = {
                                item["relation"].name: item
                                for item in await self._available_relations(
                                    request,
                                    resource,
                                    creating=False,
                                    allow_edit=False,
                                )
                            }
                        editor = relation_cache[resource.slug].get(change.name)
                        if (
                            editor is None
                            or editor["target"].slug != change.target_collection
                            or not all(
                                field.name in visible_fields(editor["target"])
                                for field in editor["target"].schema.primary_keys
                            )
                        ):
                            continue
                        changes.append(replace(change, label=editor["relation"].label))
                    elif change.name in fields:
                        changes.append(replace(change, label=fields[change.name].label))
            record_label, record_url = "", None
            if (
                details
                and details.record_key
                and resource
                and all(field.name in fields for field in resource.schema.primary_keys)
            ):
                try:
                    key = resource.schema.parse_key(details.record_key)
                    record_label = " · ".join(
                        field.format(key[field.name]) for field in resource.schema.primary_keys
                    )
                    if details.record_exists:
                        record_url = self._url(
                            request, f"/models/{resource.slug}/{details.record_key}"
                        )
                except NotFound:
                    pass
            day = event.occurred_at[:10]
            if day not in groups:
                date = datetime.strptime(day, "%Y-%m-%d").date()
                groups[day] = {
                    "date": day,
                    "label": self.gettext("Today")
                    if date == today
                    else self.gettext("Yesterday")
                    if date == today - timedelta(days=1)
                    else date.strftime("%d.%m.%Y"),
                    "events": [],
                }
            groups[day]["events"].append(
                {
                    "event": event,
                    "changes": changes,
                    "record_label": record_label,
                    "record_url": record_url,
                    "open": bool(changes) and first_changes,
                    "write": event.action in {"create", "edit", "inline_edit", "delete"}
                    or event.action.startswith("action:"),
                    "omitted": details.omitted if details else 0,
                }
            )
            if changes:
                first_changes = False
        return tuple(groups.values())

    async def _capture_activity_details(
        self,
        request,
        resource,
        action,
        before,
        saved,
        key,
        relations,
        editors,
    ):
        after = saved
        if action == "delete":
            after = None
        elif action.startswith("action:"):
            after = await self._read(resource.adapter.get, resource.model, key)
        elif not isinstance(after, Mapping):
            after = (
                await self._read(resource.adapter.get, resource.model, key)
                if key is not None
                else None
            )
        changes = scalar_changes(resource.schema, resource.options, before, after)
        for editor in editors:
            relation, target = editor["relation"], editor["target"]
            if relation.name not in relations or not editor["editable"] or after is None:
                continue
            visible = {field.name for field in target.options.visible_fields(target.schema)}
            if any(
                field.name not in visible or sensitive_name(field.name)
                for field in target.schema.primary_keys
            ) or any(sensitive_name(name) for name in relation.source_fields):
                continue
            linked = await self._read(
                resource.adapter.related,
                resource.model,
                relation.name,
                resource.schema.parse_key(resource.schema.record_key(dict(after))),
                Query(
                    limit=1001, columns=tuple(field.name for field in target.schema.primary_keys)
                ),
            )
            old_keys = [target.schema.parse_key(token) for token in editor["selected"]]
            new_keys = [
                {field.name: item[field.name] for field in target.schema.primary_keys}
                for item in linked.records[:1000]
            ]
            if canonical(sorted(old_keys, key=canonical)) == canonical(
                sorted(new_keys, key=canonical)
            ):
                continue

            def labels(keys, target=target):
                return "\n".join(
                    sorted(
                        " · ".join(
                            field.format(item[field.name]) for field in target.schema.primary_keys
                        )
                        for item in keys
                    )
                )

            old_text, old_truncated = clip_text(labels(old_keys))
            new_text, new_truncated = clip_text(labels(new_keys))
            changes.append(
                FieldChange(
                    name=relation.name,
                    label=relation.label,
                    before=old_text,
                    after=new_text,
                    kind="relation",
                    before_truncated=old_truncated,
                    after_truncated=linked.total > 1000 or new_truncated,
                    target_collection=target.slug,
                )
            )
        request.state.quite_admin_activity_details = bounded_details(
            changes,
            record_key=safe_record_key(resource.schema, resource.options, after or before),
            record_exists=after is not None,
        )
