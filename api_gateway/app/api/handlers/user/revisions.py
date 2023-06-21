from dataclasses import dataclass

from mqtransport import MQApp
from api_gateway.app.api.models.revisions import (
    CopyCorpusRequestModel,
    CreateRevisionRequestModel,
    ListRevisionsResponseModel,
    RevisionResponseModel,
    SetActiveRevisionRequestModel,
    UpdateRevisionInfoRequestModel,
    UpdateRevisionResourcesRequestModel,
)

from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import (
    DBEngineNotFoundError,
    DBFuzzerNotFoundError,
    DBImageNotFoundError,
    DBRevisionNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMError,
    ORMFuzzer,
    ORMHealth,
    ORMImageStatus,
    ORMProject,
    ORMRevision,
    ORMRevisionStatus,
    ORMUploadStatus,
    ORMUser,
    Paginator,
)
from api_gateway.app.external_api import ExternalAPI
from api_gateway.app.external_api.errors import EAPIServerError
from api_gateway.app.message_queue import MQAppState
from api_gateway.app.object_storage import ObjectStorage
from api_gateway.app.object_storage.errors import ObjectNotFoundError, UploadLimitError
from api_gateway.app.settings import AppSettings, load_app_settings
from api_gateway.app.utils import (
    datetime_utcnow,
    gen_unique_identifier,
    rfc3339_add,
    rfc3339_now,
)

from ...base import (
    DeleteActions,
    ItemCountResponseModel,
    UserObjectRemovalState,
)
from ...constants import *
from ...depends import (
    Operation,
    check_parent_fuzzer,
    current_user,
    get_db,
    get_external_api,
    get_mq,
    get_s3,
    get_settings,
    parent_fuzzer,
    parent_project,
)
from ...error_codes import *
from ...error_model import ErrorModel, error_body, error_model, error_msg
from ...utils import (
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
    pg_num_settings,
    pg_size_settings,
)

try:
    import orjson as json  # type: ignore
except ModuleNotFoundError:
    import json

import logging
import tarfile
from contextlib import suppress
from io import BytesIO
from math import ceil
from typing import Any, AsyncIterator, Optional, Set

from pydantic import ValidationError
from starlette.status import *

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from fastapi.responses import StreamingResponse

