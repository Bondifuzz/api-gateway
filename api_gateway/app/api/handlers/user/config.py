from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from starlette.status import *

from api_gateway.app.api.models.engines import (
    EngineResponseModel,
    ListEnginesResponseModel,
)
from api_gateway.app.api.models.integration_types import (
    IntegrationTypeResponseModel,
    ListIntegrationTypesResponseModel,
)
from api_gateway.app.api.models.langs import LangResponseModel, ListLangsResponseModel
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.orm import ORMLangID, Paginator
from api_gateway.app.settings import AppSettings, PlatformType

from ...depends import Operation, get_db, get_settings
from ...utils import (
    log_operation_debug_info_to,
    log_operation_error_to,
    log_operation_success_to,
    pg_num_settings,
    pg_size_settings,
)

router = APIRouter(
    tags=["platform config"],
    prefix="/config",
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.config", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.config", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.config", operation, reason, **kwargs)


########################################
# List fuzzer langs
########################################


@router.get(
    path="/langs",
    status_code=HTTP_200_OK,
    description="Returns list of supported programming languages",
    responses={
        HTTP_200_OK: {
            "model": ListLangsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_platform_langs(
    operation: str = Depends(Operation("List fuzzer langs")),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    langs = await db.langs.list(
        paginator=Paginator(pg_num, pg_size),
    )

    response_data = ListLangsResponseModel(pg_num=pg_num, pg_size=pg_size, items=langs)

    log_operation_success(operation)

    return response_data


########################################
# List fuzzer engines
########################################


@router.get(
    path="/engines",
    status_code=HTTP_200_OK,
    description="Returns list of supported fuzzing engines",
    responses={
        HTTP_200_OK: {
            "model": ListEnginesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_platform_engines(
    operation: str = Depends(Operation("List fuzzer engines")),
    lang: Optional[ORMLangID] = Query(None),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    engines = await db.engines.list(
        paginator=Paginator(pg_num, pg_size),
        lang_id=lang,
    )

    response_data = ListEnginesResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=engines
    )

    log_operation_debug_info(operation, lang)
    log_operation_success(operation)

    return response_data


########################################
# List integration types
########################################


@router.get(
    path="/integration_types",
    status_code=HTTP_200_OK,
    description="Returns list of supported integration types",
    responses={
        HTTP_200_OK: {
            "model": ListIntegrationTypesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_platform_integration_types(
    operation: str = Depends(Operation("List integration types")),
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

    log_operation_success(operation)

    return response_data


########################################
# Get full platform config
########################################


class FuzzerConfigResponseModel(BaseModel):
    min_cpu_usage: int
    min_ram_usage: int
    min_tmpfs_usage: int


class FileLimitsResponseModel(BaseModel):
    binaries: int
    config: int
    seeds: int


class PlatformConfigResponseModel(BaseModel):
    langs: List[LangResponseModel]
    engines: List[EngineResponseModel]
    integration_types: List[IntegrationTypeResponseModel]
    file_limits: FileLimitsResponseModel
    platform_type: PlatformType
    fuzzer: FuzzerConfigResponseModel


@router.get(
    path="",
    status_code=HTTP_200_OK,
    description="Returns platform configuration",
    responses={
        HTTP_200_OK: {
            "model": PlatformConfigResponseModel,
            "description": "Successful response",
        },
    },
)
async def get_platform_config(
    operation: str = Depends(Operation("Get platform config")),
    settings: AppSettings = Depends(get_settings),
    db: IDatabase = Depends(get_db),
):
    response_data = PlatformConfigResponseModel(
        langs=await db.langs.list(),
        engines=await db.engines.list(),
        integration_types=await db.integration_types.list(),
        file_limits=FileLimitsResponseModel(
            binaries=settings.revision.binaries_upload_limit,
            config=settings.revision.config_upload_limit,
            seeds=settings.revision.seeds_upload_limit,
        ),
        platform_type=settings.environment.platform_type,
        fuzzer=FuzzerConfigResponseModel(
            min_cpu_usage=settings.fuzzer.min_cpu_usage,
            min_ram_usage=settings.fuzzer.min_ram_usage,
            min_tmpfs_usage=settings.fuzzer.min_tmpfs_size,
        ),
    )

    log_operation_success(operation)

    return response_data
