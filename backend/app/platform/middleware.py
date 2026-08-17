"""Request-id middleware: assigns/propagates an X-Request-ID for log correlation."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.platform.logging import set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
