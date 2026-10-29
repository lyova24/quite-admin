from __future__ import annotations

import inspect
import re
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anyio import to_thread
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
from starlette.types import ASGIApp, Receive, Scope, Send

from .adapters.base import Adapter
from .auth import AuthBackend, Identity, LoginThrottle
from .config import Action, ModelOptions, Permission
from .errors import AdminError, Conflict, NotFound, ValidationError
from .i18n import Language, Translator
from .logging import EventLogger, LoggerProtocol
from .relations import RelationAdapter
from .schema import ModelSchema, Query
from .theme import Theme

SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
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
        ):
            if name in visible and record.get(name) is not None:
                return visible[name].format(record[name])[:200]
        return " · ".join(
            field.format(record.get(field.name)) for field in self.schema.primary_keys
        )


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
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"same-origin"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; style-src 'self'; "
                            b"script-src 'none'; img-src 'self' data:; object-src 'none'; "
                            b"base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
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
    ) -> None:
        if len(secret_key.encode()) < 32:
            raise ValueError("secret_key must contain at least 32 bytes of random secret material.")
        if session_max_age <= 0:
            raise ValueError("session_max_age must be positive.")
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
            Route("/pages/{slug}", self._page),
            Route("/models/{slug}/", self._list),
            Route("/models/{slug}/new", self._create, methods=["GET", "POST"]),
            Route("/models/{slug}/{key}/edit", self._edit, methods=["GET", "POST"]),
            Route("/models/{slug}/{key}/delete", self._delete, methods=["GET", "POST"]),
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
        await self.app(dict(scope), receive, send)

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
            models = dict.fromkeys(discovered)
            models.update(dict.fromkeys(source.options))
            for model in models:
                schema = source.adapter.describe(model)
                original_slug = (
                    f"{source.namespace}-{schema.name}" if source.namespace else schema.name
                )
                options = self.collection_options.get(
                    original_slug, source.options.get(model, ModelOptions())
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

    async def _resource(
        self, request: Request, action: Action, *, alternatives: tuple[Action, ...] = ()
    ) -> Resource:
        await self._identity(request)
        resource = (await self.resources()).get(request.path_params["slug"])
        if resource is None:
            raise NotFound("Table not found.")
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
        self, request: Request, template: str, *, status: int = 200, **context: Any
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
        shared = {
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
            "pages": pages,
            "csrf": self._csrf(request),
            "url": lambda path="/": self._url(request, path),
        }
        return self.templates.TemplateResponse(
            request=request, name=template, context={**context, **shared}, status_code=status
        )

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
        await self._form(request)
        request.session.clear()
        await self._logging.emit("info", "quite_admin.logout", status_code=303)
        return self._redirect(request, "/login")

    async def _dashboard(self, request: Request) -> Response:
        await self._identity(request)
        return await self._render(request, "quite_admin/dashboard.html")

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
        return await self._render(request, page.template, page=page, **context)

    async def _list(self, request: Request) -> Response:
        resource = await self._resource(request, "list")
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
        search = request.query_params.get("q", "")[:500]
        search_fields = resource.options.search_fields
        if search_fields is None:
            search_fields = tuple(item.name for item in fields if item.kind == "string")
        search_fields = tuple(name for name in search_fields if name in visible)
        query = Query(
            offset=(page - 1) * limit,
            limit=limit,
            search=search,
            search_fields=search_fields,
            order_by=order,
            descending=request.query_params.get("direction") == "desc",
        )
        result = await resource.adapter.list(resource.model, query)
        permissions = {
            action: await self._allowed(request, resource, action)
            for action in ("view", "create", "edit", "delete")
        }
        base = self._url(request, f"/models/{resource.slug}/")

        def query_url(**updates: Any) -> str:
            return (
                base
                + "?"
                + str(request.query_params.__class__({**dict(request.query_params), **updates}))
            )

        return await self._render(
            request,
            "quite_admin/list.html",
            resource=resource,
            columns=columns,
            result=result,
            page_number=page,
            limit=limit,
            query=query,
            query_url=query_url,
            permissions=permissions,
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

    async def _edit_form(
        self, request: Request, resource: Resource, *, creating: bool, editable: bool = True
    ) -> Response:
        record = {} if creating else await self._record(resource, request.path_params["key"])
        editors = await self._relation_editors(
            request, resource, record, creating=creating, allow_edit=editable
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
        if request.method == "POST":
            if not editable:
                raise HTTPException(403, "You do not have permission to perform this action.")
            multi = frozenset(
                "__relation__" + editor["relation"].name
                for editor in editors
                if editor["editable"] and editor["multiple"]
            )
            form = await self._form(request, multi_fields=multi)
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
                if selections:
                    saved = await resource.adapter.save_relations(
                        resource.model,
                        changes,
                        selections,
                        key=None
                        if creating
                        else resource.schema.parse_key(request.path_params["key"]),
                    )
                elif creating:
                    saved = await resource.adapter.create(resource.model, changes)
                else:
                    saved = await resource.adapter.update(
                        resource.model,
                        resource.schema.parse_key(request.path_params["key"]),
                        changes,
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
        return await self._render(
            request,
            "quite_admin/form.html",
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
            editable=editable,
            record=record,
            can_delete=not creating and await self._allowed(request, resource, "delete"),
            form_action=self._url(
                request,
                f"/models/{resource.slug}/new"
                if creating
                else f"/models/{resource.slug}/{resource.schema.record_key(record)}",
            ),
        )

    async def _relation_editors(self, request, resource, record, *, creating, allow_edit=True):
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
        editors = []
        for relation in relations:
            if (
                resource.options.relations is not None
                and relation.name not in resource.options.relations
            ):
                continue
            if set(relation.source_fields) & set(resource.options.exclude):
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
            if set(relation.target_fields) & set(target.options.exclude):
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
            linked = (
                None
                if creating
                else await resource.adapter.related(
                    resource.model,
                    relation.name,
                    resource.schema.parse_key(resource.schema.record_key(record)),
                    Query(limit=1001),
                )
            )
            selected = [] if linked is None else linked.records[:1000]
            truncated = linked is not None and linked.total > 1000
            editable = editable and not truncated
            candidates = (
                await target.adapter.list(target.model, Query(limit=1000)) if editable else None
            )
            records = {target.schema.record_key(item): item for item in selected}
            if candidates is not None:
                records.update(
                    {target.schema.record_key(item): item for item in candidates.records}
                )
            editors.append(
                {
                    "relation": relation,
                    "target": target,
                    "editable": editable,
                    "multiple": relation.kind in {"one_to_many", "many_to_many"},
                    "selected": [target.schema.record_key(item) for item in selected],
                    "choices": [(key, target.record_label(item)) for key, item in records.items()],
                    "truncated": truncated or candidates is not None and candidates.total > 1000,
                }
            )
        return editors

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
            await resource.adapter.delete(resource.model, resource.schema.parse_key(token))
            await self._logging.emit(
                "info", "quite_admin.record_deleted", collection=resource.slug, status_code=303
            )
            return self._redirect(request, f"/models/{resource.slug}/")
        return await self._render(
            request, "quite_admin/delete.html", resource=resource, record=record
        )
