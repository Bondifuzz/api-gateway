from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response
from starlette.status import *

from api_gateway.app.api.models.langs import (
    CreateLangRequestModel,
    LangResponseModel,
    ListLangsResponseModel,
    UpdateLangRequestModel,
)
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import (
    DBLangAlreadyExistsError,
    DBLangNotFoundError,
)
from api_gateway.app.database.orm import ORMLang, ORMLangID, ORMUser, Paginator

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
    prefix="/langs",
    tags=["langs (admin)"],
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
    log_operation_debug_info_to("api.langs", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.langs", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.langs", operation, reason, **kwargs)


########################################
# Create fuzzer lang
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": LangResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_LANG_EXISTS),
        },
    },
)
async def create_lang(
    response: Response,
    lang: CreateLangRequestModel,
    operation: str = Depends(Operation("Create fuzzer lang")),
    current_admin: ORMUser = Depends(current_admin),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"lang_id": lang.id, "caller": current_admin.name}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        created_lang = await db.langs.create(
            id=lang.id,
            display_name=lang.display_name,
        )
    except DBLangAlreadyExistsError:
        return error_response(HTTP_409_CONFLICT, E_LANG_EXISTS)

    response_data = LangResponseModel(**created_lang.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        lang_id=created_lang.id,
        lang_display_name=created_lang.display_name,
        caller=current_admin.name,
    )

    return response_data


########################################
# Get fuzzer lang
########################################


@router.get(
    path="/{lang_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": LangResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_LANG_NOT_FOUND),
        },
    },
)
async def get_lang(
    response: Response,
    operation: str = Depends(Operation("Get fuzzer lang")),
    current_admin: ORMUser = Depends(current_admin),
    lang_id: ORMLangID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "lang_id": lang_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        lang = await db.langs.get_by_id(lang_id)
    except DBLangNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_LANG_NOT_FOUND)

    response_data = LangResponseModel(**lang.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        lang_id=lang_id,
        caller=current_admin.name,
    )

    return response_data


########################################
# Update fuzzer lang
########################################


@router.patch(
    path="/{lang_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_LANG_NOT_FOUND),
        },
    },
)
async def update_lang(
    response: Response,
    lang: UpdateLangRequestModel,
    operation: str = Depends(Operation("Update fuzzer lang")),
    current_admin: ORMUser = Depends(current_admin),
    lang_id: ORMLangID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "lang_id": lang_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_lang = await db.langs.get_by_id(lang_id)
    except DBLangNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_LANG_NOT_FOUND)

    new_fields = lang.dict(exclude_unset=True)
    merged = {**old_lang.dict(), **new_fields}
    await db.langs.update(ORMLang(**merged))

    log_operation_success(
        operation=operation,
        lang_id=lang_id,
        caller=current_admin.name,
    )


########################################
# Delete fuzzer lang
########################################


@router.delete(
    path="/{lang_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_LANG_NOT_FOUND),
        },
    },
)
async def delete_lang(
    response: Response,
    operation: str = Depends(Operation("Delete fuzzer lang")),
    current_admin: ORMUser = Depends(current_admin),
    lang_id: ORMLangID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "lang_id": lang_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        lang = await db.langs.get_by_id(lang_id)

    except DBLangNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_LANG_NOT_FOUND)

    affected_fuzzers = await db.fuzzers.list(
        langs={lang.id},
    )

    if len(affected_fuzzers) > 0:
        return error_response(HTTP_409_CONFLICT, E_LANG_IN_USE_BY, affected_fuzzers)

    await db.langs.delete(lang)

    log_operation_success(
        operation=operation,
        lang_id=lang_id,
        caller=current_admin.name,
    )


########################################
# List fuzzer langs
########################################


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListLangsResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_langs(
    operation: str = Depends(Operation("List fuzzer langs")),
    current_admin: ORMUser = Depends(current_admin),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    langs = await db.langs.list(
        paginator=Paginator(pg_num, pg_size),
    )

    response_data = ListLangsResponseModel(pg_num=pg_num, pg_size=pg_size, items=langs)

    log_operation_success(operation, caller=current_admin.name)

    return response_data
