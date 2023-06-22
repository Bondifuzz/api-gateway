from math import ceil
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import validator
from starlette.status import *

from api_gateway.app.api.models.statistics import ListStatisticsResponseModel
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.orm import (
    ORMEngineID,
    ORMFuzzer,
    ORMRevision,
    ORMStatisticsGroupBy,
    ORMUser,
    Paginator,
)

from ...base import ItemCountResponseModel, QueryBaseModel
from ...constants import *
from ...depends import (
    Operation,
    check_parent_fuzzer,
    check_parent_revision,
    current_user,
    get_db,
    parent_fuzzer,
    parent_revision,
)
from ...error_codes import *
from ...utils import (
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
    normalize_date,
    pg_num_settings,
    pg_size_settings,
)

router = APIRouter(
    tags=["statistics"],
    prefix="/{fuzzer_id}",
    dependencies=[Depends(check_parent_fuzzer)],
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.statistics", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.statistics", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.statistics", operation, reason, **kwargs)


########################################
# Count fuzzer statistics
########################################


class FilterStatisticsRequestModel(QueryBaseModel):
    group_by: ORMStatisticsGroupBy = Query(...)
    date_begin: Optional[str] = Query(None)
    date_end: Optional[str] = Query(None)

    @validator("date_begin", "date_end", pre=True)
    def _normalize_date(cls, value: Optional[str]) -> Optional[str]:
        return normalize_date(value)


@router.get(
    path="/statistics/count",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
)
async def count_fuzzer_statistics_records(
    operation: str = Depends(Operation("Count fuzzer statistics records")),
    filter_options: FilterStatisticsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    pg_size: int = Query(**pg_size_settings()),
    db: IDatabase = Depends(get_db),
):
    if filter_options.date_begin is None:
        filter_options.date_begin = fuzzer.created

    if ORMEngineID.is_libfuzzer(fuzzer.engine):
        total_cnt = await db.statistics.libfuzzer.count(
            fuzzer_id=fuzzer.id,
            revision_id=None,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    elif ORMEngineID.is_afl(fuzzer.engine):
        total_cnt = await db.statistics.afl.count(
            fuzzer_id=fuzzer.id,
            revision_id=None,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    else:
        raise NotImplementedError(f"Unknown engine id: {fuzzer.engine}")

    total_pages = ceil(total_cnt / pg_size)
    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    dbg_info = [filter_options, response_data]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        caller=current_user.name,
    )

    return response_data


########################################
# List fuzzer statistics
########################################


@router.get(
    path="/statistics",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListStatisticsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_fuzzer_statistics(
    operation: str = Depends(Operation("List fuzzer statistics")),
    filter_options: FilterStatisticsRequestModel = Depends(),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    if filter_options.date_begin is None:
        filter_options.date_begin = fuzzer.created

    pgn = Paginator(pg_num, pg_size)
    if ORMEngineID.is_libfuzzer(fuzzer.engine):
        statistics = await db.statistics.libfuzzer.list(
            paginator=pgn,
            fuzzer_id=fuzzer.id,
            revision_id=None,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    elif ORMEngineID.is_afl(fuzzer.engine):
        statistics = await db.statistics.afl.list(
            paginator=pgn,
            fuzzer_id=fuzzer.id,
            revision_id=None,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    else:
        raise NotImplementedError(f"Unknown engine id: {fuzzer.engine}")

    response_data = ListStatisticsResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=statistics
    )

    dbg_info = [filter_options]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        caller=current_user.name,
    )

    return response_data


########################################
# Count revision statistics
########################################


@router.get(
    path="/revisions/{revision_id}/statistics/count",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
    dependencies=[Depends(check_parent_revision)],
)
async def count_revision_statistics_records(
    operation: str = Depends(Operation("Count revision statistics records")),
    filter_options: FilterStatisticsRequestModel = Depends(),
    revision: ORMRevision = Depends(parent_revision),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    pg_size: int = Query(**pg_size_settings()),
    db: IDatabase = Depends(get_db),
):
    if filter_options.date_begin is None:
        filter_options.date_begin = revision.created

    if ORMEngineID.is_libfuzzer(fuzzer.engine):
        total_cnt = await db.statistics.libfuzzer.count(
            fuzzer_id=fuzzer.id,
            revision_id=revision.id,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    elif ORMEngineID.is_afl(fuzzer.engine):
        total_cnt = await db.statistics.afl.count(
            fuzzer_id=fuzzer.id,
            revision_id=revision.id,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    else:
        raise NotImplementedError(f"Unknown engine id: {fuzzer.engine}")

    total_pages = ceil(total_cnt / pg_size)
    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    dbg_info = [filter_options, response_data]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        revision_id=revision.id,
        caller=current_user.name,
        result=response_data,
    )

    return response_data


########################################
# List revision statistics
########################################


@router.get(
    path="/revisions/{revision_id}/statistics",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListStatisticsResponseModel,
            "description": "Successful response",
        },
    },
    dependencies=[Depends(check_parent_revision)],
)
async def list_revision_statistics(
    operation: str = Depends(Operation("List revision statistics")),
    filter_options: FilterStatisticsRequestModel = Depends(),
    revision: ORMRevision = Depends(parent_revision),
    current_user: ORMUser = Depends(current_user),
    fuzzer: ORMFuzzer = Depends(parent_fuzzer),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    if filter_options.date_begin is None:
        filter_options.date_begin = revision.created

    pgn = Paginator(pg_num, pg_size)
    if ORMEngineID.is_libfuzzer(fuzzer.engine):
        statistics = await db.statistics.libfuzzer.list(
            paginator=pgn,
            fuzzer_id=fuzzer.id,
            revision_id=revision.id,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    elif ORMEngineID.is_afl(fuzzer.engine):
        statistics = await db.statistics.afl.list(
            paginator=pgn,
            fuzzer_id=fuzzer.id,
            revision_id=revision.id,
            group_by=filter_options.group_by,
            date_begin=filter_options.date_begin,
            date_end=filter_options.date_end,
        )

    else:
        raise NotImplementedError(f"Unknown engine id: {fuzzer.engine}")

    response_data = ListStatisticsResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=statistics
    )

    dbg_info = [filter_options]
    log_operation_debug_info(operation, dbg_info)

    log_operation_success(
        operation=operation,
        fuzzer_id=fuzzer.id,
        revision_id=revision.id,
        caller=current_user.name,
    )

    return response_data
