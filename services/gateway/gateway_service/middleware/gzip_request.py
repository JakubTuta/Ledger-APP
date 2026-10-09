import json
import zlib

from gateway_service import config
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLargeError(Exception):
    pass


class GzipRequestMiddleware:
    """Caps request body size and inflates gzip-encoded bodies (OTLP exporters).

    Registered inside AuthMiddleware, so only requests that already passed
    authentication are buffered or inflated. Both the bytes on the wire and the
    inflated size are capped: gzip shrinks repetitive input by roughly 1000:1,
    so inflating a small upload without a bound can exhaust the worker's memory.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = config.settings.MAX_REQUEST_BODY_BYTES
        headers = dict(scope.get("headers", []))
        declared_length = headers.get(b"content-length", b"")
        if declared_length.isdigit() and int(declared_length) > max_bytes:
            await _send_error(send, 413, "Request body too large")
            return

        if headers.get(b"content-encoding", b"").lower() != b"gzip":
            await self._call_with_limited_body(scope, receive, send, max_bytes)
            return

        try:
            compressed = await _read_body(receive, max_bytes)
            decompressed = _inflate_gzip(compressed, max_bytes)
        except RequestBodyTooLargeError:
            await _send_error(send, 413, "Request body too large")
            return
        except (zlib.error, ValueError):
            await _send_error(send, 400, "Invalid gzip body")
            return

        new_headers = [
            (k, v)
            for k, v in scope["headers"]
            if k.lower() not in (b"content-encoding", b"content-length")
        ]
        new_headers.append((b"content-length", str(len(decompressed)).encode()))

        body_sent = False

        async def decompressed_receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": decompressed, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app({**scope, "headers": new_headers}, decompressed_receive, send)

    async def _call_with_limited_body(
        self, scope: Scope, receive: Receive, send: Send, max_bytes: int
    ) -> None:
        """Pass the body through untouched, but stop a chunked upload at the cap."""
        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    raise RequestBodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLargeError:
            if not response_started:
                await _send_error(send, 413, "Request body too large")


async def _read_body(receive: Receive, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > max_bytes:
            raise RequestBodyTooLargeError
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _inflate_gzip(compressed: bytes, max_bytes: int) -> bytes:
    """Inflate every gzip member in `compressed`, refusing to produce more than max_bytes."""
    output = bytearray()
    remaining = compressed
    while remaining:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        output += decompressor.decompress(remaining, max_bytes + 1 - len(output))
        if len(output) > max_bytes or decompressor.unconsumed_tail:
            raise RequestBodyTooLargeError
        if not decompressor.eof:
            raise ValueError("truncated gzip stream")
        remaining = decompressor.unused_data
    return bytes(output)


async def _send_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
