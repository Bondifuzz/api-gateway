import asyncio
import random
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from pydantic import Field
from starlette.status import *

from api_gateway.app.api.handlers.auth.device_cookie import DeviceCookieManager
from api_gateway.app.api.handlers.security.csrf import CSRFTokenManager
from api_gateway.app.background.tasks.user_lockout import FailedLoginCounter
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBCookieNotFoundError, DBUserNotFoundError
from api_gateway.app.database.orm import ORMDeviceCookie
from api_gateway.app.settings import AppSettings
from fastapi import APIRouter, Depends, Response

from ...base import BaseModel
from ...constants import *
from ...depends import (
    CookieHelper,
    Operation,
    get_csrf_token_mgr,
    get_db,
    get_device_cookie_mgr,
    get_login_counter,
    get_settings,
)
from ...error_codes import *
from ...error_model import ErrorModel, error_model, error_msg
from ...utils import (
    check_user_status,
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
    max_length,
)
from .device_cookie import DeviceCookieManager, InvalidDeviceCookie

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.auth", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.auth", operation, **kwargs)


def log_operation_error(operation: str, reason: ErrorModel, **kwargs):
    log_operation_error_to("api.auth", operation, reason, **kwargs)


class LoginRequestModel(BaseModel):
    username: str = Field(..., **max_length(C_MAX_USERNAME_LENGTH))
    password: str = Field(..., **max_length(C_MAX_PASSWORD_LENGTH))
    session_metadata: str = Field(..., **max_length(C_MAX_SESSION_META_LENGTH))


class LoginResponseModel(BaseModel):
    user_id: str
    user_name: str
    display_name: str
    is_admin: bool


@router.post(
    path="/login",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": LoginResponseModel,
            "description": "Successful response",
        },
        HTTP_401_UNAUTHORIZED: {
            "model": ErrorModel,
            "description": error_msg(E_AUTHORIZATION_REQUIRED, E_SESSION_NOT_FOUND),
        },
        HTTP_403_FORBIDDEN: {
            "model": ErrorModel,
            "description": error_msg(E_ACCOUNT_DISABLED, E_ACCOUNT_NOT_CONFIRMED),
        },
    },
)
async def login(
    response: Response,
    login: LoginRequestModel,
    operation: str = Depends(Operation("Login")),
    device_cookie_jwt: Optional[str] = CookieHelper("DEVICE_COOKIE", optional=True),
    login_counter: FailedLoginCounter = Depends(get_login_counter),
    dc_mgr: DeviceCookieManager = Depends(get_device_cookie_mgr),
    ct_mgr: CSRFTokenManager = Depends(get_csrf_token_mgr),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, username=login.username)
        response.status_code = status_code
        return rfail

    #
    # Verify device cookie, if present.
    # If there's no device cookie, then create
    # a pseudo cookie for untrusted clients.
    # Convert parsed device cookie to ORM object
    #

    try:
        parsed_dc = dc_mgr.ensure_device_cookie(login.username, device_cookie_jwt)
        device_cookie = ORMDeviceCookie(**parsed_dc.dict())
    except InvalidDeviceCookie:
        return error_response(HTTP_403_FORBIDDEN, E_DEVICE_COOKIE_INVALID)

    # Common technique against timing attacks
    await asyncio.sleep(random.uniform(0.1, 1.0))

    #
    # Check current device cookie is not in the lockout list
    # - First check: use `login_counter` as in-memory cache.
    #   Cache contains login attempts for both existing and
    #   non-existing users to prevent user account discovery
    # - Second check: use database for lookup. Lockout list
    #   is stored in database and contains only existing users.
    #   This storage is permanent and can survive service restarts
    #

    if login_counter.is_limit_reached(device_cookie):
        return error_response(HTTP_403_FORBIDDEN, E_DEVICE_COOKIE_LOCKOUT)

    try:
        user = await db.users.get_by_name(login.username)
    except DBUserNotFoundError:
        login_counter.add_failed_login(device_cookie)
        return error_response(HTTP_401_UNAUTHORIZED, E_LOGIN_FAILED)

    if await db.lockout.has(device_cookie):
        return error_response(HTTP_403_FORBIDDEN, E_DEVICE_COOKIE_LOCKOUT)

    #
    # Proceed with password verification
    #

    try:
        ph = PasswordHasher()
        ph.verify(user.password_hash, login.password)

    except VerificationError:
        login_counter.add_failed_login(device_cookie)
        if login_counter.is_limit_reached(device_cookie):
            exp_seconds = settings.bfp.lockout_period_sec
            await db.lockout.add(device_cookie, exp_seconds)

        return error_response(HTTP_401_UNAUTHORIZED, E_LOGIN_FAILED)

    #
    # User can be disabled, deleted, e.t.c
    # Check user status before continue
    #

    status_code, error_code = check_user_status(user)
    if error_code != E_NO_ERROR:
        return error_response(status_code, error_code)

    #
    # Login successful
    # Set cookies and issue new device cookie
    #

    meta = login.session_metadata
    is_secure = settings.cookies.mode_secure
    exp_seconds = settings.cookies.expiration_seconds
    cookie = await db.cookies.create(user.id, meta, exp_seconds)
    new_device_cookie = dc_mgr.create_device_cookie(login.username)

    response.set_cookie(
        key="SESSION_ID",
        value=cookie.id,
        secure=is_secure,
        expires=exp_seconds,
        httponly=True,
    )

    response.set_cookie(
        key="USER_ID",
        value=cookie.user_id,
        secure=is_secure,
        expires=exp_seconds,
        httponly=True,
    )

    response.set_cookie(
        key="DEVICE_COOKIE",
        value=new_device_cookie,
        secure=is_secure,
        expires=2147483647,  # never expire
        httponly=True,
    )

    #
    # CSRF Protection (Double submit cookie)
    #

    if settings.csrf_protection.enabled:
        exp_seconds = settings.csrf_protection.token_exp_seconds
        csrf_token = ct_mgr.create_csrf_token(cookie.user_id)
        response.headers["X-CSRF-TOKEN"] = csrf_token

        response.set_cookie(
            key="CSRF_TOKEN",
            value=csrf_token,
            secure=is_secure,
            expires=exp_seconds,
            httponly=True,
        )

    response_data = LoginResponseModel(
        **user.dict(),
        user_id=user.id,
        user_name=user.name,
    )

    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        user_id=user.id,
        user_name=user.name,
        is_admin=user.is_admin,
    )

    return response_data


@router.post(
    path="/logout",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_SESSION_NOT_FOUND),
        },
    },
)
async def logout(
    response: Response,
    operation: str = Depends(Operation("Logout")),
    session_id: str = CookieHelper("SESSION_ID"),
    user_id: str = CookieHelper("USER_ID"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, session=session_id, user_id=user_id)
        response.status_code = status_code
        return rfail

    try:
        cookie = await db.cookies.get(session_id, user_id)
    except DBCookieNotFoundError:
        return error_response(HTTP_401_UNAUTHORIZED, E_SESSION_NOT_FOUND)

    await db.cookies.delete(cookie)

    response.delete_cookie("CSRF_TOKEN")
    response.delete_cookie("SESSION_ID")
    response.delete_cookie("USER_ID")

    log_operation_success(operation, session=session_id, user_id=user_id)
