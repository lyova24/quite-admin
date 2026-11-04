"""ASGI security headers and the Litestar mount compatibility bridge."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

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
STATIC_DIR = Path(__file__).parents[1] / "static"


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


def litestar_route(admin, path: str) -> Any:
    from litestar import asgi
    from litestar.exceptions import HTTPException as LitestarHTTPException

    body_limit_detail = admin.gettext("The form exceeds 1 MiB.")

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
        def on_registration(self, app):
            super().on_registration(app)
            if admin.aclose not in app.on_shutdown:
                app.on_shutdown.append(admin.aclose)

        # Litestar 2's body-reading LoggingMiddleware calls this HTTP-handler
        # method even for ASGI mounts. Keep the compatibility bridge local.
        def resolve_request_max_body_size(self) -> int:
            return FORM_BODY_LIMIT

        def resolve_middleware(self) -> list:
            # Litestar wraps this list inside-out. Count bytes before the
            # host's body-reading log middleware, only for this admin mount.
            return [*super().resolve_middleware(), BodyLimitMiddleware]

    mount_path = admin._mount_path(path)

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
            await admin(forwarded, receive, send)
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
            await admin(forwarded, replay_body, send)
        finally:
            await stream.aclose()

    return AdminASGIHandler(path=mount_path, is_mount=True, copy_scope=True)(mounted)
