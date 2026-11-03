from __future__ import annotations

import inspect
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anyio import to_thread
from itsdangerous import URLSafeTimedSerializer
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader, select_autoescape
from starlette.applications import Starlette
from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import Receive, Scope, Send

from ._admin.exporting import ExportViews
from ._admin.history import HistoryViews
from ._admin.listing import ListingViews
from ._admin.records import RecordViews
from ._admin.relations import RelationViews
from ._admin.rendering import Rendering
from ._admin.web import FORM_BODY_LIMIT as FORM_BODY_LIMIT
from ._admin.web import LOGO_TYPES, SLUG, STATIC_DIR, SecurityHeaders, litestar_route
from ._admin.web import TEMPLATE_API_VERSION as TEMPLATE_API_VERSION
from ._reads import ReadLimits
from .activity import HistoryLevel, validate_history_level
from .adapters.base import Adapter
from .auth import AuthBackend, Identity, LoginThrottle
from .config import Action, ModelOptions, Permission
from .diagram import schema_graph
from .errors import AdminError, NotFound
from .i18n import Language, Translator
from .logging import EventLogger, LoggerProtocol
from .operations import OperationHooks
from .schema import ModelSchema
from .storage import TABLE_PREFIX, AdminStore, StorageError, create_store
from .theme import Theme

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

    def _label_fields(self, visible):
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
            if name in visible:
                yield visible[name]

    def record_label(self, record: Mapping[str, Any]) -> str:
        visible = {item.name: item for item in self.options.visible_fields(self.schema)}
        for item in self._label_fields(visible):
            if record.get(item.name) is not None:
                return item.format(record[item.name])[:200]
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
            # Include nullable fallbacks until one label is guaranteed to exist.
            for item in self._label_fields(visible):
                selected.add(item.name)
                if not item.nullable:
                    break
        return tuple(item.name for item in self.schema.fields if item.name in selected)


@dataclass
class Source:
    adapter: Adapter
    discover: bool
    namespace: str | None
    options: dict[Any, ModelOptions] = field(default_factory=dict)


class Admin(HistoryViews, ListingViews, RecordViews, RelationViews, Rendering, ExportViews):
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
        query_timeout: float | None = None,
        max_concurrent_reads: int | None = None,
        history_level: HistoryLevel = "changes",
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
        self._read_limits = ReadLimits(query_timeout, max_concurrent_reads)
        self.storage = create_store(storage)
        self.history_permission = history_permission
        self.history_enabled = history_enabled
        self.history_level = validate_history_level(history_level)
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
            Mount("/assets", app=StaticFiles(directory=STATIC_DIR)),
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
            discovered = await self._read(source.adapter.discover) if source.discover else ()
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

    async def _read(self, operation, *args, **kwargs):
        return await self._read_limits.run(operation, *args, **kwargs)

    def mount_fastapi(self, app: Any, path: str = "/admin") -> None:
        app.mount(self._mount_path(path), self, name="quite-admin")

    def litestar_route(self, path: str = "/admin") -> Any:
        return litestar_route(self, path)

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
        return await self._permission_allowed(request, options.permission, action)

    async def _permission_allowed(self, request, permission, action):
        if permission is None:
            return True
        decision = permission(request, request.state.identity, action)
        return bool(await decision if inspect.isawaitable(decision) else decision)

    async def _page_allowed(self, request: Request, page: Page) -> bool:
        return await self._permission_allowed(request, page.permission, "view")

    async def _history_allowed(self, request):
        return self.history_enabled and await self._permission_allowed(
            request, self.history_permission, "view"
        )

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
