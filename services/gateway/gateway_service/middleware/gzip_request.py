import gzip
import logging
import typing

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class GzipRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_encoding = headers.get(b"content-encoding", b"").lower()

        if content_encoding != b"gzip":
            await self.app(scope, receive, send)
            return

        chunks: typing.List[bytes] = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break

        compressed = b"".join(chunks)
        try:
            decompressed = gzip.decompress(compressed)
        except Exception:
            response_body = b'{"detail":"Invalid gzip body"}'
            await send({
                "type": "http.response.start",
                "status": 400,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response_body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": response_body})
            return

        new_headers = [
            (k, v)
            for k, v in scope["headers"]
            if k.lower() not in (b"content-encoding", b"content-length")
        ]
        new_headers.append((b"content-length", str(len(decompressed)).encode()))

        new_scope = dict(scope)
        new_scope["headers"] = new_headers

        body_sent = False

        async def decompressed_receive() -> dict:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": decompressed, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(new_scope, decompressed_receive, send)