router = APIRouter(
    tags=["revisions"],
    prefix="/{fuzzer_id}/revisions",
    dependencies=[Depends(check_parent_fuzzer)],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.revisions", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.revisions", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.revisions", operation, reason, **kwargs)


def config_upload_settings():

    result = {
        "gt": 0,
        "le": 10000,
        "include_in_schema": False,
    }

    try:
        settings = load_app_settings()
        result["le"] = settings.revision.config_upload_limit

    except ValidationError:
        logging.warning("Settings missing or invalid. Using upload limit stubs")

    return result


########################################
# Create revision
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": RevisionResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_EXISTS, E_FUZZER_ENGINE_MISMATCH),
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_IMAGE_NOT_FOUND),
        },
    },
)
async def create_revision(
    response: Response,
    request: CreateRevisionRequestModel,
    operation: str = Depends(Operation("Create revision")),
    settings: AppSettings = Depends(get_settings),
    current_user: ORMUser = Depends(current_user),
    project: ORMProject = Depends(parent_project),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    db: IDatabase = Depends(get_db),
    external_api: ExternalAPI = Depends(get_external_api),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer.id, "revision": request.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    #
    # Check fuzzer pool is present
    # Check fuzzer resource limits: cpu, ram, tmpfs
    #

    if project.pool_id is None:
        return error_response(HTTP_409_CONFLICT, E_NO_POOL_TO_USE)
    
    try:
        pool = await external_api.pool_mgr.get_pool_by_id(
            id=project.pool_id,
            user_id=project.owner_id,
        )
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )
    
    if (
        request.cpu_usage < settings.fuzzer.min_cpu_usage
        or request.cpu_usage > pool.resources.fuzzer_max_cpu
    ):
        return error_response(HTTP_409_CONFLICT, E_CPU_USAGE_INVALID)

    if (
        request.ram_usage < settings.fuzzer.min_ram_usage
        or request.ram_usage > pool.resources.fuzzer_max_ram
    ):
        return error_response(HTTP_409_CONFLICT, E_RAM_USAGE_INVALID)

    if (
        request.tmpfs_size < settings.fuzzer.min_tmpfs_size
        or request.tmpfs_size > pool.resources.fuzzer_max_ram
    ):
        return error_response(HTTP_409_CONFLICT, E_TMPFS_SIZE_INVALID)

    if request.ram_usage + request.tmpfs_size > pool.resources.fuzzer_max_ram:
        return error_response(HTTP_409_CONFLICT, E_TOTAL_RAM_USAGE_INVALID)

    #
    # Check the match of fuzzer engines given in request and agent image
    # Check the image can be used to run fuzzer
    #

    try:
        image = await db.images.get_by_id(request.image_id)
        engine = await db.engines.get_by_id(fuzzer.engine)

    except DBImageNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_IMAGE_NOT_FOUND)

    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)

    if fuzzer.engine not in image.engines:
        return error_response(HTTP_409_CONFLICT, E_FUZZER_ENGINE_MISMATCH)

    if fuzzer.lang not in engine.langs:
        return error_response(HTTP_409_CONFLICT, E_FUZZER_LANG_MISMATCH)

    if image.status != ORMImageStatus.ready:
        return error_response(HTTP_409_CONFLICT, E_IMAGE_NOT_READY)

    #
    # Autogenerate revision name if it was not specified
    # Check revision does not exist
    #

    if request.name is not None:
        with suppress(DBRevisionNotFoundError):
            await db.revisions.get_by_name(request.name, fuzzer.id)
            return error_response(HTTP_409_CONFLICT, E_REVISION_EXISTS)
    else:
        request.name = gen_unique_identifier()

    #
    # Create database record
    #

    created_revision = await db.revisions.create(
        name=request.name,
        description=request.description,
        status=ORMRevisionStatus.unverified,
        health=ORMHealth.err,
        binaries=ORMUploadStatus(uploaded=False),
        config=ORMUploadStatus(uploaded=False),
        seeds=ORMUploadStatus(uploaded=False),
        cpu_usage=request.cpu_usage,
        ram_usage=request.ram_usage,
        tmpfs_size=request.tmpfs_size,
        image_id=request.image_id,
        fuzzer_id=fuzzer.id,
        created=rfc3339_now(),
        is_verified=False,
    )

    response_data = RevisionResponseModel(**created_revision.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        revision_id=created_revision.id,
        revision_name=created_revision.name,
        fuzzer_id=fuzzer.id,
        caller=current_user.name,
    )

    return response_data


########################################
# Start revision
########################################


