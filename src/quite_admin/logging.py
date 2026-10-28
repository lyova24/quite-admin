"""Application-owned logging; no global configuration or framework dependencies."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Literal, Protocol

default_logger = logging.getLogger("quite_admin")
default_logger.addHandler(logging.NullHandler())


class LoggerProtocol(Protocol):
    """Stdlib / picologging style, or structured keyword fields with log_structured=True.

    Methods may also return awaitables. Handlers, processors, queues and context
    enrichment belong to the application.
    """

    def debug(self, event: str, **kwargs: Any) -> Any: ...
    def info(self, event: str, **kwargs: Any) -> Any: ...
    def warning(self, event: str, **kwargs: Any) -> Any: ...


class EventLogger:
    def __init__(self, logger: LoggerProtocol | None, *, structured: bool) -> None:
        if structured and logger is None:
            raise ValueError("log_structured=True requires an explicit structured logger.")
        if structured and isinstance(logger, (logging.Logger, logging.LoggerAdapter)):
            raise ValueError("Use log_structured=False with a standard logging logger.")
        self.logger = logger if logger is not None else default_logger
        self.structured = structured

    async def emit(
        self, level: Literal["debug", "info", "warning"], event: str, **metadata: Any
    ) -> None:
        # Only explicitly supplied metadata: no request bodies, credentials, cookies,
        # URLs, query strings, primary keys, record values or raw exception messages.
        kwargs = metadata if self.structured else {"extra": {"quite_admin": metadata}}
        try:
            logger = self.logger
            # LoggerAdapter can discard caller extra (merge_extra is opt-in on
            # newer Python). Preserve both its public process hook and fields.
            while not self.structured and isinstance(logger, logging.LoggerAdapter):
                previous_extra = kwargs["extra"]
                event, kwargs = logger.process(event, kwargs)
                kwargs["extra"] = {
                    **previous_extra,
                    **kwargs.get("extra", {}),
                    "quite_admin": metadata,
                }
                logger = logger.logger
            result = getattr(logger, level)(event, **kwargs)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            # A failed sink must not turn a committed write into a failed request.
            try:
                default_logger.warning(
                    "quite_admin.logging_failed",
                    extra={
                        "quite_admin": {
                            "event_name": event,
                            "error_type": type(exc).__name__,
                        }
                    },
                )
            except Exception:
                pass
