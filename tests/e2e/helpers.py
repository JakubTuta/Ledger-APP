import asyncio
import time
import typing


async def poll_until(
    predicate: typing.Callable[[], typing.Awaitable[bool]],
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str = "condition",
) -> None:
    """Poll `predicate` until it returns truthy or `timeout` seconds elapse.

    Used throughout the E2E suite to wait on asynchronous pipeline effects
    (worker drain, alert evaluator cron ticks, monitor checker cron ticks)
    that have no synchronous completion signal from the gateway's REST API.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            if await predicate():
                return
            last_error = None
        except Exception as e:
            last_error = e
        await asyncio.sleep(interval)

    if last_error is not None:
        raise TimeoutError(f"Timed out waiting for {description}: {last_error}") from last_error
    raise TimeoutError(f"Timed out waiting for {description}")
