# Logging

quite-admin uses the application's logging configuration.
It never calls `basicConfig()`, `dictConfig()` or `structlog.configure()`, sets a logging
level, adds a console/file handler, or reconfigures application/root loggers.
The default logger is `logging.getLogger("quite_admin")`, with a `NullHandler` and propagation enabled.

## Choose a logger

```python
import logging
from quite_admin import Admin

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=logging.getLogger("quite_admin"),  # Optional; this is the default
)
```

`logger` accepts a stdlib logger, `LoggerAdapter`, picologging logger, or a structured
logger. `LoggerProtocol` describes the `debug`, `info` and `warning` methods; they may
return `None` or an awaitable. The configured logger is also available as `admin.logger`.

| Mode | Call shape | Metadata location |
| --- | --- | --- |
| `log_structured=False` (default) | `logger.info(event, extra={"quite_admin": fields})` | `LogRecord.quite_admin` in stdlib logging; see the picologging limitation below |
| `log_structured=True` | `logger.info(event, **fields)` | Structured event fields |

Structured mode requires an explicit structured logger. A stdlib `Logger` or
`LoggerAdapter` with `log_structured=True` is rejected at initialization.
`LoggerAdapter` context is preserved alongside the `quite_admin` metadata namespace,
including on Python versions where the adapter discards caller-supplied `extra` by default.

## FastAPI and Uvicorn

