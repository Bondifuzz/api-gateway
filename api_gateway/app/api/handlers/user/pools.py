from typing import Any

from starlette.status import *
from api_gateway.app.api.models.pools import (
    AdminUpdatePoolInfoRequestModel,
    UpdatePoolInfoRequestModel,
    PoolResponseModel,
    ListPoolsResponseModel,
)

from api_gateway.app.database.orm import (
    ORMUser,
)
from api_gateway.app.external_api import ExternalAPI
from api_gateway.app.external_api.errors import EAPIServerError
from fastapi import APIRouter, Depends, Path, Query, Response

from ...base import (
    ItemCountResponseModel,
)
from ...constants import *
from ...depends import (
    Operation,
    check_client_is_not_admin,
    check_user_access_permissions,
    check_user_exists,
    current_user,
    get_external_api,
)
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
    tags=["pools"],
    prefix="/{user_id}/pools",
    dependencies=[
        Depends(check_client_is_not_admin),
        Depends(check_user_access_permissions),
        Depends(check_user_exists),
    ],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.pools", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.pools", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.pools", operation, reason, **kwargs)


########################################
# Count pools
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
async def get_available_pools_count(
    response: Response,
    operation: str = Depends(Operation("Get available pools count")),
    pg_size: int = Query(**pg_size_settings()),
    user_id: str = Path(..., regex=r"^\d+$"),
    external_api: ExternalAPI = Depends(get_external_api),
):
    
    try:
        response_data = await external_api.pool_mgr.count_available_pools(
            pg_size=pg_size,
            user_id=user_id,
        )

        return response_data
    
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )


########################################
# Get pool
########################################


@router.get(
    path="/{pool_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": PoolResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_POOL_NOT_FOUND),
        },
    },
)
async def get_pool(
    response: Response,
    user_id: str = Path(..., regex=r"^\d+$"),
    pool_id: str = Path(...),
    operation: str = Depends(Operation("Get pool")),
    external_api: ExternalAPI = Depends(get_external_api),
):
    
    try:
        response_data = await external_api.pool_mgr.get_pool_by_id(
            id=pool_id,
            user_id=user_id,
        )
        return response_data
    
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )


########################################
# Update pool
########################################


@router.patch(
    path="/{pool_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_POOL_NOT_FOUND),
        },
    },
)
async def update_pool(
    response: Response,
    request: UpdatePoolInfoRequestModel,
    user_id: str = Path(..., regex=r"^\d+$"),
    pool_id: str = Path(...),
    operation: str = Depends(Operation("Update pool")),
    external_api: ExternalAPI = Depends(get_external_api),
):
    try:
        await external_api.pool_mgr.update_pool_info(
            id=pool_id,
            user_id=user_id,
            body=AdminUpdatePoolInfoRequestModel(
                **request.dict(exclude_unset=True)
            )
        )
    
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )


########################################
# Delete pool
########################################


@router.delete(
    path="/{pool_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_POOL_NOT_FOUND),
        },
    },
)
async def delete_pool(
    response: Response,
    operation: str = Depends(Operation("Delete pool")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    pool_id: str = Path(...),
    user_id: str = Path(..., regex=r"^\d+$"),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "pool_id": pool_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    if not current_user.is_admin:
        return error_response(HTTP_403_FORBIDDEN, E_ADMIN_REQUIRED)
    
    try:
        await external_api.pool_mgr.delete_pool(
            id=pool_id,
            user_id=user_id,
        )
    
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )


########################################
# List pools
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListPoolsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_pools(
    response: Response,
    user_id: str = Path(..., regex=r"^\d+$"),
    operation: str = Depends(Operation("List pools")),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    external_api: ExternalAPI = Depends(get_external_api),
):
    
    try:
        pools = await external_api.pool_mgr.list_available_pools(
            user_id=user_id,
            pg_size=pg_size,
            pg_num=pg_num,
        )
        response_data = ListPoolsResponseModel(
            pg_num=pg_num, pg_size=pg_size, items=pools
        )

        return response_data
    
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )
