from dataclasses import dataclass
from math import ceil
from typing import Any, Optional, Set

from fastapi import APIRouter, Depends, Path, Query, Response
from starlette.status import *

from api_gateway.app.api.models.images import (
    ImageResponseModel,
    ListImagesResponseModel,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBImageNotFoundError
from api_gateway.app.database.orm import ORMEngineID, ORMImageType, ORMUser, Paginator

from ...base import ItemCountResponseModel
from ...constants import *
from ...depends import Operation, current_user, get_db
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
    tags=["project images"],
    prefix="/{project_id}/images",
)


def log_operation_debug_info(operation: str, info: Any):
    log_operation_debug_info_to("api.images", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.images", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.images", operation, reason, **kwargs)


@dataclass
class FilterImagesRequestModel:
    engines: Optional[Set[ORMEngineID]] = Query(None)
    # statuses: Optional[Set[ORMImageStatus]] = Query(None)
    # image_type: Optional[ORMImageType] = Query(None)


########################################
# Count project fuzzer images
########################################


@router.get(
    path="/count",
    status_code=HTTP_200_OK,
    description="Returns count of docker images corresponding to provided programming fuzzer engine in project",
    responses={
        HTTP_200_OK: {
            "model": ItemCountResponseModel,
            "description": "Successful response",
        },
    },
)
async def count_project_images(
    operation: str = Depends(Operation("Count project images")),
    current_user: ORMUser = Depends(current_user),
    filters: FilterImagesRequestModel = Depends(),
    project_id: str = Path(..., regex=r"^\d+$"),
    pg_size: int = Query(**pg_size_settings()),
    db: IDatabase = Depends(get_db),
):
    total_cnt = await db.images.count(
        # TODO: change to project_id=project_id, when images added
        image_type=ORMImageType.builtin,
        # statuses=filters.statuses, # TODO:
        engines=filters.engines,
    )

    total_pages = ceil(total_cnt / pg_size)
    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    log_operation_debug_info(operation, filters)

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# List project fuzzer images
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    description="Returns list of docker images corresponding to provided fuzzer type in project",
    responses={
        HTTP_200_OK: {
            "model": ListImagesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_project_images(
    operation: str = Depends(Operation("List project images")),
    current_user: ORMUser = Depends(current_user),
    filters: FilterImagesRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    pgn = Paginator(pg_num, pg_size)
    images = await db.images.list(
        paginator=pgn,
        # TODO: change to project_id=project_id, when images added
        image_type=ORMImageType.builtin,
        # statuses=filters.statuses, # TODO:
        engines=filters.engines,
    )

    response_data = ListImagesResponseModel(
        pg_num=pg_num,
        pg_size=pg_size,
        items=images,
    )

    log_operation_debug_info(operation, filters)

    log_operation_success(
        operation=operation,
        project_id=project_id,
        caller=current_user.name,
    )

    return response_data


########################################
# Get image info
########################################


@router.get(
    path="/{image_id}",
    status_code=HTTP_200_OK,
    description="Returns project image",
    responses={
        HTTP_200_OK: {
            "model": ImageResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_IMAGE_NOT_FOUND),
        },
    },
)
async def get_project_image(
    response: Response,
    operation: str = Depends(Operation("Get project image")),
    current_user: ORMUser = Depends(current_user),
    project_id: str = Path(..., regex=r"^\d+$"),
    image_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_user.name, "image_id": image_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        image = await db.images.get_by_id(
            image_id=image_id,
            project_id=project_id,
        )
    except DBImageNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_IMAGE_NOT_FOUND)

    response_data = ImageResponseModel(**image.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        image_id=image_id,
        caller=current_user.name,
    )

    return response_data
