from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import Any, Optional

from fastapi import APIRouter, Depends, Path, Query, Response
from mqtransport import MQApp
from starlette.status import *

from api_gateway.app.api.models.projects import (
    CreateProjectRequestModel,
    ListProjectsResponseModel,
    ProjectResponseModel,
    UpdateProjectRequestModel,
    UserTrashbinEmptyResponseModel,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBProjectNotFoundError
from api_gateway.app.database.orm import ORMProject, ORMUser, Paginator
from api_gateway.app.external_api import ExternalAPI
from api_gateway.app.external_api.errors import EAPIServerError
from api_gateway.app.message_queue.instance import MQAppState
from api_gateway.app.settings import AppSettings
from api_gateway.app.utils import datetime_utcnow, rfc3339_add, rfc3339_now

from ...base import DeleteActions, ItemCountResponseModel, UserObjectRemovalState
from ...constants import *
from ...depends import (
    Operation,
    check_client_is_not_admin,
    check_user_access_permissions,
    check_user_exists,
    current_user,
    get_db,
    get_external_api,
    get_mq,
    get_settings,
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
    tags=["projects"],
    prefix="/{user_id}/projects",
    dependencies=[
        Depends(check_client_is_not_admin),
        Depends(check_user_access_permissions),
        Depends(check_user_exists),
    ],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.projects", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.projects", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.projects", operation, reason, **kwargs)


async def stop_all_revisions_internal(
    project: ORMProject,
    db: IDatabase,
    mq: MQApp,
):
    mq_state: MQAppState = mq.state
    sch_stop_pool_fuzzers = mq_state.producers.sch_stop_pool_fuzzers
    if project.pool_id is not None:
        await sch_stop_pool_fuzzers.produce(pool_id=project.pool_id)
    await db.revisions.stop_all(project.id)


########################################
# Create project
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": ProjectResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_PROJECT_EXISTS),
        },
    },
)
async def create_project(
    response: Response,
    project: CreateProjectRequestModel,
    user_id: str = Path(..., regex=r"^\d+$"),
    current_user: ORMUser = Depends(current_user),
    operation: str = Depends(Operation("Create project")),
    external_api: ExternalAPI = Depends(get_external_api),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "project": project.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    if not current_user.is_system or not current_user.is_admin:
        return error_response(HTTP_403_FORBIDDEN, E_SYSTEM_ADMIN_REQUIRED)

    with suppress(DBProjectNotFoundError):
        await db.projects.get_by_name(project.name, user_id)
        return error_response(HTTP_409_CONFLICT, E_PROJECT_EXISTS)

    try:
        await external_api.pool_mgr.get_pool_by_id(
            id=project.pool_id,
            user_id=user_id,
        )

    # not found
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )

    created_project = await db.projects.create(
        name=project.name,
        description=project.description,
        created=rfc3339_now(),
        owner_id=user_id,
        pool_id=project.pool_id,
    )

    response_data = ProjectResponseModel(**created_project.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        project_id=created_project.id,
        project_name=created_project.name,
        owner_id=user_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Empty user trashbin
########################################


@router.delete(
    path="/trashbin",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": UserTrashbinEmptyResponseModel,
            "description": "Successful response",
        },
    },
)
async def empty_user_trashbin(
    operation: str = Depends(Operation("Empty user trashbin")),
    current_user: ORMUser = Depends(current_user),
    db: IDatabase = Depends(get_db),
):

    e_projects = await db.projects.trashbin_empty(current_user.id)

    response_data = UserTrashbinEmptyResponseModel(
        erased_projects=e_projects,
    )

    log_operation_success(
        operation=operation,
        user_id=current_user.id,
        caller=current_user.name,
    )

    return response_data


########################################
# Count projects
########################################


