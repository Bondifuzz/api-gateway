from base64 import b64decode
from dataclasses import dataclass
from math import ceil
from typing import Any, Optional

from starlette.status import *
from api_gateway.app.api.models.crashes import (
    CrashResponseModel,
    ListCrashesResponseModel,
    PutArchivedCrashRequestModel,
)

from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBCrashNotFoundError
from api_gateway.app.database.orm import ORMUser, Paginator
from api_gateway.app.object_storage import ObjectStorage
from api_gateway.app.object_storage.errors import ObjectNotFoundError
from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import StreamingResponse

from ...base import (
    ItemCountResponseModel,
)
from ...constants import *
from ...depends import (
    Operation,
    check_parent_fuzzer,
    check_parent_revision,
    current_user,
    get_db,
    get_s3,
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
    tags=["crashes"],
    prefix="/{fuzzer_id}",
    dependencies=[Depends(check_parent_fuzzer)],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.crashes", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.crashes", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.crashes", operation, reason, **kwargs)


########################################
# Count crashes
########################################


@dataclass
class FilterCrashesRequestModel:
    date_begin: Optional[str] = Query(None)
    date_end: Optional[str] = Query(None)
    archived: Optional[bool] = Query(None)
    reproduced: Optional[bool] = Query(None)


@router.get(
    path="/crashes/count",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
)
async def count_fuzzer_crashes(
    operation: str = Depends(Operation("Count fuzzer crashes")),
    filters: FilterCrashesRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    return await _count_crashes(
        fuzzer_id=fuzzer_id,
        current_user=current_user,
        operation=operation,
        filters=filters,
        pg_size=pg_size,
        db=db,
    )


@router.get(
    path="/revisions/{revision_id}/crashes/count",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
    dependencies=[Depends(check_parent_revision)],
)
async def count_revision_crashes(
    operation: str = Depends(Operation("Count revision crashes")),
    filters: FilterCrashesRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    revision_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    return await _count_crashes(
        revision_id=revision_id,
        current_user=current_user,
        operation=operation,
        filters=filters,
        pg_size=pg_size,
        db=db,
    )


async def _count_crashes(
    filters: FilterCrashesRequestModel,
    current_user: ORMUser,
    operation: str,
    db: IDatabase,
    pg_size: int,
    fuzzer_id: Optional[str] = None,
    revision_id: Optional[str] = None,
):
    total_cnt = await db.crashes.count(
        fuzzer_id=fuzzer_id,
        revision_id=revision_id,
        date_begin=filters.date_begin,
        date_end=filters.date_end,
        archived=filters.archived,
        reproduced=filters.reproduced,
    )
    total_pages = ceil(total_cnt / pg_size)

    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    dbg_info = [filters, response_data]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        revision_id=revision_id,
        caller=current_user.name,
    )

    return response_data


########################################
# List crashes
########################################


@router.get(
    path="/crashes",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListCrashesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_fuzzer_crashes(
    operation: str = Depends(Operation("List fuzzer crashes")),
    filters: FilterCrashesRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    return await _list_crashes(
        fuzzer_id=fuzzer_id,
        current_user=current_user,
        operation=operation,
        filters=filters,
        pg_size=pg_size,
        pg_num=pg_num,
        db=db,
    )


@router.get(
    path="/revisions/{revision_id}/crashes",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListCrashesResponseModel,
            "description": "Successful response",
        },
    },
    dependencies=[Depends(check_parent_revision)],
)
async def list_revision_crashes(
    operation: str = Depends(Operation("List revision crashes")),
    filters: FilterCrashesRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    revision_id: str = Path(..., regex=r"^\d+$"),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    return await _list_crashes(
        revision_id=revision_id,
        current_user=current_user,
        operation=operation,
        filters=filters,
        pg_size=pg_size,
        pg_num=pg_num,
        db=db,
    )


async def _list_crashes(
    filters: FilterCrashesRequestModel,
    current_user: ORMUser,
    operation: str,
    db: IDatabase,
    pg_size: int,
    pg_num: int,
    fuzzer_id: Optional[str] = None,
    revision_id: Optional[str] = None,
):
    crashes = await db.crashes.list(
        fuzzer_id=fuzzer_id,
        revision_id=revision_id,
        paginator=Paginator(pg_num, pg_size),
        date_begin=filters.date_begin,
        date_end=filters.date_end,
        archived=filters.archived,
        reproduced=filters.reproduced,
    )

    response_data = ListCrashesResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=crashes
    )

    dbg_info = [filters]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer_id,
        revision_id=revision_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get fuzzer crash
########################################


@router.get(
    path="/crashes/{crash_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": CrashResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_CRASH_NOT_FOUND),
        },
    },
)
async def get_fuzzer_crash(
    response: Response,
    operation: str = Depends(Operation("Get fuzzer crash")),
    current_user: ORMUser = Depends(current_user),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    crash_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"fuzzer_id": fuzzer_id, "crash_id": crash_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        crash = await db.crashes.get(crash_id, fuzzer_id)
    except DBCrashNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_CRASH_NOT_FOUND)

    response_data = CrashResponseModel(**crash.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        crash_id=crash.id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Move crash to/from archive
########################################


@router.put(
    path="/crashes/{crash_id}/archived",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_CRASH_NOT_FOUND),
        },
    },
)
async def change_crash_archived(
    response: Response,
    request: PutArchivedCrashRequestModel,
    operation: str = Depends(Operation("Move crash to/from archive")),
    current_user: ORMUser = Depends(current_user),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    crash_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"crash_id": crash_id, "fuzzer_id": fuzzer_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, caller=current_user.name, **kw)
        response.status_code = status_code
        return rfail

    try:
        await db.crashes.update_archived(
            crash_id=crash_id,
            fuzzer_id=fuzzer_id,
            archived=request.archived,
        )
    except DBCrashNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_CRASH_NOT_FOUND)

    log_operation_success(
        operation=operation,
        crash_id=crash_id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )


########################################
# Download fuzzer crash
########################################


async def streaming_download(data: bytes, chunk_size=4096):
    for pos in range(0, len(data), chunk_size):
        yield data[pos : pos + chunk_size]


@router.get(
    path="/crashes/{crash_id}/raw",
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
            "description": error_msg(E_CRASH_NOT_FOUND, E_FILE_NOT_FOUND),
        },
    },
)
async def download_fuzzer_crash(
    response: Response,
    operation: str = Depends(Operation("Download fuzzer crash")),
    current_user: ORMUser = Depends(current_user),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    crash_id: str = Path(..., regex=r"^\d+$"),
    s3: ObjectStorage = Depends(get_s3),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"crash_id": crash_id, "caller": current_user.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        crash = await db.crashes.get(crash_id, fuzzer_id)
        media_type = "application/octet-stream"

        if not crash.input_id:
            content = b64decode(crash.preview)
            response = Response(content, media_type=media_type)

        else:
            chunks = await s3.download_crash(
                crash.fuzzer_id,
                crash.revision_id,
                crash.input_id,
            )

            response = StreamingResponse(chunks, media_type=media_type)

    except DBCrashNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_CRASH_NOT_FOUND)

    except ObjectNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_FILE_NOT_FOUND)

    log_operation_success(
        operation=operation,
        crash_id=crash.id,
        fuzzer_id=fuzzer_id,
        caller=current_user.name,
    )

    return response
