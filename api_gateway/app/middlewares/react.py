from typing import Callable

from fastapi import Request, Response
from fastapi.responses import HTMLResponse


async def react_middleware(request: Request, call_next: Callable):

    response: Response = await call_next(request)
    if response.status_code != 404:
        return response

    path = request.url.path
    if path.startswith("/api") or path.startswith("/docs"):
        return response

    return HTMLResponse(request.app.state.index_html)
