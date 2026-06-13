import gzip
import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class GzipRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.headers.get("Content-Encoding", "").lower() != "gzip":
            return await call_next(request)

        body = await request.body()
        try:
            decompressed = gzip.decompress(body)
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid gzip body"},
            )

        async def receive():
            return {"type": "http.request", "body": decompressed, "more_body": False}

        modified_scope = dict(request.scope)
        modified_scope["headers"] = [
            (k, v) for k, v in request.scope["headers"]
            if k.lower() != b"content-encoding"
        ]
        return await call_next(Request(modified_scope, receive))