@router.post(
    path="/{revision_id}/actions/start",
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
async def start_revision(
    response: Response,
    operation: str = Depends(Operation("Start revision")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project: ORMProject = Depends(parent_project),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer.id, "revision": revision_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    #
    # Check project pool is present
    #

    if project.pool_id is None:
        return error_response(HTTP_409_CONFLICT, E_NO_POOL_TO_USE)

    #
    # Get revision and ensure it's ready for start
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if not revision.binaries.uploaded:
        return error_response(HTTP_409_CONFLICT, E_MUST_UPLOAD_BINARIES)

    if revision.status in [ORMRevisionStatus.running, ORMRevisionStatus.verifying]:
        return error_response(HTTP_409_CONFLICT, E_REVISION_ALREADY_RUNNING)

    elif (
        revision.health == ORMHealth.err
        and revision.status != ORMRevisionStatus.unverified
    ):
        return error_response(HTTP_409_CONFLICT, E_REVISION_CAN_ONLY_RESTART)

    restart = revision.status == ORMRevisionStatus.unverified
    await _start_revision_internal(
        restart=restart,
        project=project,
        revision=revision,
        settings=settings,
        fuzzer=fuzzer,
        db=db,
        mq=mq,
    )

    log_operation_success(
        operation=operation,
        revision_id=revision.id,
        revision_name=revision.name,
        caller=current_user.name,
    )


########################################
# Restart revision
########################################


@router.post(
    path="/{revision_id}/actions/restart",
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
async def restart_revision(
    response: Response,
    operation: str = Depends(Operation("Restart revision")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project: ORMProject = Depends(parent_project),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer.id, "revision": revision_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    #
    # Check project pool is present
    #

    if project.pool_id is None:
        return error_response(HTTP_409_CONFLICT, E_NO_POOL_TO_USE)

    #
    # Get revision and ensure it's ready for restart
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if not revision.binaries.uploaded:
        return error_response(HTTP_409_CONFLICT, E_MUST_UPLOAD_BINARIES)

    await _start_revision_internal(
        restart=True,
        project=project,
        revision=revision,
        settings=settings,
        fuzzer=fuzzer,
        db=db,
        mq=mq,
    )

    log_operation_success(
        operation=operation,
        revision_id=revision.id,
        revision_name=revision.name,
        caller=current_user.name,
    )


async def _start_revision_internal(
    restart: bool,
    project: ORMProject,
    revision: ORMRevision,
    settings: AppSettings,
    fuzzer: ORMFuzzer,
    db: IDatabase,
    mq: MQApp,
):
    #
    # Send task to scheduler
    # Change running revision in database
    #

    mq_state: MQAppState = mq.state
    sch_start_fuzzer = mq_state.producers.sch_start_fuzzer

    await db.fuzzers.set_active_revision(
        fuzzer=fuzzer,
        revision=revision,
        start=True,
        restart=restart,
    )

    await sch_start_fuzzer.produce(
        user_id=project.owner_id,
        project_id=project.id,
        pool_id=project.pool_id,
        fuzzer_rev=revision.id,
        fuzzer_id=revision.fuzzer_id,
        fuzzer_engine=fuzzer.engine,
        fuzzer_lang=fuzzer.lang,
        is_verified=revision.is_verified,
        reset_state=restart,
        cpu_usage=revision.cpu_usage,
        ram_usage=revision.ram_usage,
        tmpfs_size=revision.tmpfs_size,
        image_id=revision.image_id,
    )


########################################
# Stop revision
########################################


async def stop_revision_internal(
    project: ORMProject,
    revision: ORMRevision,
    db: IDatabase,
    mq: MQApp,
):
    if revision.status not in [
        ORMRevisionStatus.running,
        ORMRevisionStatus.verifying,
    ]:
        return

    if revision.status == ORMRevisionStatus.verifying:
        revision.status = ORMRevisionStatus.unverified
    else:
        revision.status = ORMRevisionStatus.stopped

    revision.last_stop_date = rfc3339_now()
    await db.revisions.update(revision)

    mq_state: MQAppState = mq.state
    await mq_state.producers.sch_stop_fuzzer.produce(
        pool_id=project.pool_id,
        fuzzer_id=revision.fuzzer_id,
        fuzzer_rev=revision.id,
    )


@router.post(
    path="/{revision_id}/actions/stop",
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
async def stop_revision(
    response: Response,
    operation: str = Depends(Operation("Stop revision")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    project: ORMProject = Depends(parent_project),
    revision_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer.id, "revision": revision_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    #
    # Check project pool is present
    #

    if project.pool_id is None:
        return error_response(HTTP_409_CONFLICT, E_NO_POOL_TO_USE)

    #
    # Get revision and ensure it's running
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if revision.status not in [ORMRevisionStatus.running, ORMRevisionStatus.verifying]:
        return error_response(HTTP_409_CONFLICT, E_REVISION_IS_NOT_RUNNING)

    #
    # Update database record
    # and send stop task to scheduler
    #

    await stop_revision_internal(project, revision, db, mq)

    log_operation_success(
        operation=operation,
        revision_id=revision.id,
        revision_name=revision.name,
        caller=current_user.name,
    )


########################################
# Upload revision files: binaries
########################################


async def chain(first_chunk: bytes, other_chunks: AsyncIterator[bytes]):
    yield first_chunk
    async for chunk in other_chunks:
        yield chunk


def check_uploaded_files(revision: ORMRevision):

    binaries = revision.binaries
    seeds = revision.seeds
    config = revision.config

    if binaries.uploaded:
        binaries_error = False
    else:
        binaries_error = True

    if seeds.uploaded:
        seeds_error = False
    elif not seeds.uploaded and seeds.last_error is None:
        seeds_error = False
    else:
        seeds_error = True

    if config.uploaded:
        config_error = False
    elif not config.uploaded and config.last_error is None:
        config_error = False
    else:
        config_error = True

    some_errors = binaries_error or seeds_error or config_error

    if some_errors:
        revision.health = ORMHealth.err
    else:
        revision.health = ORMHealth.ok

    return revision


@router.put(
    path="/{revision_id}/files/binaries",
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
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        },
    },
)
async def upload_revision_binaries(
    request: Request,
    response: Response,
    operation: str = Depends(Operation("Upload revision files: binaries")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"revision_id": revision_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    async def handle_upload_error(revision: ORMRevision):
        revision.binaries.uploaded = False
        error = error_body(E_UPLOAD_FAILURE)
        revision.binaries.last_error = ORMError(**error)
        revision.health = ORMHealth.err
        await db.revisions.update(revision)

    #
    # Get revision and check it is not verified
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if revision.status != ORMRevisionStatus.unverified:
        return error_response(HTTP_409_CONFLICT, E_REVISION_CAN_NOT_BE_CHANGED)

    #
    # Perform minimal checks to ensure provided binaries is an archive
    #

    try:
        stream = request.stream()
        first_chunk = await stream.__anext__()
        tarfile.open(mode="r:gz", fileobj=BytesIO(first_chunk)).close()

    except tarfile.TarError:
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_FILE_NOT_ARCHIVE)

    except:
        await handle_upload_error(revision)
        raise

    #
    # Upload archive to object storage and update revision status
    #

    try:
        chained = chain(first_chunk, stream)
        length = settings.revision.binaries_upload_limit
        await s3.upload_fuzzer_binaries(fuzzer.id, revision_id, chained, length)

    except UploadLimitError:
        return error_response(HTTP_413_REQUEST_ENTITY_TOO_LARGE, E_FILE_TOO_LARGE)

    except:
        await handle_upload_error(revision)
        raise

    revision.binaries.uploaded = True
    revision.binaries.last_error = None
    await db.revisions.update(check_uploaded_files(revision))

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        revision_id=revision.id,
        caller=current_user.name,
    )


########################################
# Upload revision files: seeds
########################################


@router.put(
    path="/{revision_id}/files/seeds",
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
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        },
    },
)
async def upload_revision_seeds(
    request: Request,
    response: Response,
    operation: str = Depends(Operation("Upload revision files: seeds")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"revision_id": revision_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    async def handle_upload_error(revision: ORMRevision):
        revision.seeds.uploaded = False
        error = error_body(E_UPLOAD_FAILURE)
        revision.seeds.last_error = ORMError(**error)
        revision.health = ORMHealth.err
        await db.revisions.update(revision)

    #
    # Get revision and check it is not verified
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if revision.status != ORMRevisionStatus.unverified:
        return error_response(HTTP_409_CONFLICT, E_REVISION_CAN_NOT_BE_CHANGED)

    #
    # Perform minimal checks to ensure provided file is an archive
    #

    try:
        stream = request.stream()
        first_chunk = await stream.__anext__()
        tarfile.open(mode="r:gz", fileobj=BytesIO(first_chunk)).close()

    except tarfile.TarError:
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_FILE_NOT_ARCHIVE)

    except:
        await handle_upload_error(revision)
        raise

    #
    # Upload archive to object storage and update revision status
    #

    try:
        chained = chain(first_chunk, stream)
        length = settings.revision.seeds_upload_limit
        await s3.upload_fuzzer_seeds(fuzzer.id, revision_id, chained, length)

    except UploadLimitError:
        return error_response(HTTP_413_REQUEST_ENTITY_TOO_LARGE, E_FILE_TOO_LARGE)

    except:
        await handle_upload_error(revision)
        raise

    revision.seeds.uploaded = True
    revision.seeds.last_error = None
    await db.revisions.update(check_uploaded_files(revision))

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        revision_id=revision.id,
        caller=current_user.name,
    )


########################################
# Upload revision files: config
########################################


@router.put(
    path="/{revision_id}/files/config",
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
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        },
    },
)
async def upload_revision_config(
    request: Request,
    response: Response,
    operation: str = Depends(Operation("Upload revision files: config")),
    content_length: int = Header(..., **config_upload_settings()),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"revision_id": revision_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    async def handle_upload_error(revision: ORMRevision):
        revision.config.uploaded = False
        error = error_body(E_UPLOAD_FAILURE)
        revision.config.last_error = ORMError(**error)
        revision.health = ORMHealth.err
        await db.revisions.update(revision)

    #
    # Get revision and check it is not verified
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if revision.status != ORMRevisionStatus.unverified:
        return error_response(HTTP_409_CONFLICT, E_REVISION_CAN_NOT_BE_CHANGED)

    #
    # Upload file chunk by chunk with content length control
    #

    try:
        content = b""
        async for chunk in request.stream():
            content_length -= len(chunk)
            if content_length < 0:
                raise UploadLimitError()
            content += chunk

    except UploadLimitError:
        return error_response(HTTP_413_REQUEST_ENTITY_TOO_LARGE, E_FILE_TOO_LARGE)

    except:
        await handle_upload_error(revision)
        raise

    #
    # Perform checks to ensure provided file has json format
    #

    try:
        data = json.loads(content.decode())
    except ValueError:
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_JSON_FILE_IS_INVALID)

    if not isinstance(data, dict):
        return error_response(HTTP_422_UNPROCESSABLE_ENTITY, E_JSON_FILE_IS_INVALID)

    #
    # Upload archive to object storage and update revision status
    #

    try:
        await s3.upload_fuzzer_config(fuzzer.id, revision_id, content)
    except:
        await handle_upload_error(revision)
        raise

    revision.config.uploaded = True
    revision.config.last_error = None
    await db.revisions.update(check_uploaded_files(revision))

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        revision_id=revision.id,
        caller=current_user.name,
    )


########################################
# Download revision files: binaries
########################################


@router.get(
    path="/{revision_id}/files/binaries",
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
            "description": error_msg(E_REVISION_NOT_FOUND, E_FILE_NOT_FOUND),
        },
    },
)
async def download_revision_binaries(
    response: Response,
    operation: str = Depends(Operation("Download revision files: binaries")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"revision_id": revision_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    #
    # Get revision and check binaries were uploaded
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if not revision.binaries.uploaded:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    #
    # Download archive from object storage
    #

    try:
        chunks = await s3.download_fuzzer_binaries(fuzzer.id, revision_id)
    except ObjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        revision_id=revision.id,
        caller=current_user.name,
    )

    return StreamingResponse(chunks, media_type="application/octet-stream")


########################################
# Download revision files: seeds
########################################


@router.get(
    path="/{revision_id}/files/seeds",
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
            "description": error_msg(E_REVISION_NOT_FOUND, E_FILE_NOT_FOUND),
        },
    },
)
async def download_revision_seeds(
    response: Response,
    operation: str = Depends(Operation("Download revision files: seeds")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"revision_id": revision_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    #
    # Get revision and check seeds were uploaded
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if not revision.seeds.uploaded:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    #
    # Download archive from object storage
    #

    try:
        chunks = await s3.download_fuzzer_seeds(fuzzer.id, revision_id)
    except ObjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        revision_id=revision.id,
        caller=current_user.name,
    )

    return StreamingResponse(chunks, media_type="application/octet-stream")


########################################
# Download revision files: config
########################################


@router.get(
    path="/{revision_id}/files/config",
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
            "description": error_msg(E_REVISION_NOT_FOUND, E_FILE_NOT_FOUND),
        },
    },
)
async def download_revision_config(
    response: Response,
    operation: str = Depends(Operation("Download revision files: config")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    revision_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"revision_id": revision_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    #
    # Get revision and check config was uploaded
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if not revision.config.uploaded:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    #
    # Download archive from object storage
    #

    try:
        config = await s3.download_fuzzer_config(fuzzer.id, revision_id)
    except ObjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        fuzzer_name=fuzzer.name,
        revision_id=revision.id,
        caller=current_user.name,
    )

    return Response(config, media_type="application/octet-stream")


########################################
# Copy corpus files
########################################


@router.put(
    path="/{dst_rev_id}/files/corpus",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(
                E_CORPUS_OVERWRITE_FORBIDDEN,
                E_COPY_SOURCE_TARGET_SAME,
            ),
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(
                E_SOURCE_REVISION_NOT_FOUND,
                E_TARGET_REVISION_NOT_FOUND,
                E_NO_CORPUS_FOUND,
            ),
        },
    },
)
async def copy_corpus_files(
    response: Response,
    request: CopyCorpusRequestModel,
    dst_rev_id: str = Path(..., regex=r"\d+"),
    operation: str = Depends(Operation("Copy corpus files")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    src_rev_id = request.src_rev_id

    def error_response(status_code: int, error_code: int):
        kw = {"src_rev_id": src_rev_id, "dst_rev_id": dst_rev_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    if src_rev_id == dst_rev_id:
        return error_response(HTTP_409_CONFLICT, E_COPY_SOURCE_TARGET_SAME)

    try:
        await db.revisions.get_by_id(src_rev_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_SOURCE_REVISION_NOT_FOUND)

    try:
        dst_rev = await db.revisions.get_by_id(dst_rev_id, fuzzer.id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_TARGET_REVISION_NOT_FOUND)

    if dst_rev.status != ORMRevisionStatus.unverified:
        return error_response(HTTP_409_CONFLICT, E_CORPUS_OVERWRITE_FORBIDDEN)

    try:
        await s3.copy_corpus_files(src_rev_id, dst_rev_id, fuzzer.id)
    except ObjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_NO_CORPUS_FOUND)

    log_operation_success(
        operation=operation,
        src_rev_id=src_rev_id,
        dst_rev_id=dst_rev_id,
        caller=current_user.name,
    )


########################################
# Count revisions
########################################


@dataclass
class FilterRevisionsRequestModel:
    removal_state: Optional[UserObjectRemovalState] = Query(None)
    statuses: Optional[Set[ORMRevisionStatus]] = Query(None)
    health: Optional[Set[ORMHealth]] = Query(None)


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
async def get_revision_count(
    operation: str = Depends(Operation("Get revision count")),
    filters: FilterRevisionsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    total_cnt = await db.revisions.count(
        fuzzer_id=fuzzer_id,
        health=filters.health,
        statuses=filters.statuses,
        removal_state=filters.removal_state.to_internal(),
    )
    total_pages = ceil(total_cnt / pg_size)

    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get active revision
########################################


@router.get(
    path="/active",
    status_code=HTTP_200_OK,
    description="Get active revision",
    responses={
        HTTP_200_OK: {
            "model": RevisionResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_NOT_FOUND),
        },
    },
)
async def get_active_revision(
    response: Response,
    operation: str = Depends(Operation("Get active revision")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer.id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    if fuzzer.active_revision is None:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    response_data = RevisionResponseModel(**fuzzer.active_revision.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        revision_id=fuzzer.active_revision.id,
        fuzzer_id=fuzzer.id,
        caller=current_user.name,
    )

    return response_data


########################################
# Set active revision
########################################


@router.put(
    path="/active",
    status_code=HTTP_200_OK,
    description="Set active revision",
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
async def set_active_revision(
    response: Response,
    request: SetActiveRevisionRequestModel,
    operation: str = Depends(Operation("Set active revision")),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    project: ORMProject = Depends(parent_project),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer.id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    # TODO: api logic seems unfinished
    if project.pool_id is None:
        return error_response(HTTP_409_CONFLICT, E_NO_POOL_TO_USE)

    if fuzzer.active_revision is not None:
        if fuzzer.active_revision.id == request.revision_id:
            return error_response(HTTP_409_CONFLICT, E_REVISION_ALREADY_ACTIVE)

    try:
        new_revision = await db.revisions.get_by_id(request.revision_id, fuzzer.id)
        await db.fuzzers.set_active_revision(fuzzer, new_revision, False)

    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    except DBFuzzerNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)

    log_operation_success(
        operation=operation,
        revision_id=fuzzer.active_revision.id,
        fuzzer_id=fuzzer.id,
        caller=current_user.name,
    )


########################################
# Get revision by name
########################################


@router.get(
    path="/lookup",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": RevisionResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_NOT_FOUND),
        },
    },
)
async def get_revision_by_name(
    response: Response,
    operation: str = Depends(Operation("Get revision by name")),
    current_user: ORMUser = Depends(current_user),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
    name: str = Query(...),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer_id, "revision_name": name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        revision = await db.revisions.get_by_name(name, fuzzer_id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    response_data = RevisionResponseModel(**revision.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        revision_id=revision.id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get revision
########################################


@router.get(
    path="/{revision_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": RevisionResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_REVISION_NOT_FOUND),
        },
    },
)
async def get_revision(
    response: Response,
    operation: str = Depends(Operation("Get revision")),
    current_user: ORMUser = Depends(current_user),
    revision_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer_id, "revision_id": revision_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer_id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    response_data = RevisionResponseModel(**revision.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        revision_id=revision.id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Update revision: information
########################################


@router.patch(
    path="/{revision_id}",
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
async def update_revision_information(
    response: Response,
    revision: UpdateRevisionInfoRequestModel,
    operation: str = Depends(Operation("Update revision: information")),
    current_user: ORMUser = Depends(current_user),
    revision_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer_id, "revision_id": revision_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_revision = await db.revisions.get_by_id(revision_id, fuzzer_id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if old_revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    if revision.name is not None:
        with suppress(DBRevisionNotFoundError):
            await db.revisions.get_by_name(revision.name, fuzzer_id)
            return error_response(HTTP_409_CONFLICT, E_REVISION_EXISTS)

    new_fields = revision.dict(exclude_unset=True)
    merged = {**old_revision.dict(), **new_fields}
    await db.revisions.update(ORMRevision(**merged))

    log_operation_success(
        operation=operation,
        revision_id=revision_id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )


########################################
# Update revision: resources
########################################


@router.patch(
    path="/{revision_id}/resources",
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
async def update_revision_resources(
    response: Response,
    request: UpdateRevisionResourcesRequestModel,
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    revision_id: str = Path(..., regex=r"^\d+$"),
    operation: str = Depends(Operation("Update revision: resources")),
    external_api: ExternalAPI = Depends(get_external_api),
    current_user: ORMUser = Depends(current_user),
    project: ORMProject = Depends(parent_project),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer_id, "revision_id": revision_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    #
    # Check fuzzer pool is present
    # Check fuzzer resource limits: cpu, ram, tmpfs
    #

    if project.pool_id is None:
        return error_response(HTTP_409_CONFLICT, E_NO_POOL_TO_USE)
    
    try:
        pool = await external_api.pool_mgr.get_pool_by_id(
            id=project.pool_id,
            user_id=project.owner_id,
        )
    except EAPIServerError as e:
        response.status_code = e.status_code
        return ErrorModel(
            code=e.error_code,
            message=e.message,
        )
    
    if request.cpu_usage:
        if (
            request.cpu_usage < settings.fuzzer.min_cpu_usage
            or request.cpu_usage > pool.resources.fuzzer_max_cpu
        ):
            return error_response(HTTP_409_CONFLICT, E_CPU_USAGE_INVALID)

    if request.ram_usage:
        if (
            request.ram_usage < settings.fuzzer.min_ram_usage
            or request.ram_usage > pool.resources.fuzzer_max_ram
        ):
            return error_response(HTTP_409_CONFLICT, E_RAM_USAGE_INVALID)

    if request.tmpfs_size:
        if (
            request.tmpfs_size < settings.fuzzer.min_tmpfs_size
            or request.tmpfs_size > pool.resources.fuzzer_max_ram
        ):
            return error_response(HTTP_409_CONFLICT, E_TMPFS_SIZE_INVALID)

    #
    # Get revision
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer_id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if revision.erasure_date:
        return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

    #
    # Check updated RAM/TmpFS do not exceed pool limits
    #

    ram_usage = request.ram_usage or revision.ram_usage
    tmpfs_size = request.tmpfs_size or revision.tmpfs_size

    if ram_usage + tmpfs_size > pool.resources.fuzzer_max_ram:
        return error_response(HTTP_409_CONFLICT, E_TOTAL_RAM_USAGE_INVALID)

    #
    # If revision is running now, send request to scheduler for live update
    # Then merge fields and update record in database
    #

    new_fields = request.dict(exclude_unset=True)
    merged = {**revision.dict(), **new_fields}
    new_revision = ORMRevision(**merged)

    if revision.status in [ORMRevisionStatus.running, ORMRevisionStatus.verifying]:
        state: MQAppState = mq.state
        await state.producers.sch_update_fuzzer.produce(
            pool_id=project.pool_id,
            fuzzer_id=fuzzer_id,
            fuzzer_rev=revision_id,
            cpu_usage=new_revision.cpu_usage,
            ram_usage=new_revision.ram_usage,
            tmpfs_size=new_revision.tmpfs_size,
        )

    await db.revisions.update(new_revision)

    log_operation_success(
        operation=operation,
        revision_id=revision_id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )


########################################
# Delete revision
########################################


@router.delete(
    path="/{revision_id}",
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
async def delete_revision(
    response: Response,
    operation: str = Depends(Operation("Delete revision")),
    current_user: ORMUser = Depends(current_user),
    settings: AppSettings = Depends(get_settings),
    project: ORMProject = Depends(parent_project),
    revision_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    new_name: Optional[str] = Query(None),
    action: DeleteActions = Query(...),
    db: IDatabase = Depends(get_db),
    no_backup: bool = Query(False),
    mq: MQApp = Depends(get_mq),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer_id, "revision_id": revision_id, "action": action}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    #
    # Get revision and check it's not running
    #

    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer_id)
    except DBRevisionNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)

    if action == DeleteActions.restore:
        if revision.erasure_date is None:
            return error_response(HTTP_409_CONFLICT, E_REVISION_NOT_DELETED)

        if new_name is None:
            new_name = revision.name

        with suppress(DBRevisionNotFoundError):
            await db.revisions.get_by_name(new_name, fuzzer_id)
            return error_response(HTTP_409_CONFLICT, E_REVISION_EXISTS)

        revision.name = new_name
        revision.erasure_date = None
        await db.revisions.update(revision)

    else:
        if revision.erasure_date and action == DeleteActions.delete:
            # already in trashbin
            return error_response(HTTP_409_CONFLICT, E_REVISION_DELETED)

        #
        # If revision is running, stop it
        # Update database record and send stop task to scheduler
        #

        await stop_revision_internal(project, revision, db, mq)

        #
        # Move revision to trash bin
        #

        revision.no_backup = no_backup
        if action == DeleteActions.delete:
            exp_seconds = settings.trashbin.expiration_seconds
            revision.erasure_date = rfc3339_add(datetime_utcnow(), exp_seconds)
        else:
            revision.erasure_date = rfc3339_now()

        await db.revisions.update(revision)

    log_operation_success(
        operation=operation,
        revision_id=revision_id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )


########################################
# List revisions
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListRevisionsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_revisions(
    operation: str = Depends(Operation("List revisions")),
    filters: FilterRevisionsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):

    if filters.removal_state is None:
        filters.removal_state = UserObjectRemovalState.present

    revisions = await db.revisions.list(
        fuzzer_id=fuzzer_id,
        paginator=Paginator(pg_num, pg_size),
        health=filters.health,
        statuses=filters.statuses,
        removal_state=filters.removal_state.to_internal(),
    )

    response_data = ListRevisionsResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=revisions
    )

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )

    return response_data
