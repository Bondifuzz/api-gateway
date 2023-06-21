from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import Any, Optional, Set, Union

from starlette.status import *
from api_gateway.app.api.models.integrations import (
    AnotherIntegrationConfigResponseModel,
    CreateIntegrationRequestModel,
    IntegrationResponseModel,
    JiraIntegrationConfigResponseModel,
    ListIntegrationsResponseModel,
    UpdateIntegrationConfigRequestModel,
    UpdateIntegrationRequestModel,
    YoutrackIntegrationConfigResponseModel,
)

from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBIntegrationNotFoundError
from api_gateway.app.database.orm import (
    ORMIntegration,
    ORMIntegrationStatus,
    ORMIntegrationTypeID,
    ORMUser,
    Paginator,
)
from api_gateway.app.external_api import ExternalAPI
from api_gateway.app.external_api.models import (
    JiraIntegrationModel,
    YoutrackIntegrationModel,
)
from api_gateway.app.utils import gen_unique_identifier
from fastapi import APIRouter, Depends, Path, Query, Response

from ...base import (
    ItemCountResponseModel,
)
from ...constants import *
from ...depends import (
    Operation,
    check_parent_project,
    current_user,
    get_db,
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
    tags=["integrations"],
    prefix="/{project_id}/integrations",
    dependencies=[Depends(check_parent_project)],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.integrations", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.integrations", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.integrations", operation, reason, **kwargs)


########################################
# Create integration
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": IntegrationResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_EXISTS),
        },
    },
)
async def create_bug_tracker_integration(
    response: Response,
    integration: CreateIntegrationRequestModel,
    operation: str = Depends(Operation("Create BTS integration")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration": integration.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    with suppress(DBIntegrationNotFoundError):
        await db.integrations.get_by_name(integration.name, project_id)
        return error_response(HTTP_409_CONFLICT, E_INTEGRATION_EXISTS)

    update_rev = gen_unique_identifier()
    integration_config = integration.config.dict()
    integration_config.update(update_rev=update_rev)

    config_id = None
    if integration.type == ORMIntegrationTypeID.jira:
        config_id = await external_api.jira_reporter.create_integration(
            JiraIntegrationModel.construct(**integration_config)
        )
    elif integration.type == ORMIntegrationTypeID.youtrack:
        config_id = await external_api.yt_reporter.create_integration(
            YoutrackIntegrationModel.construct(**integration_config)
        )
    # elif integration.type == ORMIntegrationTypeID.email:
    #     await external_api.jira.create_integration(integration.config)

    assert config_id is not None

    created_integration = await db.integrations.create(
        status=ORMIntegrationStatus.in_progress,
        name=integration.name,
        project_id=project_id,
        config_id=config_id,
        type=integration.type,
        update_rev=update_rev,
        num_undelivered=0,
        last_error=None,
        enabled=True,
    )

    response_data = IntegrationResponseModel(**created_integration.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        integration_id=created_integration.id,
        integration_name=created_integration.name,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Count integrations
########################################


@dataclass
class FilterIntegrationsRequestModel:
    types: Optional[Set[ORMIntegrationTypeID]] = Query(None)
    statuses: Optional[Set[ORMIntegrationStatus]] = Query(None)


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
async def get_count_of_bug_tracker_integrations(
    operation: str = Depends(Operation("Get count of BTS integrations")),
    filters: FilterIntegrationsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    total_cnt = await db.integrations.count(
        project_id=project_id,
        statuses=filters.statuses,
        types=filters.types,
    )
    total_pages = ceil(total_cnt / pg_size)

    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get integration config
########################################


GetIntegrationConfigResponseModel = Union[
    JiraIntegrationConfigResponseModel,
    YoutrackIntegrationConfigResponseModel,
    AnotherIntegrationConfigResponseModel,
]


@router.get(
    path="/{integration_id}/config",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": GetIntegrationConfigResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_NOT_FOUND),
        },
    },
)
async def get_bug_tracker_integration_config(
    response: Response,
    operation: str = Depends(Operation("Get BTS integration config")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    integration_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration_id": integration_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration = await db.integrations.get_by_id(integration_id, project_id)
    except DBIntegrationNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_NOT_FOUND)

    response_data = None
    if integration.type == ORMIntegrationTypeID.jira:
        config = await external_api.jira_reporter.get_integration(integration.config_id)
        response_data = JiraIntegrationConfigResponseModel(**config.dict())
    elif integration.type == ORMIntegrationTypeID.youtrack:
        config = await external_api.yt_reporter.get_integration(integration.config_id)
        response_data = YoutrackIntegrationConfigResponseModel(**config.dict())
    # else:

    assert response_data is not None
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        integration_id=integration.id,
        integration_name=integration.name,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get integration by name
########################################


@router.get(
    path="/lookup",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": IntegrationResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_NOT_FOUND),
        },
    },
)
async def get_bug_tracker_integration_by_name(
    response: Response,
    operation: str = Depends(Operation("Get BTS integration by name")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    name: str = Query(...),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration_name": name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration = await db.integrations.get_by_name(name, project_id)
    except DBIntegrationNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_NOT_FOUND)

    response_data = IntegrationResponseModel(**integration.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        integration_id=integration.id,
        integration_name=integration.name,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get integration
########################################


@router.get(
    path="/{integration_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": IntegrationResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_NOT_FOUND),
        },
    },
)
async def get_bug_tracker_integration(
    response: Response,
    operation: str = Depends(Operation("Get BTS integration")),
    current_user: ORMUser = Depends(current_user),
    integration_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration_id": integration_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration = await db.integrations.get_by_id(integration_id, project_id)
    except DBIntegrationNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_NOT_FOUND)

    response_data = IntegrationResponseModel(**integration.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        integration_id=integration.id,
        integration_name=integration.name,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Update integration
########################################


@router.patch(
    path="/{integration_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_NOT_FOUND),
        },
    },
)
async def update_bug_tracker_integration(
    response: Response,
    integration: UpdateIntegrationRequestModel,
    operation: str = Depends(Operation("Update BTS integration")),
    current_user: ORMUser = Depends(current_user),
    integration_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration_id": integration_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_integration = await db.integrations.get_by_id(integration_id, project_id)
    except DBIntegrationNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_NOT_FOUND)

    if integration.name:
        with suppress(DBIntegrationNotFoundError):
            await db.integrations.get_by_name(integration.name, project_id)
            return error_response(HTTP_409_CONFLICT, E_INTEGRATION_EXISTS)

    new_fields = integration.dict(exclude_unset=True)
    merged = {**old_integration.dict(), **new_fields}
    await db.integrations.update(ORMIntegration(**merged))

    log_operation_success(
        operation=operation,
        integration_id=integration_id,
        integration_name=integration.name,
        project_id=project_id,
        caller=current_user.name,
    )


