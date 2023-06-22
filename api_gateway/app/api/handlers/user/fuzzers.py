from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import Any, Optional, Set

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import StreamingResponse
from mqtransport import MQApp
from starlette.status import *

from api_gateway.app.api.models.fuzzers import (
    CreateFuzzerRequestModel,
    FuzzerResponseModel,
    ListFuzzersResponseModel,
    ProjectTrashbinEmptyResponseModel,
    UpdateFuzzerRequestModel,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBEngineNotFoundError, DBFuzzerNotFoundError
from api_gateway.app.database.orm import (
    ORMEngineID,
    ORMFuzzer,
    ORMLangID,
    ORMProject,
    ORMUser,
    Paginator,
)
from api_gateway.app.object_storage import ObjectStorage
from api_gateway.app.object_storage.errors import ObjectNotFoundError
from api_gateway.app.settings import AppSettings
from api_gateway.app.utils import datetime_utcnow, rfc3339_add, rfc3339_now

from ...base import DeleteActions, ItemCountResponseModel, UserObjectRemovalState
from ...constants import *
from ...depends import (
    Operation,
    check_parent_project,
    current_user,
    get_db,
    get_mq,
    get_s3,
    get_settings,
    parent_project,
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
from .revisions import (
    restart_revision,
    start_revision,
    stop_revision,
    stop_revision_internal,
)

router = APIRouter(
    tags=["fuzzers"],
    prefix="/{project_id}/fuzzers",
    dependencies=[Depends(check_parent_project)],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.fuzzers", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.fuzzers", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.fuzzers", operation, reason, **kwargs)


########################################
# Create fuzzer
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": FuzzerResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_FUZZER_EXISTS),
        },
    },
)
async def create_fuzzer(
    response: Response,
    fuzzer: CreateFuzzerRequestModel,
    operation: str = Depends(Operation("Create fuzzer")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "fuzzer": fuzzer.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        engine = await db.engines.get_by_id(fuzzer.engine)
    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)

    if fuzzer.lang not in engine.langs:
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_ENGINE_LANG_INCOMPATIBLE)

    with suppress(DBFuzzerNotFoundError):
        await db.fuzzers.get_by_name(fuzzer.name, project_id)
        return error_response(HTTP_409_CONFLICT, E_FUZZER_EXISTS)

    created_fuzzer = await db.fuzzers.create(
        name=fuzzer.name,
        description=fuzzer.description,
        project_id=project_id,
        engine=fuzzer.engine,
        lang=fuzzer.lang,
        ci_integration=fuzzer.ci_integration,
        created=rfc3339_now(),
        active_revision=None,
    )

    response_data = FuzzerResponseModel(**created_fuzzer.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        fuzzer_id=created_fuzzer.id,
        fuzzer_name=created_fuzzer.name,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Count fuzzers
########################################


@dataclass
class FilterFuzzersRequestModel:
    engines: Optional[Set[ORMEngineID]] = Query(None)
    langs: Optional[Set[ORMLangID]] = Query(None)
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
async def get_fuzzer_count(
    operation: str = Depends(Operation("Get fuzzer count")),
    filters: FilterFuzzersRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    total_cnt = await db.fuzzers.count(
        project_id=project_id,
        engines=filters.engines,
        langs=filters.langs,
        removal_state=filters.removal_state.to_internal(),
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
# List fuzzers
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListFuzzersResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_fuzzers(
    operation: str = Depends(Operation("List fuzzers")),
    filters: FilterFuzzersRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    fuzzers = await db.fuzzers.list(
        project_id=project_id,
        paginator=Paginator(pg_num, pg_size),
        engines=filters.engines,
        langs=filters.langs,
        removal_state=filters.removal_state.to_internal(),
    )

    response_data = ListFuzzersResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=fuzzers
    )

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Count trashbin fuzzers
########################################


@router.get(
    path="/trashbin/count",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
)
async def get_trashbin_fuzzers_count(
    operation: str = Depends(Operation("Get trashbin fuzzers count")),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    total_cnt = await db.fuzzers.trashbin_count(project_id)
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
# List trashbin fuzzers
########################################


@router.get(
    path="/trashbin",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListFuzzersResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_trashbin_fuzzers(
    operation: str = Depends(Operation("List trashbin fuzzers")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    pgn = Paginator(pg_num, pg_size)
    fuzzers = await db.fuzzers.trashbin_list(pgn, project_id)

    response_data = ListFuzzersResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=fuzzers
    )

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Empty project trashbin
########################################


@router.delete(
    path="/trashbin",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ProjectTrashbinEmptyResponseModel,
            "description": "Successful response",
        },
    },
)
async def empty_project_trashbin(
    operation: str = Depends(Operation("Empty project trashbin")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    e_fuzzers, e_revisions = await db.fuzzers.trashbin_empty(project_id)

    response_data = ProjectTrashbinEmptyResponseModel(
        erased_fuzzers=e_fuzzers,
        erased_revisions=e_revisions,
    )

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Erase fuzzer in user trashbin
########################################


@router.delete(
    path="/trashbin/{fuzzer_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ProjectTrashbinEmptyResponseModel,
            "description": "Successful response",
        },
    },
)
async def erase_fuzzer_in_trashbin(
    response: Response,
    operation: str = Depends(Operation("Erase fuzzer in user trashbin")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        await db.fuzzers.get_by_id(fuzzer_id, project_id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    e_fuzzers, e_revisions = await db.fuzzers.trashbin_empty(project_id, fuzzer_id)

    response_data = ProjectTrashbinEmptyResponseModel(
        erased_fuzzers=e_fuzzers,
        erased_revisions=e_revisions,
    )

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Start fuzzer
########################################


@router.post(
    path="/{fuzzer_id}/actions/start",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_NOT_FOUND),
        },
    },
)
async def start_fuzzer(
    response: Response,
    operation: str = Depends(Operation("Start fuzzer")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project: ORMProject = Depends(parent_project),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project.id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project.id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    if fuzzer.erasure_date is not None:
        return error_response(HTTP_409_CONFLICT, E_FUZZER_DELETED)

    if fuzzer.active_revision is None:
        return error_response(HTTP_409_CONFLICT, E_ACTIVE_REVISION_NOT_FOUND)

    return await start_revision(
        response=response,
        operation=operation,
        current_user=current_user,
        settings=settings,
        project=project,
        fuzzer=fuzzer,
        revision_id=fuzzer.active_revision.id,
        db=db,
        mq=mq,
    )


########################################
# Restart fuzzer
########################################


@router.post(
    path="/{fuzzer_id}/actions/restart",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_NOT_FOUND),
        },
    },
)
async def restart_fuzzer(
    response: Response,
    operation: str = Depends(Operation("Restart fuzzer")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project: ORMProject = Depends(parent_project),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project.id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project.id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    if fuzzer.erasure_date is not None:
        return error_response(HTTP_409_CONFLICT, E_FUZZER_DELETED)

    if fuzzer.active_revision is None:
        return error_response(HTTP_409_CONFLICT, E_ACTIVE_REVISION_NOT_FOUND)

    return await restart_revision(
        response=response,
        operation=operation,
        current_user=current_user,
        settings=settings,
        project=project,
        fuzzer=fuzzer,
        revision_id=fuzzer.active_revision.id,
        db=db,
        mq=mq,
    )


########################################
# Stop fuzzer
########################################


@router.post(
    path="/{fuzzer_id}/actions/stop",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_NOT_FOUND),
        },
    },
)
async def stop_fuzzer(
    response: Response,
    operation: str = Depends(Operation("Stop fuzzer")),
    current_user: ORMUser = Depends(current_user),
    project: ORMProject = Depends(parent_project),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project.id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project.id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    if fuzzer.erasure_date is not None:
        return error_response(HTTP_409_CONFLICT, E_FUZZER_DELETED)

    if fuzzer.active_revision is None:
        return error_response(HTTP_409_CONFLICT, E_ACTIVE_REVISION_NOT_FOUND)

    return await stop_revision(
        response=response,
        operation=operation,
        current_user=current_user,
        fuzzer=fuzzer,
        project=project,
        revision_id=fuzzer.active_revision.id,
        db=db,
        mq=mq,
    )


########################################
# Download fuzzer files: corpus
########################################


@router.get(
    path="/{fuzzer_id}/files/corpus",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "description": "Successful response. Begin file download",
            "content": {
                "application/octet-stream": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_FUZZER_NOT_FOUND, E_FILE_NOT_FOUND),
        },
    },
)
async def download_fuzzer_corpus(
    response: Response,
    operation: str = Depends(Operation("Download fuzzer files: corpus")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project_id)
        if fuzzer.active_revision is None:
            return error_response(HTTP_404_NOT_FOUND, E_ACTIVE_REVISION_NOT_FOUND)
        else:
            chunks = await s3.download_fuzzer_corpus(
                fuzzer_id, fuzzer.active_revision.id
            )

    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)
    except ObjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    log_operation_success(operation, fuzzer_id=fuzzer_id, caller=current_user.name)
    return StreamingResponse(chunks, media_type="application/octet-stream")


########################################
# Get fuzzer by name
########################################


@router.get(
    path="/lookup",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": FuzzerResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_FUZZER_NOT_FOUND),
        },
    },
)
async def get_fuzzer_by_name(
    response: Response,
    operation: str = Depends(Operation("Get fuzzer by name")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    name: str = Query(...),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "fuzzer_name": name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_name(name, project_id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    response_data = FuzzerResponseModel(**fuzzer.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        caller=current_user.name,
    )

    return response_data


########################################
# Get fuzzer
########################################


@router.get(
    path="/{fuzzer_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": FuzzerResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_FUZZER_NOT_FOUND),
        },
    },
)
async def get_fuzzer(
    response: Response,
    operation: str = Depends(Operation("Get fuzzer")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project_id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    response_data = FuzzerResponseModel(**fuzzer.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        caller=current_user.name,
    )

    return response_data


########################################
# Update fuzzer
########################################


@router.patch(
    path="/{fuzzer_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_FUZZER_NOT_FOUND),
        },
    },
)
async def update_fuzzer(
    response: Response,
    fuzzer: UpdateFuzzerRequestModel,
    operation: str = Depends(Operation("Update fuzzer")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project_id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project_id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    if old_fuzzer.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_FUZZER_DELETED)

    if fuzzer.name is not None:
        with suppress(DBFuzzerNotFoundError):
            await db.fuzzers.get_by_name(fuzzer.name, project_id)
            return error_response(HTTP_409_CONFLICT, E_FUZZER_EXISTS)

    new_fields = fuzzer.dict(exclude_unset=True)
    merged = {**old_fuzzer.dict(), **new_fields}
    await db.fuzzers.update(ORMFuzzer(**merged))

    log_operation_success(
        operation=operation,
        fuzzer_id=old_fuzzer.id,
        caller=current_user.name,
    )


########################################
# Delete fuzzer
########################################


@router.delete(
    path="/{fuzzer_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_FUZZER_NOT_FOUND),
        },
    },
)
async def delete_fuzzer(
    response: Response,
    operation: str = Depends(Operation("Delete fuzzer")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project: ORMProject = Depends(parent_project),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    new_name: Optional[str] = Query(None),
    action: DeleteActions = Query(...),
    db: IDatabase = Depends(get_db),
    no_backup: bool = Query(False),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"project_id": project.id, "fuzzer_id": fuzzer_id, "action": action}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project.id)
    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    if action == DeleteActions.restore:
        if fuzzer.erasure_date is None:
            return error_response(HTTP_409_CONFLICT, E_FUZZER_NOT_DELETED)

        if new_name is None:
            new_name = fuzzer.name

        with suppress(DBFuzzerNotFoundError):
            await db.fuzzers.get_by_name(new_name, project.id)
            return error_response(HTTP_409_CONFLICT, E_FUZZER_EXISTS)

        fuzzer.name = new_name
        fuzzer.erasure_date = None
        await db.fuzzers.update(fuzzer)

    else:
        if fuzzer.erasure_date and action == DeleteActions.delete:
            # already in trashbin
            return error_response(HTTP_409_CONFLICT, E_FUZZER_DELETED)

        #
        # Stop running revision in this fuzzer
        #

        if project.pool_id and fuzzer.active_revision:
            await stop_revision_internal(project, fuzzer.active_revision, db, mq)

        fuzzer.no_backup = no_backup
        if action == DeleteActions.delete:
            exp_seconds = settings.trashbin.expiration_seconds
            fuzzer.erasure_date = rfc3339_add(datetime_utcnow(), exp_seconds)
        else:
            fuzzer.erasure_date = rfc3339_now()

        await db.fuzzers.update(fuzzer)

    log_operation_success(operation, fuzzer_id=fuzzer.id, caller=current_user.name)
