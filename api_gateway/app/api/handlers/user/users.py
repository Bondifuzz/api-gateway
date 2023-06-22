from contextlib import suppress
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, Response
from starlette.status import *

from api_gateway.app.api.constants import *
from api_gateway.app.api.error_codes import *
from api_gateway.app.api.error_model import error_model, error_msg
from api_gateway.app.api.models.users import UpdateUserRequestModel, UserResponseModel
from api_gateway.app.api.utils import (
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBUserNotFoundError
from api_gateway.app.database.orm import ORMUser

from ...depends import Operation, current_user, get_db
from ...error_model import ErrorModel

router = APIRouter(
    tags=["users"],
    prefix="/users",
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.users", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.users", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.users", operation, reason, **kwargs)


########################################
# Get self user
########################################


@router.get(
    path="/self",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": UserResponseModel,
            "description": "Successful response",
        },
        HTTP_401_UNAUTHORIZED: {
            "model": ErrorModel,
            "description": error_msg(E_SESSION_NOT_FOUND),
        },
    },
)
async def get_self_user(
    operation: str = Depends(Operation("Get self user")),
    user: ORMUser = Depends(current_user),
):

    response_data = UserResponseModel(**user.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        user_id=user.id,
        user_name=user.name,
    )

    return response_data


@router.patch(
    path="/self",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(
                E_WRONG_PASSWORD,
                E_USER_EXISTS,
            ),
        },
    },
)
async def update_self_user(
    response: Response,
    user: UpdateUserRequestModel,
    operation: str = Depends(Operation("Update self user")),
    old_user: ORMUser = Depends(current_user),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": old_user.name, "user_id": old_user.id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    if user.name is not None:
        with suppress(DBUserNotFoundError):
            await db.users.get_by_name(user.name)
            return error_response(HTTP_409_CONFLICT, E_USER_EXISTS)

    new_fields = user.dict(
        exclude_unset=True, exclude={"current_password", "new_password"}
    )
    merged = {**old_user.dict(), **new_fields}

    if user.new_password:
        try:
            ph = PasswordHasher()
            ph.verify(old_user.password_hash, user.current_password)
        except (AttributeError, VerificationError):
            return error_response(HTTP_409_CONFLICT, E_WRONG_PASSWORD)

        merged.update(password_hash=ph.hash(user.new_password))

    await db.users.update(ORMUser.construct(**merged))

    log_operation_success(
        operation=operation,
        user_id=old_user.id,
        caller=old_user.name,
    )
