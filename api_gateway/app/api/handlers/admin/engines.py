from dataclasses import dataclass
from typing import Any, List, Optional

from starlette.status import *
from api_gateway.app.api.models.engines import (
    CreateEngineRequestModel,
    EngineResponseModel,
    ListEnginesResponseModel,
    UpdateEngineRequestModel,
)

from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.errors import (
    DBEngineAlreadyExistsError,
    DBEngineNotFoundError,
    DBLangAlreadyEnabledError,
    DBLangNotEnabledError,
    DBLangsNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMEngineID,
    ORMEngine,
    ORMLangID,
    ORMUser,
    Paginator,
)
from fastapi import APIRouter, Depends, Path, Query, Response

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
    prefix="/engines",
    tags=["engines (admin)"],
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
    log_operation_debug_info_to("api.engines", operation, info)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.engines", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.engines", operation, reason, **kwargs)


########################################
# Create fuzzing engine
########################################


@router.post(
    path="",
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            "model": EngineResponseModel,
            "description": "Successful response",
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_EXISTS),
        },
    },
)
async def create_engine(
    response: Response,
    engine: CreateEngineRequestModel,
    operation: str = Depends(Operation("Create fuzzing engine")),
    current_admin: ORMUser = Depends(current_admin),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int, params: Optional[list] = None):
        kw = {"engine_id": engine.id, "caller": current_admin.name}
        rfail = error_model(error_code, params)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        created_engine = await db.engines.create(
            id=engine.id,
            display_name=engine.display_name,
            lang_ids=engine.langs,
        )

    except DBEngineAlreadyExistsError:
        return error_response(HTTP_409_CONFLICT, E_ENGINE_EXISTS)

    except DBLangsNotFoundError as e:
        return error_response(HTTP_409_CONFLICT, E_LANGS_INVALID, e.langs)
        
    response_data = EngineResponseModel(**created_engine.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        engine_id=created_engine.id,
        engine_display_name=created_engine.display_name,
        caller=current_admin.name,
    )

    return response_data


########################################
# Get fuzzing engine
########################################


@router.get(
    path="/{engine_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": EngineResponseModel,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_NOT_FOUND),
        },
    },
)
async def get_engine(
    response: Response,
    operation: str = Depends(Operation("Get fuzzing engine")),
    current_admin: ORMUser = Depends(current_admin),
    engine_id: ORMEngineID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "engine_id": engine_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        engine = await db.engines.get_by_id(engine_id)
    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)

    response_data = EngineResponseModel(**engine.dict())
    log_operation_debug_info(operation, response_data)

    log_operation_success(
        operation=operation,
        engine_id=engine_id,
        caller=current_admin.name,
    )

    return response_data


########################################
# Update fuzzing engine
########################################


@router.patch(
    path="/{engine_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_NOT_FOUND),
        },
    },
)
async def update_engine(
    response: Response,
    engine: UpdateEngineRequestModel,
    operation: str = Depends(Operation("Update fuzzing engine")),
    current_admin: ORMUser = Depends(current_admin),
    engine_id: ORMEngineID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "engine_id": engine_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        old_engine = await db.engines.get_by_id(engine_id)
    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)

    new_fields = engine.dict(exclude_unset=True)
    merged = {**old_engine.dict(), **new_fields}
    await db.engines.update(ORMEngine(**merged))

    log_operation_success(
        operation=operation,
        engine_id=engine_id,
        caller=current_admin.name,
    )


########################################
# Set fuzzing engine langs
########################################


@router.put(
    path="/{engine_id}/langs",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_NOT_FOUND),
        },
    },
)
async def set_engine_langs(
    response: Response,
    langs: List[ORMLangID],
    operation: str = Depends(Operation("Set fuzzing engine langs")),
    current_admin: ORMUser = Depends(current_admin),
    engine_id: ORMEngineID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int, params: Optional[list] = None):
        kw = {"caller": current_admin.name, "engine_id": engine_id}
        rfail = error_model(error_code, params)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        engine = await db.engines.get_by_id(engine_id)
        await db.engines.set_langs(engine, langs)

    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)

    except DBLangsNotFoundError as e:
        return error_response(HTTP_409_CONFLICT, E_LANGS_INVALID, e.langs)

    log_operation_debug_info(operation, langs)

    log_operation_success(
        operation=operation,
        engine_id=engine_id,
        caller=current_admin.name,
    )


