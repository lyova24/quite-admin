"""One admin's read budget, including queue and asynchronous pool acquisition."""

import asyncio
import inspect
import math
from contextlib import asynccontextmanager

from anyio import Semaphore, fail_after, to_thread
from anyio.lowlevel import checkpoint_if_cancelled

from .errors import QueryTimeout


def validate_timeout(seconds):
    if seconds is not None and (
        type(seconds) not in {int, float}
        or not math.isfinite(seconds)
        or not 0 < seconds <= 2147483
    ):
        raise ValueError(
            "query_timeout must be a positive finite number of seconds, at most 2147483."
        )
    return seconds


class ReadLimits:
    def __init__(self, query_timeout=None, max_concurrent_reads=None):
        self.timeout = validate_timeout(query_timeout)
        if max_concurrent_reads is not None and (
            type(max_concurrent_reads) is not int or max_concurrent_reads <= 0
        ):
            raise ValueError("max_concurrent_reads must be a positive integer or None.")
        self.slots = Semaphore(max_concurrent_reads) if max_concurrent_reads is not None else None

    async def run(self, operation, *args, **kwargs):
        if self.timeout is None and self.slots is None:
            return await self._call(operation, *args, **kwargs)
        async with deadline(self.timeout):
            if self.slots is None:
                return await self._call(operation, *args, **kwargs)
            async with self.slots:
                return await self._call(operation, *args, **kwargs)

    @staticmethod
    async def _call(operation, *args, **kwargs):
        result = operation(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        # Sync adapters wait for their worker to release its connection before
        # returning. Notice an expired deadline after that shielded cleanup too.
        await checkpoint_if_cancelled()
        return result


@asynccontextmanager
async def deadline(seconds):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Keep the ORM-independent path usable with other AnyIO backends.
        try:
            with fail_after(seconds) as scope:
                yield
        except TimeoutError as exc:
            if scope.cancel_called:
                raise QueryTimeout() from exc
            raise
    else:
        # An edge cancellation lets asyncio database drivers finish their async
        # rollback/close. A repeatedly cancelled AnyIO scope can interrupt cleanup.
        try:
            async with asyncio.timeout(seconds) as timer:
                yield
        except TimeoutError as exc:
            if timer.expired():
                raise QueryTimeout() from exc
            raise


async def run_sync(operation):
    """Never abandon a synchronous database worker, including on asyncio cancellation."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return await to_thread.run_sync(operation)
    task = asyncio.create_task(to_thread.run_sync(operation))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise
