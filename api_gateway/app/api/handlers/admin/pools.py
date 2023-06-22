from dataclasses import dataclass
from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, Path, Query, Response
from starlette.status import *

from api_gateway.app.api.models.pools import (
    AdminUpdatePoolInfoRequestModel,
    CloudNodeGroupModel,
    CreatePoolRequestModel,
    ListPoolsResponseModel,
    LocalNodeGroupModel,
    PoolResponseModel,
)
from api_gateway.app.database.orm import ORMUser
from api_gateway.app.external_api.errors import EAPIServerError
from api_gateway.app.external_api.external_api import ExternalAPI
from api_gateway.app.settings import AppSettings, PlatformType

from ...base import ItemCountResponseModel
from ...constants import *
from ...depends import Operation, current_user, get_external_api, get_settings
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
    prefix="/pools",
    tags=["pools (admin)"],
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
    log_operation_debug_info_to("api.admin_pools", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.admin_pools", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.admin_pools", operation, reason, **kwargs)


def is_valid_node_group(settings: AppSettings, node_group) -> bool:
    platform_type = settings.environment.platform_type
    if platform_type == PlatformType.cloud:
        return isinstance(node_group, CloudNodeGroupModel)
    elif platform_type in {PlatformType.demo, PlatformType.onprem}:
        return isinstance(node_group, LocalNodeGroupModel)

    raise NotImplementedError(f"Unknown platform_type: {platform_type}")


########################################
# Create pool
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": PoolResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_PROJECT_EXISTS),
        },
    },
)
async def admin_create_pool(
    response: Response,
    request: CreatePoolRequestModel,
    current_user: ORMUser = Depends(current_user),
    operation: str = Depends(Operation("[admin] Create pool")),
    external_api: ExternalAPI = Depends(get_external_api),
    settings: AppSettings = Depends(get_settings),
):
    def error_response(status_code: int, error_code: int):
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name)
        response.status_code = status_code
        return rfail

    if not is_valid_node_group(settings, request.node_group):
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_INVALID_NODE_GROUP)

    try:
        response_data = await external_api.pool_mgr.create_pool(request)

        return response_data

    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )


########################################
# Count pools
########################################


@dataclass
class FilterPoolsRequestModel:
    user_id: Optional[str] = Query(None)


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
async def admin_get_pools_count(
    response: Response,
    filters: FilterPoolsRequestModel = Depends(),
    operation: str = Depends(Operation("[admin] Get pools count")),
    pg_size: int = Query(**pg_size_settings()),
    external_api: ExternalAPI = Depends(get_external_api),
):

    try:
        response_data = await external_api.pool_mgr.count_pools(
            pg_size=pg_size,
            user_id=filters.user_id,
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
            "description": error_msg(E_PROJECT_NOT_FOUND),
        },
    },
)
async def admin_get_pool(
    response: Response,
    pool_id: str = Path(...),
    operation: str = Depends(Operation("[admin] Get pool")),
    external_api: ExternalAPI = Depends(get_external_api),
):

    try:
        response_data = await external_api.pool_mgr.get_pool_by_id(
            id=pool_id,
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
async def admin_update_pool_info(
    response: Response,
    request: AdminUpdatePoolInfoRequestModel,
    pool_id: str = Path(...),
    operation: str = Depends(Operation("Update pool info")),
    external_api: ExternalAPI = Depends(get_external_api),
):
    try:
        await external_api.pool_mgr.update_pool_info(
            id=pool_id,
            body=request,
        )

    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )


########################################
# Update pool node group
########################################


@router.put(
    path="/{pool_id}/node_group",
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
async def admin_update_pool_node_group(
    response: Response,
    node_group: Union[LocalNodeGroupModel, CloudNodeGroupModel],
    pool_id: str = Path(...),
    operation: str = Depends(Operation("Update pool node group")),
    external_api: ExternalAPI = Depends(get_external_api),
    settings: AppSettings = Depends(get_settings),
    current_user: ORMUser = Depends(current_user),
):
    def error_response(status_code: int, error_code: int):
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name)
        response.status_code = status_code
        return rfail

    if not is_valid_node_group(settings, node_group):
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_INVALID_NODE_GROUP)

    try:
        await external_api.pool_mgr.update_pool_node_group(
            id=pool_id,
            node_group=node_group,
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
async def admin_delete_pool(
    response: Response,
    operation: str = Depends(Operation("[admin] Delete pool")),
    external_api: ExternalAPI = Depends(get_external_api),
    pool_id: str = Path(...),
):

    try:
        await external_api.pool_mgr.delete_pool(
            id=pool_id,
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
async def admin_list_pools(
    response: Response,
    operation: str = Depends(Operation("[admin] List pools")),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    filters: FilterPoolsRequestModel = Depends(),
    external_api: ExternalAPI = Depends(get_external_api),
):

    try:
        pools = await external_api.pool_mgr.list_pools(
            pg_size=pg_size,
            pg_num=pg_num,
            user_id=filters.user_id,
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
