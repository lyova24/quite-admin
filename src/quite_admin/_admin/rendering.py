"""Shared template context, navigation and UI messages."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urlsplit

from starlette.requests import Request
from starlette.responses import Response

from .._display import display_kind, display_value
from .assets import script_integrity, script_names
from .web import STATIC_DIR, TEMPLATE_API_VERSION


def _navigation_context(resources, url, gettext):
    """Describe already-authorized resources without reading their records."""
    groups = {}
    catalog = []
    grouped = any(item.options.group is not None for item in resources)
    for item in resources:
        group = item.options.group or gettext("Other collections")
        if grouped:
            groups.setdefault(group, []).append(item)
        catalog.append(
            {
                "id": item.slug,
                "name": item.schema.name,
                "label": item.label,
                "group": group,
                "url": url(f"/models/{item.slug}/"),
            }
        )
    return {
        "resource_groups": groups,
        "table_catalog": catalog,
        "table_group_count": len({item["group"] for item in catalog}),
    }


class Rendering:
    @staticmethod
    def _with_return(path, return_to):
        return (
            path + ("&" if "?" in path else "?") + urlencode({"return_to": return_to})
            if return_to
            else path
        )

    def _navigation_url(self, request, path, return_to=None):
        return self._with_return(self._url(request, path), return_to)

    async def _return_context(self, request):
        """Accept only an authorized listing inside this admin mount as a return target."""
        values = request.query_params.getlist("return_to")
        if len(values) != 1 or not values[0] or len(values[0]) > 65536:
            return None
        target = values[0]
        if not target.startswith("/") or target.startswith("//") or target != target.strip():
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in target):
            return None
        try:
            parsed = urlsplit(target)
        except ValueError:
            return None
        if parsed.scheme or parsed.netloc or parsed.fragment:
            return None
        for resource in (await self.resources()).values():
            if parsed.path == self._url(request, f"/models/{resource.slug}/"):
                if await self._allowed(request, resource, "list"):
                    return target, resource.label
                break
        return None

    async def _render(
        self,
        request: Request,
        template: str,
        *,
        status: int = 200,
        trusted_scripts: tuple[str, ...] = (),
        **context: Any,
    ) -> Response:
        identity = getattr(request.state, "identity", None)
        resources = []
        pages = []
        if identity is not None:
            resources = [
                resource
                for resource in (await self.resources()).values()
                if await self._allowed(request, resource, "list")
            ]
            pages = [
                page for page in self.pages.values() if await self._page_allowed(request, page)
            ]
        resource = context.get("resource")
        display_fields = (
            {
                item.name: display_kind(resource.options.fields[item.name])
                for item in resource.options.visible_fields(resource.schema)
                if item.name in resource.options.fields
                and display_kind(resource.options.fields[item.name]) != "text"
            }
            if resource is not None
            else {}
        )
        if display_fields and template in {"quite_admin/list.html", "quite_admin/form.html"}:
            trusted_scripts += ("values.js",)
        if identity is not None:
            trusted_scripts += ("table-navigation.js", "navigation.js")
            if "dashboard.js" in trusted_scripts:
                trusted_scripts = tuple(
                    name for name in trusted_scripts if name != "dashboard.js"
                ) + ("dashboard.js",)
        scripts = [
            {
                "url": self._url(request, "/assets/" + name),
                "integrity": script_integrity(STATIC_DIR / name),
            }
            for name in script_names(trusted_scripts)
        ]
        request.state.quite_admin_script_hashes = tuple(item["integrity"] for item in scripts)
        shared = {
            "template_api_version": TEMPLATE_API_VERSION,
            "scripts": scripts,
            "request": request,
            "admin": self,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "theme": self.theme,
            "logo_url": self._url(request, "/logo") if self.logo is not None else None,
            "t": self.gettext,
            "tn": self.ngettext,
            "identity": identity,
            "resources": resources,
            **_navigation_context(resources, lambda path: self._url(request, path), self.gettext),
            "pages": pages,
            "history_allowed": identity is not None and await self._history_allowed(request),
            "csrf": self._csrf(request),
            "display_fields": display_fields,
            "display_value": display_value,
            "url": lambda path="/": self._url(request, path),
            "navigation_url": lambda path: self._navigation_url(
                request, path, context.get("return_to")
            ),
            "breadcrumbs": self._breadcrumbs(request, template, context),
        }
        return self.templates.TemplateResponse(
            request=request, name=template, context={**context, **shared}, status_code=status
        )

    def _breadcrumbs(self, request, template, context):
        items = [{"label": self.gettext("Home"), "url": self._url(request, "/")}]
        resource = context.get("resource")
        if resource is not None:
            items.append(
                {
                    "label": context.get("back_label", resource.label),
                    "url": context.get("back_url", self._url(request, f"/models/{resource.slug}/")),
                }
            )
            record = context.get("record")
            if record:
                items.append(
                    {
                        "label": resource.record_label(record),
                        "url": self._navigation_url(
                            request,
                            f"/models/{resource.slug}/{resource.schema.record_key(record)}",
                            context.get("return_to"),
                        ),
                    }
                )
            if context.get("creating"):
                items.append({"label": self.gettext("Create record"), "url": None})
            elif template == "quite_admin/delete.html":
                items.append({"label": self.gettext("Delete record"), "url": None})
            elif template == "quite_admin/bulk.html":
                items.append(
                    {
                        "label": self.gettext(
                            "Bulk action results"
                            if context.get("results") is not None
                            else "Confirm bulk action"
                        ),
                        "url": None,
                    }
                )
        elif context.get("schema_page"):
            items.append({"label": self.gettext("Database schema"), "url": None})
        elif context.get("history_page"):
            items.append({"label": self.gettext("Activity history"), "url": None})
        elif context.get("page") is not None:
            items.append({"label": context["page"].title, "url": None})
        elif context.get("status_code"):
            items.append({"label": str(context["status_code"]), "url": None})
        items[-1]["url"] = None
        return items

    def _schema_messages(self, translations=None):
        translations = translations or self._translations
        translated = {
            name: translations.gettext(text)
            for name, text in {
                "expandJunction": "Show junction table",
                "collapseJunction": "Hide junction table",
                "showAll": "Show all",
                "hideAll": "Hide all",
                "tables": "Tables",
                "junctions": "Junction tables",
                "selectTables": "Select tables to display",
                "searchTables": "Search tables",
                "showTable": "Show table",
                "showRelated": "Show only related tables",
                "restoreRelated": "Restore previous tables",
                "showGroup": "Show group",
                "groupSearchHelp": (
                    "Group checkboxes select every table in the group, "
                    "including tables hidden by search."
                ),
                "expandView": "Expand view",
                "exitView": "Exit expanded view",
                "noTables": "No matching tables.",
                "expand": "Show all fields",
                "collapse": "Show key fields",
                "more": "more fields",
                "fields": "fields",
                "o2o": "One to one",
                "o2m": "One to many",
                "m2m": "Many to many",
                "empty": "No visible fields",
                "one": "1",
                "many": "N",
            }.items()
        }
        return {
            **translated,
            "language": translations.language,
            "fieldForms": [translations.ngettext("field", "fields", count) for count in (1, 2, 5)],
        }

    def _form_messages(self):
        return {
            name: self.gettext(name)
            for name in (
                "True",
                "False",
                "None",
                "e.g. 42",
                "e.g. 19.50",
                "Enter valid JSON",
                "Enter a password",
                "Choose date",
                "Choose date and time",
                "Choose time",
                "Choose date range",
                "Choose time range",
                "Date",
                "Time",
                "From",
                "To",
                "Month",
                "Apply",
                "Cancel",
                "Clear",
                "Precision and timezone",
                "More options",
                "Today",
                "Choose a date.",
                "Enter a time.",
                "Invalid date/time value.",
                "The lower bound must not exceed the upper bound.",
                "Previous month",
                "Next month",
                "Close",
                "Year",
                "Format JSON",
                "Valid JSON",
                "Invalid JSON",
                "JSON is too large for highlighting.",
                "UTC offset (optional)",
                "Fractional seconds (optional)",
                "Use Z or ±HH:MM; leave empty for no timezone.",
                "JSON nesting is too deep to format.",
            )
        }

    def _picker_messages(self):
        return {
            name: self.gettext(text)
            for name, text in {
                "choose": "Choose records",
                "chooseOne": "Choose a record",
                "change": "Change selection",
                "clear": "Clear selection",
                "search": "Search related records",
                "remove": "Remove",
                "previous": "Previous",
                "next": "Next",
                "loading": "Loading…",
                "empty": "No matching records.",
                "failed": "Could not load records. Try again.",
                "retry": "Retry",
                "selected": "Selected",
                "results": "Results",
                "limit": "Select up to 1000 records.",
            }.items()
        }
