from __future__ import annotations

import asyncio
import io
import json
import logging
import subprocess
import sys
from contextlib import contextmanager
from urllib.parse import urlencode

import pytest
import structlog
from anyio import to_thread
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.middleware.logging import LoggingMiddlewareConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin
from uvicorn.logging import DefaultFormatter

from quite_admin import Admin, ModelOptions, Page, Query

from .helpers import csrf, login, revision


class RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@contextmanager
def recording_logger(name="quite_admin.tests"):
    logger = logging.getLogger(name)
    previous = logger.handlers[:], logger.level, logger.propagate, logger.disabled
    handler = RecordingHandler()
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.disabled = False
    try:
        yield logger, handler.records
    finally:
        logger.handlers, logger.level, logger.propagate, logger.disabled = previous


def quiet_config():
    return LoggingConfig(
        logging_module="logging",
        configure_root_logger=False,
        handlers={"silent": {"class": "logging.NullHandler"}},
        loggers={"litestar": {"handlers": ["silent"], "propagate": False}},
    )


@pytest.fixture(autouse=True)
def preserve_structlog_configuration():
    configured = structlog.is_configured()
    config = structlog.get_config().copy()
    try:
        yield
    finally:
        structlog.reset_defaults()
        if configured:
            structlog.configure(**config)
        structlog.contextvars.clear_contextvars()


def test_import_and_instances_leave_application_logging_untouched():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import logging, logging.config
root = logging.getLogger()
handler = logging.NullHandler()
root.handlers = [handler]
root.setLevel(logging.ERROR)
def forbidden(*args, **kwargs):
    raise AssertionError('The library must not configure application logging')
logging.basicConfig = logging.config.dictConfig = forbidden
from quite_admin import Admin
for _ in range(2):
    Admin(auth=object(), secret_key='s' * 32)
assert root.handlers == [handler]
assert root.level == logging.ERROR
logger = logging.getLogger('quite_admin')
assert logger.level == logging.NOTSET
assert logger.propagate
assert len(logger.handlers) == 1
assert isinstance(logger.handlers[0], logging.NullHandler)
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_default_logger_through_uvicorn_log_config():
    # Isolate the application's intentional dictConfig from pytest's log handlers.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio, io, logging, re
from copy import deepcopy
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from uvicorn import Config
from uvicorn.config import LOGGING_CONFIG
from quite_admin import Admin, PasswordAuth

events, access = io.StringIO(), io.StringIO()
configuration = deepcopy(LOGGING_CONFIG)
configuration['handlers']['default']['stream'] = events
configuration['handlers']['access']['stream'] = access
configuration['loggers']['quite_admin'] = {
    'handlers': ['default'], 'level': 'INFO', 'propagate': False,
}
host = FastAPI()
config = Config(host, log_config=configuration, ws='none', lifespan='off')
admin = Admin(auth=PasswordAuth.single_user('admin', 'local-test-only'),
              secret_key='s' * 32, secure_cookies=False)
admin.mount_fastapi(host)
config.load()

async def main():
    async with AsyncClient(transport=ASGITransport(app=config.loaded_app),
                           base_url='http://test') as client:
        form = await client.get('/admin/login')
        token = re.search(r'name="__csrf" value="([^"]+)"', form.text).group(1)
        response = await client.post('/admin/login', data={
            '__csrf': token, 'username': 'admin', 'password': 'local-test-only',
        })
        assert response.status_code == 303
asyncio.run(main())
assert events.getvalue().count('quite_admin.login_succeeded') == 1
assert 'local-test-only' not in events.getvalue()
logging.getLogger('uvicorn.access').info('%s - "%s %s HTTP/%s" %d',
    '127.0.0.1:1', 'GET', '/health', '1.1', 200)