########################################
# Enable fuzzing engine lang
########################################


@router.post(
    path="/{engine_id}/langs/{lang}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_NOT_FOUND),
        },
        HTTP_409_CONFLICT: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_LANG_ALREADY_ENABLED),
        },
    },
)
async def enable_engine_lang(
    response: Response,
    operation: str = Depends(Operation("Enable fuzzing engine lang")),
    current_admin: ORMUser = Depends(current_admin),
    engine_id: ORMEngineID = Path(...),
    lang: ORMLangID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "engine_id": engine_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        engine = await db.engines.get_by_id(engine_id)
        await db.engines.enable_lang(engine, lang)
    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)
    except DBLangAlreadyEnabledError:
        return error_response(HTTP_409_CONFLICT, E_ENGINE_LANG_ALREADY_ENABLED)

    log_operation_debug_info(operation, lang)

    log_operation_success(
        operation=operation,
        engine_id=engine_id,
        caller=current_admin.name,
    )


########################################
# Disable fuzzing engine lang
########################################


@router.delete(
    path="/{engine_id}/langs/{lang}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_NOT_FOUND, E_ENGINE_LANG_NOT_ENABLED),
        },
    },
)
async def disable_engine_lang(
    response: Response,
    operation: str = Depends(Operation("Disable fuzzing engine lang")),
    current_admin: ORMUser = Depends(current_admin),
    engine_id: ORMEngineID = Path(...),
    lang: ORMLangID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int):
        kw = {"caller": current_admin.name, "engine_id": engine_id}
        rfail = error_model(error_code)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        engine = await db.engines.get_by_id(engine_id)
        await db.engines.disable_lang(engine, lang)
    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)
    except DBLangNotEnabledError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_LANG_NOT_ENABLED)

    log_operation_debug_info(operation, lang)

    log_operation_success(
        operation=operation,
        engine_id=engine_id,
        caller=current_admin.name,
    )


########################################
# Delete fuzzing engine
########################################


@router.delete(
    path="/{engine_id}",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": None,
            "description": "Successful response",
        },
        HTTP_404_NOT_FOUND: {
            "model": ErrorModel,
            "description": error_msg(E_ENGINE_NOT_FOUND),
        },
    },
)
async def delete_engine(
    response: Response,
    operation: str = Depends(Operation("Delete fuzzing engine")),
    current_admin: ORMUser = Depends(current_admin),
    engine_id: ORMEngineID = Path(...),
    db: IDatabase = Depends(get_db),
):
    def error_response(status_code: int, error_code: int, params: Optional[list] = None):
        kw = {"caller": current_admin.name, "engine_id": engine_id}
        rfail = error_model(error_code, params)
        log_operation_error(operation, rfail, **kw)
        response.status_code = status_code
        return rfail

    try:
        engine = await db.engines.get_by_id(engine_id)

    except DBEngineNotFoundError:
        return error_response(HTTP_404_NOT_FOUND, E_ENGINE_NOT_FOUND)

    affected_fuzzers = await db.fuzzers.list(
        engines={engine.id},
    )
    
    if len(affected_fuzzers) > 0:
        return error_response(HTTP_409_CONFLICT, E_ENGINE_IN_USE_BY, affected_fuzzers)

    await db.engines.delete(engine)

    log_operation_success(
        operation=operation,
        engine_id=engine_id,
        caller=current_admin.name,
    )


########################################
# List fuzzing engines
########################################


@dataclass
class FilterEnginesRequestModel:
    lang: Optional[ORMLangID] = Query(None)


@router.get(
    path="",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "model": ListEnginesResponseModel,
            "description": "Successful response",
        },
    },
)
async def list_engines(
    operation: str = Depends(Operation("List fuzzing engines")),
    current_admin: ORMUser = Depends(current_admin),
    filters: FilterEnginesRequestModel = Depends(),
    pg_size: int = Query(**pg_size_settings()),
    pg_num: int = Query(**pg_num_settings()),
    db: IDatabase = Depends(get_db),
):
    engines = await db.engines.list(
        paginator=Paginator(pg_num, pg_size),
        lang_id=filters.lang,
    )

    response_data = ListEnginesResponseModel(
        pg_num=pg_num, pg_size=pg_size, items=engines
    )

    log_operation_debug_info(operation, [filters])
    log_operation_success(operation, caller=current_admin.name)

    return response_data
