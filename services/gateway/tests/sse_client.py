import asyncio
import typing

import sse_starlette.sse as sse_starlette_sse


class ASGISSEStream:
    """Drives an ASGI app's SSE endpoint directly instead of through
    httpx.ASGITransport.

    httpx.ASGITransport.handle_async_request awaits the whole ASGI app call
    to completion before it ever constructs a Response, and its receive()
    only ever surfaces "http.disconnect" after the app has already finished
    (response_complete.wait() happens before that message is returned). For
    an endpoint that streams indefinitely (like a live SSE tail, which only
    exits on a real client disconnect) those two conditions can never both
    be satisfied - the transport deadlocks. httpx.Timeout does not help
    either: ASGITransport has no timeout handling of its own, so nothing
    ever interrupts the await.

    This helper reproduces just enough of the ASGI protocol - a real
    request body message followed by a receive() that blocks until the
    test explicitly disconnects - so SSE responses can be read incrementally
    and closed on demand, the way a real client/server socket pair behaves.
    """

    def __init__(self, app: typing.Callable, scope: dict, timeout: float = 5.0):
        self.app = app
        self.scope = scope
        self.timeout = timeout
        self.status_code: int | None = None
        self.headers: list[tuple[bytes, bytes]] = []
        self._body_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._receive_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._response_started = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._buffer = b""

    async def __aenter__(self) -> "ASGISSEStream":
        # sse_starlette.sse.AppStatus.should_exit_event is a module-level
        # anyio.Event that gets bound to whichever event loop first
        # constructs it. pytest-asyncio hands each test function its own
        # loop, so without this reset the second SSE test in a session
        # reuses an Event tied to a closed loop and crashes with
        # "bound to a different event loop".
        sse_starlette_sse.AppStatus.should_exit_event = None
        await self._receive_queue.put({"type": "http.request", "body": b"", "more_body": False})
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._response_started.wait(), timeout=self.timeout)
        return self

    async def _run(self) -> None:
        async def receive() -> dict:
            return await self._receive_queue.get()

        async def send(message: dict) -> None:
            if message["type"] == "http.response.start":
                self.status_code = message["status"]
                self.headers = message.get("headers", [])
                self._response_started.set()
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    await self._body_queue.put(body)
                if not message.get("more_body", False):
                    await self._body_queue.put(None)

        try:
            await self.app(self.scope, receive, send)
        finally:
            await self._body_queue.put(None)

    async def next_event(self) -> dict[str, str]:
        """Read raw SSE bytes until one blank-line-terminated event is assembled."""
        while b"\n\n" not in self._buffer.replace(b"\r\n", b"\n"):
            chunk = await asyncio.wait_for(self._body_queue.get(), timeout=self.timeout)
            if chunk is None:
                raise EOFError("SSE stream ended before a full event was received")
            self._buffer += chunk

        normalized = self._buffer.replace(b"\r\n", b"\n")
        raw_event, _, rest = normalized.partition(b"\n\n")
        self._buffer = rest

        event: dict[str, str] = {}
        for line in raw_event.split(b"\n"):
            if not line or line.startswith(b":"):
                continue
            field, _, value = line.partition(b":")
            if value.startswith(b" "):
                value = value[1:]
            event[field.decode()] = value.decode()
        return event

    async def aclose(self) -> None:
        await self._receive_queue.put({"type": "http.disconnect"})
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.timeout)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


def build_http_scope(
    method: str,
    path: str,
    query_string: bytes = b"",
    headers: dict[str, str] | None = None,
) -> dict:
    raw_headers = [(b"host", b"test")]
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))

    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "headers": raw_headers,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "server": ("test", 80),
        "client": ("127.0.0.1", 123),
        "root_path": "",
    }