assert 'GET /health HTTP/1.1' in access.getvalue()
assert 'quite_admin' not in access.getvalue()
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_events_with_uvicorn_formatter_and_litestar_logging(backend, auth, framework):
    adapter, model = backend
    host = FastAPI() if framework == "fastapi" else Litestar(logging_config=quiet_config())
    with recording_logger() as (logger, records):
        if framework == "litestar":
            assert host.get_logger(logger.name) is logger
        admin = Admin(
            auth=auth, secret_key="s" * 32, adapters=[adapter], logger=logger, secure_cookies=False
        )
        admin.register(
            model, options=ModelOptions(exclude=("internal",), readonly_fields=("count",))
        )
        if framework == "fastapi":
            admin.mount_fastapi(host)
        else:
            admin.mount_litestar(host)
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            form = await client.get("/admin/login")
            token = csrf(form)
            bad = await client.post(
                "/admin/login",
                data={
                    "__csrf": token,
                    "username": "PRIVATE_USERNAME",
                    "password": "PRIVATE_PASSWORD",
                },
            )
            assert bad.status_code == 401
            await login(client)
            form = await client.get("/admin/models/items/new")
            token = csrf(form)
            saved = await client.post(
                "/admin/models/items/new",
                data={
                    "__csrf": token,
                    "name": "PRIVATE_RECORD_VALUE",
                    "active": "true",
                    "note": "PRIVATE_NOTE_VALUE",
                },
            )
            assert saved.status_code == 303, saved.text
            detail = saved.headers["location"]
            edit_form = await client.get(detail)
            edited = await client.post(
                detail + "/edit",
                data={
                    "__csrf": token,
                    "__revision": revision(edit_form),
                    "note": "PRIVATE_EDIT_VALUE",
                },
            )
            assert edited.status_code == 303, edited.text
            assert (
                await client.post(detail + "/delete", data={"__csrf": token})
            ).status_code == 303
            assert (await client.post("/admin/logout", data={"__csrf": token})).status_code == 303
        assert [record.getMessage() for record in records] == [
            "quite_admin.login_failed",
            "quite_admin.login_succeeded",
            "quite_admin.record_created",
            "quite_admin.record_updated",
            "quite_admin.record_deleted",
            "quite_admin.logout",
        ]
        mutations = [record for record in records if record.msg.startswith("quite_admin.record_")]
        assert all(
            record.quite_admin == {"collection": "items", "status_code": 303}
            for record in mutations
        )
        formatter = DefaultFormatter(fmt="%(levelprefix)s %(message)s", use_colors=False)
        output = "\n".join(formatter.format(record) + str(record.quite_admin) for record in records)
        for private in ("PRIVATE_", "correct horse battery staple", token, detail):
            assert private not in output


async def test_logger_adapter_preserves_context_and_event_fields(auth):
    with recording_logger() as (logger, records):
        adapter = logging.LoggerAdapter(logger, {"request_id": "adapter-context"})
        admin = Admin(auth=auth, secret_key="s" * 32, logger=adapter, secure_cookies=False)
        host = FastAPI()
        admin.mount_fastapi(host)
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            await login(client)
        assert records[0].request_id == "adapter-context"
        assert records[0].quite_admin == {"status_code": 303}


