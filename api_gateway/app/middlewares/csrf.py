from typing import Callable

from starlette.status import *

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..api.depends import get_csrf_token_mgr, get_settings
from ..api.error_codes import *
from ..api.error_model import error_body
from ..api.handlers.security.csrf import CSRFTokenInvalid


async def csrf_protection_middleware(request: Request, call_next: Callable):
    def error_response(status_code: int, error_code: str):
        return JSONResponse(error_body(error_code), status_code)

    path = request.url.path
    app: FastAPI = request.app
    mgr = get_csrf_token_mgr(request)

    if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
        return await call_next(request)

    if path == app.url_path_for("login"):
        return await call_next(request)

    if path == app.url_path_for("refresh_csrf_token"):
        return await call_next(request)

    csrf_token1 = request.headers.get("X-CSRF-TOKEN")
    csrf_token2 = request.cookies.get("CSRF_TOKEN")
    user_id = request.cookies.get("USER_ID")

    if user_id is None:
        return error_response(HTTP_401_UNAUTHORIZED, E_AUTHORIZATION_REQUIRED)

    if csrf_token1 is None or csrf_token2 is None:
        return error_response(HTTP_403_FORBIDDEN, E_CSRF_TOKEN_MISSING)

    if csrf_token1 != csrf_token2:
        return error_response(HTTP_403_FORBIDDEN, E_CSRF_TOKEN_MISMATCH)

    try:
        parsed_token = mgr.parse_csrf_token(csrf_token1)
    except CSRFTokenInvalid:
        return error_response(HTTP_403_FORBIDDEN, E_CSRF_TOKEN_INVALID)

    if parsed_token.user_id != user_id:
        return error_response(HTTP_403_FORBIDDEN, E_CSRF_TOKEN_USER_MISMATCH)

    return await call_next(request)
