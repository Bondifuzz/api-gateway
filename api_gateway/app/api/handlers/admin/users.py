from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import Any, Optional

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, Path, Query, Response
from mqtransport import MQApp
from starlette.status import *

from api_gateway.app.api.handlers.user.projects import stop_all_revisions_internal
from api_gateway.app.api.models.users import (
    AdminUpdateUserRequestModel,
    CreateUserRequestModel,
    ListUsersResponseModel,
    UserResponseModel,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBUserNotFoundError
from api_gateway.app.database.orm import ORMUser, Paginator
from api_gateway.app.settings import AppSettings
from api_gateway.app.utils import (
    datetime_utcnow,
    rfc3339_add,
    rfc3339_expired,
    rfc3339_now,
)

from ...base import DeleteActions, ItemCountResponseModel, UserObjectRemovalState
from ...constants import *
from ...depends import Operation, current_admin, get_db, get_mq, get_settings
from ...error_codes import *
from ...error_model import ErrorModel, error_model, error_msg
from ...utils import (
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
    pg_num_settings,
    pg_size_settings,
)

router = APIRouter(
    prefix="/users",
    tags=["users (admin)"],
    responses={
        HTTP_401_UNAUTHORIZED: {
            "model": ErrorModel,
            "description": error_msg(E_AUTHORIZATION_REQUIRED),
        },
        HTTP_403_FORBIDDEN: {
            "model": ErrorModel,
            "description": error_msg(E_ADMIN_REQUIRED, E_ACCESS_DENIED),
        },
    },
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.users", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.users", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.users", operation, reason, **kwargs)


########################################
# Create user
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": UserResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_USER_EXISTS),
        },
    },
)
async def create_user(
    response: Response,
    user: CreateUserRequestModel,
    operation: str = Depends(Operation("Create create_user")),
    current_admin: ORMUser = Depends(current_admin),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        rfail = error_model(error_code)
        kw = {"to_create": user.name, "is_admin": user.is_admin}
        log_operation_error(operation, rfail, caller=current_admin.name, **kw)
        response.status_code = status_code
        return rfail

    if user.is_admin:
        if not current_admin.is_system:
            return error_response(HTTP_403_FORBIDDEN, E_ACCESS_DENIED)

    with suppress(DBUserNotFoundError):
        await db.users.get_by_name(user.name)
        return error_response(HTTP_409_CONFLICT, E_USER_EXISTS)

    ph = PasswordHasher()

    created_user = await db.users.create(
        name=user.name,
        display_name=user.display_name,
        password_hash=ph.hash(user.password),
        is_confirmed=True,
        is_disabled=False,
        is_admin=user.is_admin,
        is_system=False,
        email=user.email,
    )

    response_data = UserResponseModel(**created_user.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        user_id=created_user.id,
        username=created_user.name,
        is_admin=created_user.is_admin,
        caller=current_admin.name,
    )

    return response_data


########################################
# List users
########################################


@dataclass
class FilterUsersRequestModel:
    removal_state: Optional[UserObjectRemovalState] = Query(None)


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListUsersResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_users(
    operation: str = Depends(Operation("List users")),
    current_admin: ORMUser = Depends(current_admin),
    filters: FilterUsersRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    users = await db.users.list(
        paginator=Paginator(pg_num, pg_size),
        removal_state=filters.removal_state.to_internal(),
    )

    response_data = ListUsersResponseModel(
        pg_num=pg_num,
        pg_size=pg_size,
        items=users,
    )

    dbg_info = [filters]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        caller=current_admin.name,
    )

    return response_data


########################################
# Count users
########################################


@router.get(
    path="/count",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
)
async def get_user_count(
    operation: str = Depends(Operation("Get user count")),
    current_admin: ORMUser = Depends(current_admin),
    filters: FilterUsersRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    total_cnt = await db.users.count(
        removal_state=filters.removal_state.to_internal(),
    )
    total_pages = ceil(total_cnt / pg_size)

    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    dbg_info = [filters, response_data]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        caller=current_admin.name,
    )

    return response_data


########################################
# Get user by name
########################################


@router.get(
    path="/lookup",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": UserResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_USER_NOT_FOUND),
        },
    },
)
async def get_user_by_name(
    response: Response,
    operation: str = Depends(Operation("Get user by name")),
    current_admin: ORMUser = Depends(current_admin),
    db: IDatabase = Depends(get_db),
    name: str = Query(...),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "user_name": name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        user = await db.users.get_by_name(name)
    except DBUserNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)

    response_data = UserResponseModel(**user.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        user_name=name,
        caller=current_admin.name,
    )

    return response_data