@dataclass
class FilterProjectsRequestModel:
    removal_state: Optional[UserObjectRemovalState] = Query(None)


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
async def get_project_count(
    operation: str = Depends(Operation("Get project count")),
    filters: FilterProjectsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    user_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    total_cnt = await db.projects.count(
        owner_id=user_id,
        removal_state=filters.removal_state.to_internal(),
    )
    total_pages = ceil(total_cnt / pg_size)

    response_data = ItemCountResponseModel(
        pg_size=pg_size,
        pg_total=total_pages,
        cnt_total=total_cnt,
    )

    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        owner_id=user_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get project by name
########################################


@router.get(
    path="/lookup",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ProjectResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_PROJECT_NOT_FOUND),
        },
    },
)
async def get_project_by_name(
    response: Response,
    name: str = Query(...),
    user_id: str = Path(..., regex=r"^\d+$"),
    operation: str = Depends(Operation("Get project by name")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "project_name": name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        project = await db.projects.get_by_name(name, user_id)
    except DBProjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_PROJECT_NOT_FOUND)

    response_data = ProjectResponseModel(**project.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        project_id=project.id,
        project_name=project.name,
        caller=current_user.name,
    )

    return response_data


########################################
# Get project
########################################


@router.get(
    path="/{project_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ProjectResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_PROJECT_NOT_FOUND),
        },
    },
)
async def get_project(
    response: Response,
    user_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    operation: str = Depends(Operation("Get project")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "project_id": project_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        project = await db.projects.get_by_id(project_id, user_id)
    except DBProjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_PROJECT_NOT_FOUND)

    response_data = ProjectResponseModel(**project.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        project_id=project.id,
        project_name=project.name,
        caller=current_user.name,
    )

    return response_data


########################################
# Update project
########################################


@router.patch(
    path="/{project_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_PROJECT_NOT_FOUND),
        },
    },
)
async def update_project(
    response: Response,
    project: UpdateProjectRequestModel,
    operation: str = Depends(Operation("Update project")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project_id: str = Path(..., regex=r"^\d+$"),
    user_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    external_api: ExternalAPI = Depends(get_external_api),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "project_id": project_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_project = await db.projects.get_by_id(project_id, user_id)
    except DBProjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_PROJECT_NOT_FOUND)

    if old_project.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_PROJECT_DELETED)

    if project.name is not None:
        with suppress(DBProjectNotFoundError):
            await db.projects.get_by_name(project.name, user_id)
            return error_response(HTTP_409_CONFLICT, E_PROJECT_EXISTS)

    if project.pool_id is not None:
        try:
            await external_api.pool_mgr.get_pool_by_id(
                id=project.pool_id,
                user_id=user_id,
            )

        # not found, ...
        except EAPIServerError as e:
            response.status_code = e.status_code
            return ErrorModel(
                code=e.error_code,
                message=e.message,
            )

    new_fields = project.dict(exclude_unset=True)
    merged = {**old_project.dict(), **new_fields}
    await db.projects.update(ORMProject(**merged))

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )


########################################
# Delete project
########################################


@router.delete(
    path="/{project_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_PROJECT_NOT_FOUND),
        },
    },
)
async def delete_project(
    response: Response,
    operation: str = Depends(Operation("Delete project")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project_id: str = Path(..., regex=r"^\d+$"),
    user_id: str = Path(..., regex=r"^\d+$"),
    new_name: Optional[str] = Query(None),
    action: DeleteActions = Query(...),
    db: IDatabase = Depends(get_db),
    no_backup: bool = Query(False),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"user_id": user_id, "project_id": project_id, "action": action}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    if not current_user.is_system or not current_user.is_admin:
        return error_response(HTTP_403_FORBIDDEN, E_SYSTEM_ADMIN_REQUIRED)

    try:
        project = await db.projects.get_by_id(project_id, user_id)
    except DBProjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_PROJECT_NOT_FOUND)

    if action == DeleteActions.restore:
        if project.erasure_date is None:
            return error_response(HTTP_409_CONFLICT, E_PROJECT_NOT_DELETED)

        if new_name is None:
            new_name = project.name

        with suppress(DBProjectNotFoundError):
            await db.projects.get_by_name(new_name, user_id)
            return error_response(HTTP_409_CONFLICT, E_PROJECT_EXISTS)

        project.name = new_name
        project.erasure_date = None
        await db.projects.update(project)

    else:
        # Already deleted (moved to trashbin)
        if action == DeleteActions.delete and project.erasure_date:
            return error_response(HTTP_409_CONFLICT, E_PROJECT_DELETED)

        if project.pool_id is not None:

            #
            # Stop running revisions in this project
            #

            await stop_all_revisions_internal(project, db, mq)

        #
        # Delete/erase logic there
        #

        project.no_backup = no_backup
        if action == DeleteActions.delete:
            exp_seconds = settings.trashbin.expiration_seconds
            project.erasure_date = rfc3339_add(datetime_utcnow(), exp_seconds)
        else:  # DeleteActions.erase
            project.erasure_date = rfc3339_now()

        await db.projects.update(project)

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )


########################################
# List projects
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListProjectsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_projects(
    user_id: str = Path(..., regex=r"^\d+$"),
    operation: str = Depends(Operation("List projects")),
    filters: FilterProjectsRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    projects = await db.projects.list(
        owner_id=user_id,
        paginator=Paginator(pg_num, pg_size),
        removal_state=filters.removal_state.to_internal(),
    )

    response_data = ListProjectsResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=projects
    )

    log_operation_success(
        operation=operation,
        owner_id=user_id,
        caller=current_user.name,
    )

    return response_data


# TODO: pool/project load