async def test_litestar_queue_listener_backend(auth):
    output = io.StringIO()
    handlers = {
        "console": {"class": "logging.StreamHandler", "stream": output, "formatter": "standard"}
    }
    if sys.version_info < (3, 12):
        # Litestar's legacy handler defaults to its own stderr StreamHandler.
        # Unlike Python 3.12's QueueHandler config, it needs an explicit cfg:// reference.
        handlers["queue_listener"] = {
            "class": "litestar.logging.standard.QueueListenerHandler",
            "handlers": ["cfg://handlers.console"],
        }
    config = LoggingConfig(
        logging_module="logging",
        configure_root_logger=False,
        handlers=handlers,
        formatters={"standard": {"format": "%(message)s %(quite_admin)s"}},
        loggers={
            "quite_admin.queue": {
                "handlers": ["queue_listener"],
                "level": "INFO",
                "propagate": False,
            }
        },
    )
    host = Litestar(logging_config=config)
    logger = host.get_logger("quite_admin.queue")
    assert logger.handlers[0].listener.handlers[0].stream is output
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, logger=logger)
    admin.mount_litestar(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
    # Wait for the real queue listener, not a synchronous replacement handler.
    await to_thread.run_sync(logger.handlers[0].queue.join)
    assert output.getvalue().count("quite_admin.login_succeeded") == 1
    assert "'status_code': 303" in output.getvalue()


@pytest.mark.parametrize("framework", ["fastapi", "litestar_plugin"])
async def test_structlog_json_and_contextvars_across_async_and_worker_calls(
    auth, framework, tmp_path
):
    output = io.StringIO()
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
    if framework == "litestar_plugin":
        config = StructlogConfig(
            structlog_logging_config=StructLoggingConfig(
                processors=processors,
                logger_factory=structlog.WriteLoggerFactory(output),
                standard_lib_logging_config=quiet_config(),
            ),
            middleware_logging_config=LoggingMiddlewareConfig(
                request_log_fields=("method", "path"),
                response_log_fields=("status_code",),
            ),
        )
        host = Litestar(plugins=[StructlogPlugin(config)])
        logger = host.get_logger("quite_admin").bind(service="admin-service")
    else:
        host = FastAPI()
        logger = structlog.wrap_logger(
            structlog.WriteLogger(output),
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        )
        logger = logger.bind(service="admin-service")
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        logger=logger,
        log_structured=True,
        secure_cookies=False,
        templates_dir=tmp_path,
    )
    (tmp_path / "context.html").write_text("<p>ok</p>")

    def worker_context(request):
        logger.info("worker_event")
        return {}

    admin.add_page(Page("context", "Context", "context.html", context=worker_context))
    if framework == "fastapi":
        admin.mount_fastapi(host)
    else:
        admin.mount_litestar(host)

    class ContextMiddleware:
        async def __call__(self, scope, receive, send):
            structlog.contextvars.clear_contextvars()
            request_id = dict(scope["headers"]).get(b"x-request-id", b"unknown").decode()
            structlog.contextvars.bind_contextvars(request_id=request_id)
            try:
                await host(scope, receive, send)
            finally:
                structlog.contextvars.clear_contextvars()

    async def session(request_id):
        async with AsyncClient(
            transport=ASGITransport(app=ContextMiddleware()),
            base_url="http://test",
            headers={"x-request-id": request_id},
        ) as client:
            await login(client)
            assert (await client.get("/admin/pages/context")).status_code == 200

    await asyncio.gather(session("request-one"), session("request-two"))
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    own = [
        event
        for event in events
        if event["event"] in {"quite_admin.login_succeeded", "worker_event"}
    ]
    assert len(own) == 4
    assert {event["request_id"] for event in own} == {"request-one", "request-two"}
    assert all(event["service"] == "admin-service" for event in own)
    assert all(event["level"] == "info" for event in own)
    assert len([event for event in own if event["event"] == "quite_admin.login_succeeded"]) == 2
    if framework == "litestar_plugin":
        assert any(event["event"] == "HTTP Request" for event in events)
        assert any(event["event"] == "HTTP Response" for event in events)
    assert "correct horse battery staple" not in output.getvalue()


async def test_loguru_structured_interface(auth):
    from loguru import logger

    records = []
    sink = logger.add(
        lambda message: records.append(message.record),
        filter=lambda record: record["extra"].get("quite_admin_test"),
        format="{message}",
    )
    try:
        admin = Admin(
            auth=auth,
            secret_key="s" * 32,
            secure_cookies=False,
            logger=logger.bind(quite_admin_test=True),
            log_structured=True,
        )
        host = FastAPI()
        admin.mount_fastapi(host)
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            await login(client)
        assert len(records) == 1
        assert records[0]["message"] == "quite_admin.login_succeeded"
        assert records[0]["extra"]["status_code"] == 303
    finally:
        logger.remove(sink)


async def test_async_logger_methods_are_awaited(auth):
    events = []

    class AsyncLogger:
        async def info(self, event, **fields):
            await asyncio.sleep(0)
            events.append((event, fields))

        debug = warning = info

    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        logger=AsyncLogger(),
        log_structured=True,
    )
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
    assert events == [("quite_admin.login_succeeded", {"status_code": 303})]


