from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, Query, Response
from starlette.status import *

from api_gateway.app.api.models.integration_types import (
    CreateIntegrationTypeRequestModel,
    IntegrationTypeResponseModel,
    ListIntegrationTypesResponseModel,
    UpdateIntegrationTypeRequestModel,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import (
    DBIntegrationTypeAlreadyExistsError,
    DBIntegrationTypeNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMIntegrationType,
    ORMIntegrationTypeID,
    ORMUser,
    Paginator,
)

from ...constants import *
from ...depends import Operation, current_admin, get_db
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
    prefix="/integration_types",
    tags=["integration types (admin)"],
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
    log_operation_debug_info_to("api.integration_types", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.integration_types", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.integration_types", operation, reason, **kwargs)


########################################
# Create integration type
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": IntegrationTypeResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_TYPE_EXISTS),
        },
    },
)
async def create_integration_type(
    response: Response,
    integration_type: CreateIntegrationTypeRequestModel,
    operation: str = Depends(Operation("Create integration type")),
    current_admin: ORMUser = Depends(current_admin),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"integration_type_id": integration_type.id, "caller": current_admin.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        created_integration_type = await db.integration_types.create(
            id=integration_type.id,
            display_name=integration_type.display_name,
            twoway=integration_type.twoway,
        )
    except DBIntegrationTypeAlreadyExistsError:
        return error_response(HTTP_409_CONFLICT, E_INTEGRATION_TYPE_EXISTS)

    response_data = IntegrationTypeResponseModel(**created_integration_type.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        integration_type_id=created_integration_type.id,
        integration_type_display_name=created_integration_type.display_name,
        caller=current_admin.name,
    )

    return response_data


########################################
# Get integration type
########################################


@router.get(
    path="/{integration_type_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": IntegrationTypeResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_TYPE_NOT_FOUND),
        },
    },
)
async def get_integration_type(
    response: Response,
    operation: str = Depends(Operation("Get integration type")),
    current_admin: ORMUser = Depends(current_admin),
    integration_type_id: ORMIntegrationTypeID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "integration_type_id": integration_type_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration_type = await db.integration_types.get_by_id(integration_type_id)
    except DBIntegrationTypeNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_TYPE_NOT_FOUND)

    response_data = IntegrationTypeResponseModel(**integration_type.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        integration_type_id=integration_type_id,
        caller=current_admin.name,
    )

    return response_data


########################################
# Update integration type
########################################


@router.patch(
    path="/{integration_type_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_TYPE_NOT_FOUND),
        },
    },
)
async def update_integration_type(
    response: Response,
    integration_type: UpdateIntegrationTypeRequestModel,
    operation: str = Depends(Operation("Update integration type")),
    current_admin: ORMUser = Depends(current_admin),
    integration_type_id: ORMIntegrationTypeID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "integration_type_id": integration_type_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_integration_type = await db.integration_types.get_by_id(integration_type_id)
    except DBIntegrationTypeNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_TYPE_NOT_FOUND)

    new_fields = integration_type.dict(exclude_unset=True)
    merged = {**old_integration_type.dict(), **new_fields}
    await db.integration_types.update(ORMIntegrationType(**merged))

    log_operation_success(
        operation=operation,
        integration_type_id=integration_type_id,
        caller=current_admin.name,
    )


########################################
# Delete integration type
########################################


@router.delete(
    path="/{integration_type_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_TYPE_NOT_FOUND),
        },
    },
)
async def delete_integration_type(
    response: Response,
    operation: str = Depends(Operation("Delete integration type")),
    current_admin: ORMUser = Depends(current_admin),
    integration_type_id: ORMIntegrationTypeID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(
        status_code: int, error_code: int, params: Optional[list] = None
    ):
        kw = {"caller": current_admin.name, "integration_type_id": integration_type_id}
        rfail = error_model(error_code, params)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration_type = await db.integration_types.get_by_id(integration_type_id)

    except DBIntegrationTypeNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_TYPE_NOT_FOUND)

    affected_integrations = await db.integrations.list(
        types={integration_type.id},
    )

    if len(affected_integrations) > 0:
        return error_response(
            HTTP_409_CONFLICT, E_INTEGRATION_TYPE_IN_USE_BY, affected_integrations
        )

    await db.integration_types.delete(integration_type)

    log_operation_success(
        operation=operation,
        integration_type_id=integration_type_id,
        caller=current_admin.name,
    )


########################################
# List integration types
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListIntegrationTypesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_integration_types(
    operation: str = Depends(Operation("List integration types")),
    current_admin: ORMUser = Depends(current_admin),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    integration_types = await db.integration_types.list(
        paginator=Paginator(pg_num, pg_size),
    )

    response_data = ListIntegrationTypesResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=integration_types
    )

    log_operation_success(operation, caller=current_admin.name)

    return response_data