FastAPI uses Python logging; server, access and exception logging are configured in
[Uvicorn](https://uvicorn.dev/concepts/logging/). To route library events through
Uvicorn's normal formatter while retaining its existing loggers:

```python
from copy import deepcopy
import uvicorn
from uvicorn.config import LOGGING_CONFIG

log_config = deepcopy(LOGGING_CONFIG)
log_config["loggers"]["quite_admin"] = {
    "handlers": ["default"],
    "level": "INFO",
    "propagate": False,
}

if __name__ == "__main__":
    uvicorn.run("myapp:app", log_config=log_config)
```

The default text formatter shows the event name. Use your own JSON formatter or
`structlog.stdlib.ProcessorFormatter` with `structlog.stdlib.ExtraAdder` to include
`LogRecord.quite_admin` in structured output.
Do not send library events to `uvicorn.access`: its formatter expects Uvicorn's access-record fields.
You can also provide Uvicorn's `--log-config` instead of configuring it in Python.

## Litestar LoggingConfig and queues

The current stable Litestar 2 API offers `LoggingConfig`, its queue-based handler,
picologging and `StructlogPlugin`; see the [Litestar logging guide](https://docs.litestar.dev/2/usage/logging.html).
Pass the logger returned by the application so the admin uses the same backend:

```python
from litestar import Litestar
from litestar.logging import LoggingConfig
from litestar.middleware.logging import LoggingMiddlewareConfig
from quite_admin import Admin

app = Litestar(
    logging_config=LoggingConfig(logging_module="logging", log_exceptions="always"),
    middleware=[LoggingMiddlewareConfig(
        request_log_fields=("method", "path"),
        response_log_fields=("status_code",),
    ).middleware],
)
admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=app.get_logger("quite_admin"),
)
admin.mount_litestar(app)
```

The application's queue listener, formatter and levels remain in control.
For picologging, select `logging_module="picologging"` and pass `app.get_logger(...)`
in the same way. Without an explicit module, Litestar 2 selects picologging when installed.
Calling stdlib `logging.getLogger()` does not select a picologging logger.

The tested picologging 0.9.3 accepts but ignores `extra`: event names and levels work,
but `LogRecord.quite_admin` is unavailable. Do not use `%(quite_admin)s` in its formatter.
For metadata fields, select `logging_module="logging"` as above or use `StructlogPlugin`.
quite-admin does not patch picologging or modify application filters to work around this backend limitation.

## StructlogPlugin and structured logging

Install `structlog` in the application, then use Litestar's plugin:

```python
from litestar import Litestar
from litestar.middleware.logging import LoggingMiddlewareConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin
from quite_admin import Admin

plugin = StructlogPlugin(StructlogConfig(
    middleware_logging_config=LoggingMiddlewareConfig(
        request_log_fields=("method", "path"),
        response_log_fields=("status_code",),
    ),
))
app = Litestar(plugins=[plugin])
admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=app.get_logger("quite_admin").bind(component="admin"),
    log_structured=True,
)
admin.mount_litestar(app)
```

For FastAPI, pass `structlog.get_logger("quite_admin")` with `log_structured=True` after
configuring structlog in the application. A logger already configured with
`structlog.stdlib.ProcessorFormatter` also works; renderer setup remains the application's responsibility.

Include `structlog.contextvars.merge_contextvars` in your processor chain to retain
request IDs and tracing context. The admin neither binds nor clears application context.
Its ASGI boundary keeps the request context, and AnyIO carries it into synchronous
custom-page callbacks executed in worker threads.

Loguru can use the same structured call shape:

```python
from loguru import logger

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=logger.bind(component="admin"),
    log_structured=True,
)
```

Metadata is available in Loguru's `record["extra"]`. Configure sinks and queues in the application.
Neither structlog, Loguru nor picologging becomes a required dependency of quite-admin.

## Request logging middleware

Mounted routes work with Litestar's body-reading `LoggingMiddleware`, including cached
request bodies, streamed forms and the admin's 1 MiB body limit.
The mount provides a local body-limit resolver for Litestar 2's ASGI handler and replays
the public `Request.stream()` API into ASGI receive messages. A per-mount receive guard
counts bytes before body-reading middleware, including parser retries. Framework classes are not patched.

Litestar's default request/response logging includes bodies and cookies. For admin routes,
use the restricted fields shown above: login bodies contain passwords and CSRF tokens,
and responses can contain session cookies and record values. The admin cannot redact
data that an outer application middleware logs independently.

## Library events

| Event | Level | Fields |
| --- | --- | --- |
| `quite_admin.login_succeeded` | INFO | `status_code` |
| `quite_admin.login_failed` | WARNING | `status_code` |
| `quite_admin.login_throttled` | WARNING | `status_code` |
| `quite_admin.logout` | INFO | `status_code` |
| `quite_admin.record_created` | INFO | `collection`, `status_code` |
| `quite_admin.record_updated` | INFO | `collection`, `status_code` |
| `quite_admin.record_deleted` | INFO | `collection`, `status_code` |
| `quite_admin.record_conflict` | WARNING | `collection`, `status_code` |
| `quite_admin.validation_failed` | DEBUG | `collection`, `status_code` |
| `quite_admin.permission_denied` | WARNING | `collection`, `operation`, `status_code` |
| `quite_admin.csrf_rejected` | WARNING | `status_code` |

Metadata supplied by the library excludes credentials, identities, tokens, cookies, headers, URLs,
query strings, record keys, field values and raw exception messages.
Additional application-bound logging context remains under your control.
Mutation events are emitted after the adapter successfully commits.
They are diagnostic events, not a durable audit log.

The admin adds no per-request access log and does not catch or log unhandled application
exceptions a second time; they propagate to the host/server error pipeline.
If a custom sink or processor raises, a best-effort `quite_admin.logging_failed` warning
goes to the default stdlib logger with only `event_name` and `error_type`.
A sink failure does not change the HTTP result or roll back a committed write.

## Tested compatibility

Tests cover Uvicorn's formatter, Litestar `LoggingConfig` and its real queue listener,
`LoggerAdapter`, `StructlogPlugin` JSON output, Loguru, context propagation, body-reading
middleware, sensitive-data exclusion and sink failures.
The optional picologging test runs in a separate Python 3.12 CI job using
`uv sync --locked --group logging-check`. The normal Python 3.11–3.15 matrix does not
require picologging or imply its binary-extension support for every Python/platform combination.