async def test_broken_sink_does_not_fail_committed_writes(backend, auth, caplog):
    class BrokenLogger:
        def info(self, *args, **kwargs):
            raise RuntimeError("PRIVATE_SINK_ERROR")

        debug = warning = info

    adapter, _ = backend
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        logger=BrokenLogger(),
    )
    host = FastAPI()
    admin.mount_fastapi(host)
    with caplog.at_level(logging.WARNING, logger="quite_admin"):
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            await login(client)
            form = await client.get("/admin/models/items/new")
            result = await client.post(
                "/admin/models/items/new",
                data={
                    "__csrf": csrf(form),
                    "name": "committed",
                },
            )
            assert result.status_code == 303, result.text
        _, model = backend
        assert (await adapter.list(model, Query())).total == 1
    errors = [record for record in caplog.records if record.msg == "quite_admin.logging_failed"]
    assert len(errors) == 2
    assert all(record.quite_admin["error_type"] == "RuntimeError" for record in errors)
    assert "PRIVATE_SINK_ERROR" not in caplog.text


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_unhandled_errors_reach_host_server(auth, framework, tmp_path):
    with recording_logger() as (logger, records):
        admin = Admin(
            auth=auth,
            secret_key="s" * 32,
            secure_cookies=False,
            logger=logger,
            templates_dir=tmp_path,
        )

        async def fail(request):
            raise RuntimeError("PRIVATE_EXCEPTION_TEXT")

        admin.add_page(Page("broken", "Broken", "unused.html", context=fail))
        if framework == "fastapi":
            host = FastAPI()
            admin.mount_fastapi(host)
        else:
            host = Litestar(route_handlers=[admin.litestar_route()], logging_config=quiet_config())
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            await login(client)
            with pytest.raises(Exception) as error:
                await client.get("/admin/pages/broken")
        original = error.value
        while original.__cause__ is not None:
            original = original.__cause__
        assert isinstance(original, RuntimeError)
        assert str(original) == "PRIVATE_EXCEPTION_TEXT"
        assert [record.msg for record in records] == ["quite_admin.login_succeeded"]


async def test_litestar_picologging(auth):
    picologging = pytest.importorskip("picologging")
    output = io.StringIO()
    config = LoggingConfig(
        logging_module="picologging",
        configure_root_logger=False,
        handlers={
            "capture": {
                "()": lambda: picologging.StreamHandler(output),
                "formatter": "standard",
            }
        },
        formatters={"standard": {"format": "%(name)s %(message)s"}},
        loggers={
            "litestar": {"handlers": ["capture"], "level": "INFO", "propagate": False},
            "quite_admin.pico": {"handlers": ["capture"], "level": "INFO", "propagate": False},
        },
    )
    host = Litestar(
        logging_config=config,
        middleware=[
            LoggingMiddlewareConfig(
                request_log_fields=("method", "path"),
                response_log_fields=("status_code",),
            ).middleware
        ],
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        logger=host.get_logger("quite_admin.pico"),
    )
    admin.mount_litestar(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
    assert output.getvalue().count("quite_admin.login_succeeded") == 1
    assert "HTTP Request" in output.getvalue()
    assert "HTTP Response" in output.getvalue()


def test_structured_mode_rejects_a_standard_logger(auth):
    with pytest.raises(ValueError, match="explicit structured logger"):
        Admin(auth=auth, secret_key="s" * 32, log_structured=True)
    with pytest.raises(ValueError, match="log_structured=False"):
        Admin(auth=auth, secret_key="s" * 32, logger=logging.getLogger("test"), log_structured=True)


@pytest.mark.parametrize("read_body", [False, True])
async def test_litestar_streamed_and_cached_forms_keep_body_limit(auth, read_body):
    config = quiet_config()
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False)
    host = Litestar(
        route_handlers=[admin.litestar_route()],
        logging_config=config,
        middleware=[
            LoggingMiddlewareConfig(
                request_log_fields=("method", "body") if read_body else ("method",),
                response_log_fields=("status_code",),
            ).middleware
        ],
    )

    async def chunks(body):
        for offset in range(0, len(body), 16 * 1024):
            await asyncio.sleep(0)
            yield body[offset : offset + 16 * 1024]

    headers = {"content-type": "application/x-www-form-urlencoded"}
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        initial = await client.get("/admin/login")
        payload = urlencode(
            {
                "__csrf": csrf(initial),
                "username": "admin",
                "password": "correct horse battery staple",
            }
        ).encode()
        response = await client.post("/admin/login", content=chunks(payload), headers=headers)
        assert response.status_code == 303, response.text
        oversized = await client.post(
            "/admin/login", content=chunks(b"x=" + b"x" * (1024 * 1024)), headers=headers
        )
        assert oversized.status_code == 413, oversized.text