########################################
# Update integration config
########################################


@router.put(
    path="/{integration_id}/config",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(
                E_INTEGRATION_NOT_FOUND,
                E_INTEGRATION_TYPE_MISMATCH,
            ),
        },
    },
)
async def update_bug_tracker_integration_config(
    response: Response,
    updates: UpdateIntegrationConfigRequestModel,
    operation: str = Depends(Operation("Update BTS integration config")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    integration_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration_id": integration_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration = await db.integrations.get_by_id(integration_id, project_id)
    except DBIntegrationNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_NOT_FOUND)

    if integration.type != updates.type:
        return error_response(
            HTTP_422_UNPROCESSABLE_ENTITY,
            E_INTEGRATION_TYPE_MISMATCH,
        )

    update_rev = gen_unique_identifier()
    integration_config = updates.config.dict()
    integration_config.update(update_rev=update_rev)
    integration_config.update(id=integration.config_id)

    if integration.type == ORMIntegrationTypeID.jira:
        await external_api.jira_reporter.update_integration(
            JiraIntegrationModel.construct(**integration_config)
        )
    elif integration.type == ORMIntegrationTypeID.youtrack:
        await external_api.yt_reporter.update_integration(
            YoutrackIntegrationModel.construct(**integration_config)
        )
    # elif integration.type == ORMIntegrationTypeID.email:
    #    pass

    integration.last_error = None
    integration.update_rev = update_rev
    integration.status = ORMIntegrationStatus.in_progress
    await db.integrations.update(integration)

    log_operation_success(
        operation=operation,
        integration_id=integration.id,
        integration_name=integration.name,
        project_id=project_id,
        caller=current_user.name,
    )


########################################
# Delete integration
########################################


@router.delete(
    path="/{integration_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response. Object deleted",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_INTEGRATION_NOT_FOUND),
        },
    },
)
async def delete_integration(
    response: Response,
    operation: str = Depends(Operation("Delete integration")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    integration_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "integration_id": integration_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        integration = await db.integrations.get_by_id(integration_id, project_id)
    except DBIntegrationNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_INTEGRATION_NOT_FOUND)

    # First, delete from db to disable notifications
    await db.integrations.delete(integration)

    # Then, delete record from jira reporter
    if integration.type == ORMIntegrationTypeID.jira:
        await external_api.jira_reporter.delete_integration(integration.config_id)
    elif integration.type == ORMIntegrationTypeID.youtrack:
        await external_api.yt_reporter.delete_integration(integration.config_id)
    # else:
    #   ...

    log_operation_success(
        operation=operation,
        integration_id=integration.id,
        integration_name=integration.name,
        project_id=project_id,
        caller=current_user.name,
    )


########################################
# List integrations
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListIntegrationsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_integrations(
    operation: str = Depends(Operation("List integrations")),
    filters: FilterIntegrationsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    integrations = await db.integrations.list(
        project_id=project_id,
        paginator=Paginator(pg_num, pg_size),
        statuses=filters.statuses,
        types=filters.types,
    )

    response_data = ListIntegrationsResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=integrations
    )

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data
