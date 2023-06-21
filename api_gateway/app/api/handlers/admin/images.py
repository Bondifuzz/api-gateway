from contextlib import suppress
from dataclasses import dataclass
from math import ceil
from typing import Any, Optional, Set

from starlette.status import *
from api_gateway.app.api.models.images import (
    CreateImageRequestModel,
    ImageResponseModel,
    ListImagesResponseModel,
    UpdateImageRequestModel,
)

from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import DBEnginesNotFoundError, DBImageNotFoundError
from api_gateway.app.database.orm import (
    ORMEngineID,
    ORMImage,
    ORMImageStatus,
    ORMImageType,
    ORMUser,
    Paginator,
)
from fastapi import APIRouter, Depends, Path, Query, Response

from ...base import (
    ItemCountResponseModel,
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
    prefix="/images",
    tags=["images (admin)"],
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
    log_operation_debug_info_to("api.images", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.images", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.images", operation, reason, **kwargs)


########################################
# Create built-in image
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": ImageResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_IMAGE_EXISTS),
        },
    },
)
async def create_builtin_image(
    response: Response,
    image: CreateImageRequestModel,
    operation: str = Depends(Operation("Create built-in image")),
    current_admin: ORMUser = Depends(current_admin),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int, params: Optional[list] = None):
        kw = {"image": image.name, "caller": current_admin.name}
        rfail = error_model(error_code, params)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    with suppress(DBImageNotFoundError):
        await db.images.get_by_name(image.name, None)
        return error_response(HTTP_409_CONFLICT, E_IMAGE_EXISTS)

    try:
        created_image = await db.images.create(
            name=image.name,
            description=image.description,
            project_id=None,
            engines=image.engines,
            status=ORMImageStatus.ready,
        )

    except DBEnginesNotFoundError as e:
        return error_response(HTTP_409_CONFLICT, E_ENGINES_INVALID, e.engines)

    response_data = ImageResponseModel(**created_image.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        image_id=created_image.id,
        image_name=created_image.name,
        caller=current_admin.name,
    )

    return response_data


########################################
# Count built-in images
########################################


@dataclass
class FilterImagesRequestModel:
    engines: Optional[Set[ORMEngineID]] = Query(None)
    statuses: Optional[Set[ORMImageStatus]] = Query(None)
    image_type: Optional[ORMImageType] = Query(None)


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
async def get_builtin_image_count(
    operation: str = Depends(Operation("Get built-in image count")),
    current_admin: ORMUser = Depends(current_admin),
    filters: FilterImagesRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    db: IDatabase = Depends(get_db),
):
    total_cnt = await db.images.count(
        engines=filters.engines,
        statuses=filters.statuses,
        image_type=filters.image_type,
    )
    total_pages = ceil(total_cnt / pg_size)

    response_data = ItemCountResponseModel(
        pg_size=pg_size, pg_total=total_pages, cnt_total=total_cnt
    )

    dbg_info = [filters, response_data]
    log_operation_debug_info(operation, dbg_info)
    log_operation_success(operation, caller=current_admin.name)

    return response_data


########################################
# Get built-in image
########################################


@router.get(
    path="/{image_id}",
    status_code=HTTP_200_OK,
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
async def get_builtin_image(
    response: Response,
    operation: str = Depends(Operation("Get built-in image")),
    current_admin: ORMUser = Depends(current_admin),
    image_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "image_id": image_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        image = await db.images.get_by_id(image_id)
    except DBImageNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_IMAGE_NOT_FOUND)

    response_data = ImageResponseModel(**image.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        image_id=image_id,
        caller=current_admin.name,
    )

    return response_data


########################################
# Update built-in image
########################################


@router.patch(
    path="/{image_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_IMAGE_NOT_FOUND),
        },
    },
)
async def update_builtin_image(
    response: Response,
    image: UpdateImageRequestModel,
    operation: str = Depends(Operation("Update built-in image")),
    current_admin: ORMUser = Depends(current_admin),
    image_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "image_id": image_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_image = await db.images.get_by_id(image_id)
    except DBImageNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_IMAGE_NOT_FOUND)

    if image.name is not None:
        with suppress(DBImageNotFoundError):
            await db.images.get_by_name(image.name, None)
            return error_response(HTTP_409_CONFLICT, E_IMAGE_EXISTS)

    new_fields = image.dict(exclude_unset=True)
    merged = {**old_image.dict(), **new_fields}
    await db.images.update(ORMImage(**merged))

    log_operation_success(
        operation=operation,
        image_id=image_id,
        caller=current_admin.name,
    )


########################################
# Delete built-in image
########################################


@router.delete(
    path="/{image_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_IMAGE_NOT_FOUND),
        },
    },
)
async def delete_builtin_image(
    response: Response,
    operation: str = Depends(Operation("Delete built-in image")),
    current_admin: ORMUser = Depends(current_admin),
    image_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "image_id": image_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        image = await db.images.get_by_id(image_id)
        await db.images.delete(image)

    except DBImageNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_IMAGE_NOT_FOUND)

    log_operation_success(
        operation=operation,
        image_id=image_id,
        image_name=image.name,
        caller=current_admin.name,
    )


########################################
# List built-in images
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListImagesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_builtin_images(
    operation: str = Depends(Operation("List built-in images")),
    current_admin: ORMUser = Depends(current_admin),
    filters: FilterImagesRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    images = await db.images.list(
        paginator=Paginator(pg_num, pg_size),
        engines=filters.engines,
        statuses=filters.statuses,
        image_type=filters.image_type,
    )

    response_data = ListImagesResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=images
    )

    dbg_info = [filters]
    log_operation_debug_info(operation, dbg_info)
    log_operation_success(operation, caller=current_admin.name)

    return response_data
