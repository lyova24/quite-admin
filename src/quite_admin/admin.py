from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import json
import re
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import quote

from anyio import to_thread
from itsdangerous import BadData, URLSafeTimedSerializer
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader, select_autoescape
from starlette.applications import Starlette
from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp, Receive, Scope, Send

from . import exports
from . import filters as list_filters
from .activity import (
    FieldChange,
    bounded_details,
    clip_text,
    safe_record_key,
    scalar_changes,
    sensitive_name,
)
from .adapters.base import Adapter
from .auth import AuthBackend, Identity, LoginThrottle
from .concurrency import CheckedAdapter, StaleRecord, WriteGuard, canonical
from .config import Action, FieldOptions, ModelOptions, Permission
from .diagram import schema_graph
from .errors import AdminError, Conflict, NotFound, ValidationError
from .i18n import Language, Translator
from .logging import EventLogger, LoggerProtocol
from .operations import Operation, OperationHooks, _operation
from .pagination import WindowAdapter
from .relations import BatchRelationAdapter, RelationAdapter
from .schema import ModelSchema, Query, RecordPage, RelatedFilter
from .storage import TABLE_PREFIX, Activity, AdminStore, StorageError, create_store
from .theme import Theme

SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
TEMPLATE_API_VERSION = 1
FORM_BODY_LIMIT = 1024 * 1024
LOGO_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
PageContext = Callable[[Request], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    template: str
    context: PageContext | None = None
    permission: Permission | None = None


@dataclass(frozen=True)
class Resource:
    slug: str
    model: Any
    adapter: Adapter
    schema: ModelSchema
    options: ModelOptions

    @property
    def label(self) -> str:
        return self.options.label or self.schema.label or self.slug

    def record_label(self, record: Mapping[str, Any]) -> str:
        visible = {item.name: item for item in self.options.visible_fields(self.schema)}
        for name in (
            self.options.record_label,
            "name",
            "title",
            "label",
            "display_name",
            "username",
            *(self.options.search_fields or ()),
            *(
                name
                for name, item in visible.items()
                if item.kind == "string" and not item.primary_key
            ),
        ):
            if name in visible and record.get(name) is not None:
                return visible[name].format(record[name])[:200]
        return (
            " · ".join(
                field.format(record.get(field.name))
                for field in self.schema.primary_keys
                if field.name in visible
            )[:200]
            or self.label
        )

    def _projection(self, names=(), *, labels=True):
        selected = set(names) | {item.name for item in self.schema.primary_keys}
        if labels:
            visible = {item.name: item for item in self.options.visible_fields(self.schema)}
            candidates = (
                self.options.record_label,
                "name",
                "title",
                "label",
                "display_name",
                "username",
                *(self.options.search_fields or ()),
                *(
                    name
                    for name, item in visible.items()
                    if item.kind == "string" and not item.primary_key
                ),
            )
            for name in candidates:
                if name in visible:
                    selected.add(name)
                    if not visible[name].nullable:
                        break
        return tuple(item.name for item in self.schema.fields if item.name in selected)


@dataclass
class Source:
    adapter: Adapter
    discover: bool
    namespace: str | None
    options: dict[Any, ModelOptions] = field(default_factory=dict)


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def secure_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                scripts = scope.get("state", {}).get("quite_admin_script_hashes", ())
                script_policy = " ".join("'" + value + "'" for value in scripts) or "'none'"
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"same-origin"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; style-src 'self'; "
                            + f"script-src {script_policy}; ".encode()
                            + b"img-src 'self' data:; object-src 'none'; "
                            + b"base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                        ),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, secure_send)


class Admin:
    """Standalone ASGI admin. Host applications own engines and their lifespan."""

    def __init__(
        self,
        *,
        auth: AuthBackend,
        secret_key: str,
        adapters: Iterable[Adapter] = (),
        title: str = "Quite Admin",
        description: str = "",
        language: Language = "en",
        theme: Theme | None = None,
        logo: str | Path | None = None,
        templates_dir: str | Path | None = None,
        secure_cookies: bool = True,
        session_cookie: str = "quite_admin_session",
        session_max_age: int = 8 * 60 * 60,
        logger: LoggerProtocol | None = None,
        log_structured: bool = False,
        hooks: OperationHooks | None = None,
        storage: AdminStore | str | Path | None = None,
        history_permission: Permission | None = None,
        history_enabled: bool = True,
    ) -> None:
        if len(secret_key.encode()) < 32:
            raise ValueError("secret_key must contain at least 32 bytes of random secret material.")
        if session_max_age <= 0:
            raise ValueError("session_max_age must be positive.")
        if not isinstance(history_enabled, bool):
            raise ValueError("history_enabled must be a boolean.")
        self._revision_signer = URLSafeTimedSerializer(
            secret_key, salt="quite-admin-record-revision"
        )
        self._revision_secret = secret_key.encode()
        self._cursor_signer = URLSafeTimedSerializer(secret_key, salt="quite-admin-list-cursor")
        self._revision_max_age = session_max_age
        self.auth = auth
        self.title = title
        self.description = description
        self._translations = Translator(language)
        self.language = language
        self.theme = theme if theme is not None else Theme()
        self.logo = Path(logo).expanduser().resolve() if logo is not None else None
        if self.logo is not None and (
            not self.logo.is_file() or self.logo.suffix.lower() not in LOGO_TYPES
        ):
            raise ValueError("logo must be an existing SVG, PNG, JPEG, WebP or GIF file.")
        self._logging = EventLogger(logger, structured=log_structured)
        self.logger = self._logging.logger
        self.hooks = hooks if hooks is not None else OperationHooks()
        self.storage = create_store(storage)
        self.history_permission = history_permission
        self.history_enabled = history_enabled
        self._history_signer = URLSafeTimedSerializer(secret_key, salt="quite-admin-history")
        self.sources: list[Source] = []
        self.collection_options: dict[str, ModelOptions] = {}
        self.pages: dict[str, Page] = {}
        self.throttle = LoginThrottle()
        for adapter in adapters:
            self.add_adapter(adapter)
        loaders = [PackageLoader("quite_admin", "templates")]
        if templates_dir is not None:
            loaders.insert(0, FileSystemLoader(str(templates_dir)))
        environment = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(default=True, default_for_string=True),
            auto_reload=True,
        )
        self.templates = Jinja2Templates(env=environment)
        routes = [
            Mount("/assets", app=StaticFiles(directory=Path(__file__).parent / "static")),
            Route("/theme.css", self._theme_styles),
            Route("/logo", self._logo),
            Route("/login", self._login, methods=["GET", "POST"]),
            Route("/logout", self._logout, methods=["POST"]),
            Route("/", self._dashboard),
            Route("/schema", self._schema),
            Route("/history", self._history),
            Route("/history/users", self._history_users),
            Route("/pages/{slug}", self._page),
            Route("/models/{slug}/", self._list),
            Route("/models/{slug}/new", self._create, methods=["GET", "POST"]),
            Route("/models/{slug}/relationships/{relation}/options", self._relation_options),
            Route(
                "/models/{slug}/{key}/inline/{field:path}",
                self._inline_edit,
                methods=["GET", "POST"],
            ),
            Route("/models/{slug}/{key}/edit", self._edit, methods=["GET", "POST"]),
            Route("/models/{slug}/{key}/delete", self._delete, methods=["GET", "POST"]),
            Route("/models/{slug}/{key}/actions/{action}", self._record_action, methods=["POST"]),
            Route("/models/{slug}/{key}", self._record_page, methods=["GET", "POST"]),
        ]
        self.app = Starlette(
            routes=routes,
            middleware=[
                Middleware(SecurityHeaders),
                Middleware(
                    SessionMiddleware,
                    secret_key=secret_key,
                    session_cookie=session_cookie,
                    max_age=session_max_age,
                    same_site="lax",
                    https_only=secure_cookies,
                ),
            ],
            exception_handlers={AdminError: self._error, HTTPException: self._error},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # SessionMiddleware replaces scope['session']. Keep the host's session intact.
        forwarded = dict(scope)
        forwarded.setdefault("state", {})
        recorded = False

        async def audited_send(message):
            nonlocal recorded
            if message["type"] == "http.response.start" and not recorded:
                recorded = True
                await self._record_activity(forwarded["state"], message["status"])
            await send(message)

        try:
            await self.app(forwarded, receive, audited_send)
        except Exception:
            if not recorded:
                await self._record_activity(forwarded["state"], 500)
            raise

    async def _storage_ready(self):
        try:
            await self.storage.initialize()
        except StorageError as exc:
            raise HTTPException(503, "The admin storage is unavailable.") from exc

    async def _record_activity(self, state, status):
        if not self.history_enabled:
            return
        identity = state.get("identity")
        target = state.get("quite_admin_activity")
        if identity is None or target is None:
            return
        event = Activity.new(
            subject=identity.subject,
            display_name=identity.display_name,
            collection=target[0],
            action=target[1],
            outcome="success" if state.get("quite_admin_committed") or status < 400 else "failure",
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

    def gettext(self, message: str, **values: Any) -> str:
        return self._translations.gettext(message, **values)

    def ngettext(self, singular: str, plural: str, count: int) -> str:
        return self._translations.ngettext(singular, plural, count)

    async def _theme_styles(self, request: Request) -> Response:
        return Response(self.theme.stylesheet(), media_type="text/css")

    async def _logo(self, request: Request) -> Response:
        if self.logo is None:
            raise HTTPException(404, "Logo not found.")
        return FileResponse(self.logo, media_type=LOGO_TYPES[self.logo.suffix.lower()])

    def add_adapter(
        self, adapter: Adapter, *, discover: bool = True, namespace: str | None = None
    ) -> Admin:
        if namespace is not None and not SLUG.fullmatch(namespace):
            raise ValueError("namespace must be a URL-safe slug.")
        if any(source.adapter is adapter for source in self.sources):
            raise ValueError("Adapter already added.")
        self.sources.append(Source(adapter, discover, namespace))
        return self

    def register(
        self, model: Any, *, adapter: Adapter | None = None, options: ModelOptions | None = None
    ) -> Admin:
        if adapter is None:
            if len(self.sources) != 1:
                raise ValueError("Select an adapter explicitly when there are zero or several.")
            source = self.sources[0]
        else:
            source = next((source for source in self.sources if source.adapter is adapter), None)
            if source is None:
                self.add_adapter(adapter, discover=False)
                source = self.sources[-1]
        source.options[model] = options or ModelOptions()
        return self

    def add_page(self, page: Page) -> Admin:
        if not SLUG.fullmatch(page.slug) or page.slug in self.pages:
            raise ValueError("A page needs a unique URL-safe slug.")
        self.pages[page.slug] = page
        return self

    def configure(self, collection: str, *, options: ModelOptions) -> Admin:
        """Configure a discovered table by its original, optionally namespaced slug."""
        self.collection_options[collection] = options
        return self

    async def resources(self) -> dict[str, Resource]:
        """Refresh metadata lazily, including models registered during host startup."""
        result: dict[str, Resource] = {}
        for source in self.sources:
            discovered = source.adapter.discover() if source.discover else ()
            if inspect.isawaitable(discovered):
                discovered = await discovered
            resolver = getattr(source.adapter, "resolve_model", None)
            registered = {
                resolver(model) if resolver is not None else model: options
                for model, options in source.options.items()
            }
            models = dict.fromkeys(discovered)
            models.update(dict.fromkeys(registered))
            for model in models:
                schema = source.adapter.describe(model)
                if schema.name.rsplit(".", 1)[-1].lower().startswith(TABLE_PREFIX):
                    continue
                original_slug = (
                    f"{source.namespace}-{schema.name}" if source.namespace else schema.name
                )
                options = self.collection_options.get(
                    original_slug, registered.get(model, ModelOptions())
                )
                options.validate(schema)
                slug = options.slug or schema.name
                if source.namespace:
                    slug = f"{source.namespace}-{slug}"
                if not SLUG.fullmatch(slug):
                    raise ValueError(f"Set ModelOptions(slug=...) for table {schema.name!r}.")
                if slug in result:
                    raise ValueError(
                        f"Duplicate resource {slug!r}; set namespace or explicit slugs."
                    )
                result[slug] = Resource(slug, model, source.adapter, schema, options)
        return dict(sorted(result.items(), key=lambda pair: pair[1].label.casefold()))

    def mount_fastapi(self, app: Any, path: str = "/admin") -> None:
        app.mount(self._mount_path(path), self, name="quite-admin")

    def litestar_route(self, path: str = "/admin") -> Any:
        from litestar import asgi
        from litestar.exceptions import HTTPException as LitestarHTTPException

        body_limit_detail = self.gettext("The form exceeds 1 MiB.")

        class BodyLimitMiddleware:
            def __init__(self, app: ASGIApp) -> None:
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                size = 0
                exceeded = False

                async def limited_receive() -> dict:
                    nonlocal size, exceeded
                    # Body parsers may retry receive() after swallowing a parse
                    # failure. A limit violation must remain a limit violation.
                    if exceeded:
                        raise LitestarHTTPException(status_code=413, detail=body_limit_detail)
                    message = await receive()
                    if message["type"] == "http.request":
                        size += len(message.get("body", b""))
                        if size > FORM_BODY_LIMIT:
                            exceeded = True
                            raise LitestarHTTPException(status_code=413, detail=body_limit_detail)
                    return message

                await self.app(scope, limited_receive if scope["type"] == "http" else receive, send)

        class AdminASGIHandler(asgi):
            # Litestar 2's body-reading LoggingMiddleware calls this HTTP-handler
            # method even for ASGI mounts. Keep the compatibility bridge local.
            def resolve_request_max_body_size(self) -> int:
                return FORM_BODY_LIMIT

            def resolve_middleware(self) -> list:
                # Litestar wraps this list inside-out. Count bytes before the
                # host's body-reading log middleware, only for this admin mount.
                return [*super().resolve_middleware(), BodyLimitMiddleware]

        mount_path = self._mount_path(path)

        # Litestar strips the mount and normalizes every path with a trailing slash.
        # Rebuild standard ASGI path/root_path before passing scope to Starlette.
        async def mounted(scope: Scope, receive: Receive, send: Send) -> None:
            forwarded = dict(scope)
            root = scope.get("root_path", "").rstrip("/")
            parents = scope["route_handler"].ownership_layers[:-1]
            prefix = "".join(
                "/" + layer.path.strip("/")
                for layer in parents
                if getattr(layer, "path", "").strip("/")
            )
            root += prefix + mount_path
            relative = scope["path"]
            raw = scope.get("raw_path")
            if raw is not None:
                if not raw.endswith(b"/") and relative != "/":
                    relative = relative.rstrip("/")
            elif relative != "/" and not (
                relative.startswith("/models/") and len(relative.strip("/").split("/")) == 2
            ):
                relative = relative.rstrip("/")
            forwarded["root_path"] = root
            forwarded["path"] = root + relative
            forwarded.pop("raw_path", None)
            if scope["type"] != "http":
                await self(forwarded, receive, send)
                return

            # LoggingMiddleware may already have read the body into Litestar's
            # request cache. Its public stream() API reads that cache when present.
            # Replay as ASGI messages without eagerly buffering a fresh request.
            request = scope["litestar_app"].request_class(scope, receive)
            stream = request.stream()
            complete = False

            async def replay_body() -> dict:
                nonlocal complete
                if complete:
                    return await receive()
                try:
                    chunk = await anext(stream)
                except StopAsyncIteration:
                    chunk = b""
                except LitestarHTTPException as exc:
                    # The inner Starlette exception handler must own the response,
                    # including limits raised by Litestar's streaming request API.
                    raise HTTPException(exc.status_code, exc.detail) from exc
                complete = not chunk
                return {"type": "http.request", "body": chunk, "more_body": not complete}

            try:
                await self(forwarded, replay_body, send)
            finally:
                await stream.aclose()

        return AdminASGIHandler(path=mount_path, is_mount=True, copy_scope=True)(mounted)

    def mount_litestar(self, app: Any, path: str = "/admin") -> None:
        app.register(self.litestar_route(path))

    @staticmethod
    def _mount_path(path: str) -> str:
        path = path.rstrip("/")
        if not path.startswith("/") or path.startswith("//") or not path:
            raise ValueError("Use a non-root absolute mount path, such as '/admin'.")
        return path

    @staticmethod
    def _url(request: Request, path: str = "/") -> str:
        return request.scope.get("root_path", "").rstrip("/") + path

    def _redirect(self, request: Request, path: str) -> RedirectResponse:
        return RedirectResponse(self._url(request, path), status_code=303)

    async def _identity(self, request: Request) -> Identity:
        subject = request.session.get("subject")
        identity = (
            await self.auth.get_identity(request, subject) if isinstance(subject, str) else None
        )
        if identity is None:
            request.session.pop("subject", None)
            raise HTTPException(303, headers={"location": self._url(request, "/login")})
        request.state.identity = identity
        if self.history_enabled:
            await self._storage_ready()
        return identity

    async def _allowed(self, request: Request, resource: Resource, action: Action) -> bool:
        options = resource.options
        if (
            (action == "create" and not options.can_create)
            or (action == "edit" and not options.can_edit)
            or (action == "delete" and not options.can_delete)
        ):
            return False
        if options.permission is None:
            return True
        decision = options.permission(request, request.state.identity, action)
        return bool(await decision if inspect.isawaitable(decision) else decision)

    async def _page_allowed(self, request: Request, page: Page) -> bool:
        if page.permission is None:
            return True
        result = page.permission(request, request.state.identity, "view")
        return bool(await result if inspect.isawaitable(result) else result)

    async def _history_allowed(self, request):
        if not self.history_enabled:
            return False
        if self.history_permission is None:
            return True
        result = self.history_permission(request, request.state.identity, "view")
        return bool(await result if inspect.isawaitable(result) else result)

    async def _resource(
        self, request: Request, action: Action, *, alternatives: tuple[Action, ...] = ()
    ) -> Resource:
        await self._identity(request)
        resource = (await self.resources()).get(request.path_params["slug"])
        if resource is None:
            raise NotFound("Table not found.")
        request.state.quite_admin_activity = (
            resource.slug,
            action if request.method == "POST" or action == "list" else "view",
        )
        allowed = False
        for candidate in (action, *alternatives):
            if await self._allowed(request, resource, candidate):
                allowed = True
                break
        if not allowed:
            await self._logging.emit(
                "warning",
                "quite_admin.permission_denied",
                collection=resource.slug,
                operation=action,
                status_code=403,
            )
            raise HTTPException(403, "You do not have permission to perform this action.")
        return resource

    def _csrf(self, request: Request) -> str:
        if "csrf" not in request.session:
            request.session["csrf"] = secrets.token_urlsafe(32)
        return request.session["csrf"]

    async def _form(
        self, request: Request, *, multi_fields: frozenset[str] = frozenset()
    ) -> FormData:
        # Only small URL-encoded forms. Avoid unbounded body buffering and file uploads.
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
        if content_type != "application/x-www-form-urlencoded":
            raise HTTPException(415, "Expected a URL-encoded form.")
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > FORM_BODY_LIMIT:
                raise HTTPException(413, "The form exceeds 1 MiB.")
            chunks.append(chunk)
        request._body = b"".join(chunks)
        form = await request.form()
        if any(len(form.getlist(name)) > 1 and name not in multi_fields for name in form):
            raise HTTPException(422, "Duplicate form fields are not accepted.")
        expected = request.session.get("csrf")
        supplied = form.get("__csrf")
        if (
            not isinstance(expected, str)
            or not isinstance(supplied, str)
            or not secrets.compare_digest(expected.encode(), supplied.encode())
        ):
            await self._logging.emit("warning", "quite_admin.csrf_rejected", status_code=403)
            raise HTTPException(403, "Invalid CSRF token. Reload the form and try again.")
        return form

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
        groups = {}
        if any(item.options.group is not None for item in resources):
            for item in resources:
                label = item.options.group or self.gettext("Other collections")
                groups.setdefault(label, []).append(item)
            trusted_scripts += ("navigation.js",)
        dependencies = []
        for name in trusted_scripts:
            if name in {"forms.js", "history.js"}:
                dependencies.append("datetime.js")
            dependencies.append(name)
        scripts = []
        for name in dict.fromkeys(dependencies):
            if name not in {
                "relations.js",
                "schema.js",
                "filters.js",
                "forms.js",
                "datetime.js",
                "navigation.js",
                "listing.js",
                "inline.js",
                "history.js",
            }:
                raise ValueError("Unknown built-in script.")
            digest = base64.b64encode(
                hashlib.sha256((Path(__file__).parent / "static" / name).read_bytes()).digest()
            ).decode()
            scripts.append(
                {"url": self._url(request, "/assets/" + name), "integrity": "sha256-" + digest}
            )
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
            "resource_groups": groups,
            "pages": pages,
            "history_allowed": identity is not None and await self._history_allowed(request),
            "csrf": self._csrf(request),
            "url": lambda path="/": self._url(request, path),
            "breadcrumbs": self._breadcrumbs(request, template, context),
        }
        return self.templates.TemplateResponse(
            request=request, name=template, context={**context, **shared}, status_code=status
        )

    def _breadcrumbs(self, request, template, context):
        items = [{"label": self.gettext("Overview"), "url": self._url(request, "/")}]
        resource = context.get("resource")
        if resource is not None:
            items.append(
                {"label": resource.label, "url": self._url(request, f"/models/{resource.slug}/")}
            )
            record = context.get("record")
            if record:
                items.append(
                    {
                        "label": resource.record_label(record),
                        "url": self._url(
                            request, f"/models/{resource.slug}/{resource.schema.record_key(record)}"
                        ),
                    }
                )
            if context.get("creating"):
                items.append({"label": self.gettext("Create record"), "url": None})
            elif template == "quite_admin/delete.html":
                items.append({"label": self.gettext("Delete record"), "url": None})
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

    async def _error(self, request: Request, exc: Exception) -> Response:
        if isinstance(exc, HTTPException) and exc.status_code == 303:
            return Response(status_code=303, headers=exc.headers)
        status = getattr(exc, "status_code", 500)
        message = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return await self._render(
            request, "quite_admin/error.html", status=status, error=message, status_code=status
        )

    async def _login(self, request: Request) -> Response:
        error = None
        status = 200
        if request.method == "POST":
            form = await self._form(request)
            client = request.client.host if request.client else "unknown"
            retry = self.throttle.attempt(client)
            if retry:
                await self._logging.emit("warning", "quite_admin.login_throttled", status_code=429)
                response = await self._render(
                    request,
                    "quite_admin/login.html",
                    status=429,
                    error="Too many attempts. Try again shortly.",
                )
                response.headers["retry-after"] = str(retry)
                return response
            username = str(form.get("username", ""))
            password = str(form.get("password", ""))
            if len(username) > 256 or len(password) > 1024:
                raise HTTPException(400, "Credentials are too long.")
            identity = await self.auth.authenticate(request, username, password)
            if identity is not None:
                if self.history_enabled:
                    await self._storage_ready()
                request.state.identity = identity
                request.state.quite_admin_activity = ("", "login")
                self.throttle.reset(client)
                request.session.clear()
                request.session.update(subject=identity.subject, csrf=secrets.token_urlsafe(32))
                await self._logging.emit("info", "quite_admin.login_succeeded", status_code=303)
                return self._redirect(request, "/")
            await self._logging.emit("warning", "quite_admin.login_failed", status_code=401)
            error, status = "Invalid username or password.", 401
        return await self._render(request, "quite_admin/login.html", error=error, status=status)

    async def _logout(self, request: Request) -> Response:
        await self._identity(request)
        request.state.quite_admin_activity = ("", "logout")
        await self._form(request)
        request.session.clear()
        await self._logging.emit("info", "quite_admin.logout", status_code=303)
        return self._redirect(request, "/login")

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
            users = await self.storage.actors(collections=("", *resources), search=search)
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
            [subject, collection, action, outcome, collections, date_from, date_to]
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
            result = await self.storage.activities(
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
            users = await self.storage.actors(collections=collections)
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
            "collection": [("__auth__", self.gettext("Authentication"))]
            + [(slug, resource.label) for slug, resource in resources.items()],
            "action": [(name, self.gettext(label)) for name, label in actions.items()],
            "outcome": [("success", self.gettext("Success")), ("failure", self.gettext("Failure"))],
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
            history_actions=actions,
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
        today = datetime.now(UTC).date()
        first_changes = True
        for event in events:
            resource = resources.get(event.collection)
            fields = (
                {
                    field.name: field
                    for field in resource.options.visible_fields(resource.schema)
                    if not sensitive_name(field.name)
                }
                if resource
                else {}
            )
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
                                field.name
                                in {
                                    item.name
                                    for item in editor["target"].options.visible_fields(
                                        editor["target"].schema
                                    )
                                }
                                and not sensitive_name(field.name)
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

    async def _dashboard(self, request: Request) -> Response:
        await self._identity(request)
        return await self._render(request, "quite_admin/dashboard.html")

    async def _schema(self, request):
        await self._identity(request)
        all_resources = tuple((await self.resources()).values())
        resources = [
            resource
            for resource in all_resources
            if await self._allowed(request, resource, "list")
            and await self._allowed(request, resource, "view")
        ]
        graph = await schema_graph(resources, all_resources=all_resources)
        for node in graph["nodes"] + graph["junctions"]:
            node["url"] = (
                self._url(request, f"/models/{node['id']}/") if not node.get("junction") else None
            )
        return await self._render(
            request,
            "quite_admin/schema.html",
            schema_page=True,
            graph=graph,
            schema_messages=self._schema_messages(),
            trusted_scripts=("schema.js",) if graph["nodes"] else (),
        )

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

    async def _page(self, request: Request) -> Response:
        await self._identity(request)
        page = self.pages.get(request.path_params["slug"])
        if page is None:
            raise NotFound("Page not found.")
        if not await self._page_allowed(request, page):
            raise HTTPException(403, "You do not have permission to view this page.")
        if page.context is None:
            context = {}
        elif inspect.iscoroutinefunction(page.context):
            context = await page.context(request)
        else:
            context = await to_thread.run_sync(page.context, request)
        if inspect.isawaitable(context):
            context = await context
        context = dict(context)
        # Page data cannot replace renderer arguments or grant script permissions.
        for name in ("request", "template", "page", "status", "trusted_scripts"):
            context.pop(name, None)
        return await self._render(request, page.template, page=page, **context)

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
            window = await resource.adapter.list_window(
                resource.model, query, after=after, before=before
            )
            result = window
        else:
            if "after" in request.query_params or "before" in request.query_params:
                raise HTTPException(400, "Cursor parameters require cursor pagination.")
            result = await resource.adapter.list(resource.model, query)
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
        return await self._render(
            request,
            "quite_admin/list.html",
            listing_page=True,
            inline_fields=inline_fields,
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

    def _form_messages(self):
        return {
            name: self.gettext(name)
            for name in (
                "True",
                "False",
                "None",
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
                    for item in resource.options.visible_fields(resource.schema)
                    if item.name
                    in (
                        resource.options.list_fields
                        or [f.name for f in resource.options.visible_fields(resource.schema)[:6]]
                    )
                },
            }
        )

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
        return await self._render(
            request,
            "quite_admin/form.html",
            trusted_scripts=(
                (("relations.js",) if any(item["editable"] for item in editors) else ())
                + (
                    ("forms.js",)
                    if editable
                    and any(
                        item.name in resource.options.writable_fields(resource.schema, creating)
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
            writable=resource.options.writable_fields(resource.schema, creating)
            if editable
            else {},
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
            after = await resource.adapter.get(resource.model, key)
        elif not isinstance(after, Mapping):
            after = await resource.adapter.get(resource.model, key) if key is not None else None
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
            linked = await resource.adapter.related(
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

    async def _action_allowed(self, request, resource, action):
        if not await self._allowed(request, resource, action.required_permission):
            return False
        if action.permission is None:
            return True
        result = action.permission(request, request.state.identity, action.required_permission)
        return bool(await result if inspect.isawaitable(result) else result)

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

    def _picker_messages(self):
        return {
            name: self.gettext(text)
            for name, text in {
                "choose": "Choose records",
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
        resources = tuple((await self.resources()).values())
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
            target = next(
                (
                    item
                    for item in resources
                    if item.adapter is resource.adapter and item.model is relation.target
                ),
                None,
            )
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