########################################
# Get user
########################################


@router.get(
    path="/{user_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": UserResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_USER_NOT_FOUND),
        },
    },
)
async def get_user(
    response: Response,
    operation: str = Depends(Operation("Get user")),
    current_admin: ORMUser = Depends(current_admin),
    user_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "user_id": user_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        user = await db.users.get_by_id(user_id)
    except DBUserNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)

    response_data = UserResponseModel(**user.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        user_id=user_id,
        caller=current_admin.name,
    )

    return response_data


########################################
# Update user
########################################


@router.patch(
    path="/{user_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_USER_NOT_FOUND),
        },
    },
)
async def update_user(
    response: Response,
    user: AdminUpdateUserRequestModel,
    operation: str = Depends(Operation("Update user")),
    current_admin: ORMUser = Depends(current_admin),
    user_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "user_id": user_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_user = await db.users.get_by_id(user_id)
    except DBUserNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)

    if old_user.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_USER_DELETED)

    if old_user.is_admin:  # Modify admin user
        if old_user.id != current_admin.id:  # Not self
            if not current_admin.is_system:  # Not root
                return error_response(HTTP_403_FORBIDDEN, E_ACCESS_DENIED)

    if user.name is not None:
        with suppress(DBUserNotFoundError):
            await db.users.get_by_name(user.name)
            return error_response(HTTP_409_CONFLICT, E_USER_EXISTS)

    new_fields = user.dict(exclude_unset=True)
    merged = {**old_user.dict(), **new_fields}

    if user.password:
        ph = PasswordHasher()
        merged.update(password_hash=ph.hash(user.password))
        merged.pop("password")

    await db.users.update(ORMUser.construct(**merged))

    log_operation_success(
        operation=operation,
        user_id=user_id,
        caller=current_admin.name,
    )


########################################
# Delete user
########################################


@router.delete(
    path="/{user_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_USER_NOT_FOUND),
        },
    },
)
async def delete_user(
    response: Response,
    operation: str = Depends(Operation("Delete user")),
    current_admin: ORMUser = Depends(current_admin),
    settings: AppSettings = Depends(get_settings),
    user_id: str = Path(..., regex=r"^\d+$"),
    action: DeleteActions = Query(...),
    no_backup: bool = Query(False),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "action": action}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_admin.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        user = await db.users.get_by_id(user_id)
    except DBUserNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)

    if user.erasure_date and rfc3339_expired(user.erasure_date):
        return error_response(HTTP_409_CONFLICT, E_USER_BEING_ERASED)

    if action == DeleteActions.restore:
        if user.erasure_date is None:
            return error_response(HTTP_409_CONFLICT, E_USER_NOT_DELETED)

        user.erasure_date = None
        await db.users.update(user)

    else:
        if user.erasure_date and action == DeleteActions.delete:
            # already in trashbin
            return error_response(HTTP_409_CONFLICT, E_USER_DELETED)

        if user.is_system:  # System users can't be deleted
            return error_response(HTTP_403_FORBIDDEN, E_ACCESS_DENIED)

        if user.is_admin:  # Delete admin user
            if user.id != current_admin.id:  # Not self
                if not current_admin.is_system:  # Not root
                    return error_response(HTTP_403_FORBIDDEN, E_ACCESS_DENIED)

        #
        # Stop running revisions in user projects
        #

        async for project in await db.projects.list_internal(user_id):
            await stop_all_revisions_internal(project, db, mq)

        user.no_backup = no_backup
        if action == DeleteActions.delete:
            exp_seconds = settings.trashbin.expiration_seconds
            user.erasure_date = rfc3339_add(datetime_utcnow(), exp_seconds)
        else:
            user.erasure_date = rfc3339_now()

        await db.users.update(user)

    log_operation_success(operation, user_id=user_id, caller=current_admin.name)
