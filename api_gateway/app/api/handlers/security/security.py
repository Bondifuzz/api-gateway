from typing import Any

from fastapi import APIRouter, Depends, Response
from starlette.status import *

from api_gateway.app.database.orm import ORMUser
from api_gateway.app.settings import AppSettings

from ...constants import *
from ...depends import Operation, current_user, get_csrf_token_mgr, get_settings
from ...error_codes import *
from ...error_model import ErrorModel
from ...utils import (
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
)
from .csrf import CSRFTokenManager

router = APIRouter(
    prefix="/security",
    tags=["security"],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.security", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.security", operation, **kwargs)


def log_operation_error(operation: str, reason: ErrorModel, **kwargs):
    log_operation_error_to("api.security", operation, reason, **kwargs)


@router.post(
    path="/csrf-token",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
    },
)
async def refresh_csrf_token(
    response: Response,
    operation: str = Depends(Operation("Logout")),
    current_user: ORMUser = Depends(current_user),
    mgr: CSRFTokenManager = Depends(get_csrf_token_mgr),
    settings: AppSettings = Depends(get_settings),
):
    csrf_token = mgr.create_csrf_token(current_user.id)
    response.headers["X-CSRF-TOKEN"] = csrf_token

    exp_seconds = settings.csrf_protection.token_exp_seconds
    is_secure = settings.cookies.mode_secure

    response.set_cookie(
        key="CSRF_TOKEN",
        value=csrf_token,
        secure=is_secure,
        expires=exp_seconds,
        httponly=True,
    )

    log_operation_success(operation, user_id=current_user.id)
