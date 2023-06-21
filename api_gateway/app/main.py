from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from mqtransport.errors import MQTransportError
from pydantic import ValidationError

from api_gateway.app.api.handlers.auth.device_cookie import DeviceCookieManager
from api_gateway.app.api.handlers.security.csrf import CSRFTokenManager
from api_gateway.app.background.manager import BackgroundTaskManager
from api_gateway.app.background.tasks.user_lockout import (
    FailedLoginCounter,
    UserLockoutCleaner,
)
from api_gateway.app.external_api.external_api import ExternalAPI
from api_gateway.app.middlewares import register_middlewares
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

try:
    import orjson  # type: ignore
except ModuleNotFoundError:
    from fastapi.responses import JSONResponse
else:
    from fastapi.responses import ORJSONResponse as JSONResponse

import json
import logging
import sys

from starlette.status import (
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from api_gateway.app.api.error_codes import E_INTERNAL_ERROR, E_WRONG_REQUEST
from api_gateway.app.api.error_model import (
    DependencyException,
    ErrorModel,
    error_body,
    error_model,
)
from api_gateway.app.database.errors import DatabaseError
from api_gateway.app.external_api.errors import ExternalAPIError
from api_gateway.app.object_storage.errors import ObjectStorageError

from .api import handlers as api_handlers
from .database.instance import db_init
from .message_queue.instance import mq_init
from .object_storage import ObjectStorage
from .settings import AppSettings, load_app_settings

if TYPE_CHECKING:
    from mqtransport import MQApp

    from .database.abstract import IDatabase

# override fastapi 422 schema
import fastapi.openapi.utils as fu
fu.validation_error_response_definition = ErrorModel.schema()


def configure_exception_handlers(app: FastAPI):
    def error_response(request: Request):
        content = error_body(E_INTERNAL_ERROR)
        return JSONResponse(content, HTTP_500_INTERNAL_SERVER_ERROR)

    @app.exception_handler(ObjectStorageError)
    async def exception_handler(request: Request, e: ObjectStorageError):
        operation = "None"
        with suppress(AttributeError):
            operation = request.state.operation
        route = f"{request.method} {request.url.path}"
        msg = "Unexpected S3 error: %s. Operation: '%s'. Route: '%s'"
        logging.getLogger("s3").error(msg, e, operation, route)
        return error_response(request)

    @app.exception_handler(DatabaseError)
    async def exception_handler(request: Request, e: DatabaseError):
        operation = "None"
        with suppress(AttributeError):
            operation = request.state.operation
        route = f"{request.method} {request.url.path}"
        msg = "Unexpected DB error: %s. Operation: '%s'. Route: '%s'"
        logging.getLogger("db").error(msg, e, operation, route)
        return error_response(request)

    @app.exception_handler(MQTransportError)
    async def exception_handler(request: Request, e: MQTransportError):
        operation = "None"
        with suppress(AttributeError):
            operation = request.state.operation
        route = f"{request.method} {request.url.path}"
        msg = "Unexpected MQ error: %s. Operation: '%s'. Route: '%s'"
        logging.getLogger("mq").error(msg, e, operation, route)
        return error_response(request)

    @app.exception_handler(ExternalAPIError)
    async def exception_handler(request: Request, e: ExternalAPIError):
        operation = "None"
        with suppress(AttributeError):
            operation = request.state.operation
        route = f"{request.method} {request.url.path}"
        msg = "Unexpected external API error: %s. Operation: '%s'. Route: '%s'"
        logging.getLogger("api.external").error(msg, e, operation, route)
        return error_response(request)

    @app.exception_handler(HTTPException)
    async def exception_handler(request: Request, e: HTTPException):
        route = f"{request.method} {request.url.path}"
        msg = "Unhandled HTTPException. Route: '%s'"
        logging.getLogger("main").exception(msg, route, exc_info=e)
        return error_response(request)

    @app.exception_handler(RequestValidationError)
    async def exception_handler(request: Request, e: ValidationError):
        # TODO: debug this
        params = []
        for err in e.errors():
            params.append(".".join(err["loc"]) + ": " + err["msg"])

        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_model(E_WRONG_REQUEST, params).dict(),
        )

    @app.exception_handler(DependencyException)
    async def exception_handler(request: Request, e: DependencyException):

        operation = "None"
        with suppress(AttributeError):
            operation = request.state.operation

        route = f"{request.method} {request.url.path}"
        msg = "API error: %s. Operation: '%s'. Route: '%s'"
        logging.getLogger("depends").debug(msg, e, operation, route)

        return JSONResponse(
            status_code=e.response_code,
            content=error_model(e.error_code).dict(),
        )


def configure_startup_events(app: FastAPI, settings: AppSettings):

    logger = logging.getLogger("main")

    @app.on_event("startup")
    async def init_csrf_token_manager():
        logger.info("Configuring CSRF token manager...")
        app.state.csrf_token_manager = CSRFTokenManager(settings)
        logger.info("Configuring CSRF token manager... OK")

    @app.on_event("startup")
    async def init_device_cookie_manager():
        logger.info("Configuring device cookie manager...")
        app.state.device_cookie_manager = DeviceCookieManager(settings)
        logger.info("Configuring device cookie manager... OK")

    @app.on_event("startup")
    async def init_external_api():
        logger.info("Configuring external API sessions...")
        app.state.external_api = await ExternalAPI.create(settings)
        logger.info("Configuring external API sessions... OK")

    @app.on_event("startup")
    async def init_object_storage():
        logger.info("Configuring object storage...")
        app.state.s3 = await ObjectStorage.create(settings)
        logger.info("Configuring object storage... OK")

    @app.on_event("startup")
    async def init_database():
        logger.info("Configuring database...")
        app.state.db = await db_init(settings)
        logger.info("Configuring database... OK")

    @app.on_event("startup")
    async def init_message_queue():
        logger.info("Configuring message queue...")
        mq_app = await mq_init(settings)
        mq_app.state.s3 = app.state.s3
        mq_app.state.db = app.state.db
        mq_app.state.settings = settings
        mq_app.state.fastapi = app
        app.state.mq = mq_app
        logger.info("Configuring message queue... OK")

    @app.on_event("startup")
    async def init_background_task_manager():
        logger.info("Starting background tasks...")
        bg_task_mgr = BackgroundTaskManager()
        bg_task_mgr.add_task(FailedLoginCounter(settings))
        bg_task_mgr.add_task(UserLockoutCleaner(settings, app.state.db))
        app.state.bg_task_mgr = bg_task_mgr
        bg_task_mgr.start_tasks()
        logger.info("Starting background tasks... OK")

    @app.on_event("startup")
    async def import_unsent_messages_then_run():
        db: IDatabase = app.state.db
        mq_app: MQApp = app.state.mq
        logger.info("Loading MQ unsent messages...")
        messages = await db.unsent_mq.load_unsent_messages()
        mq_app.import_unsent_messages(messages)
        logger.info("Loading MQ unsent messages... OK")
        await mq_app.start()


def configure_shutdown_events(app: FastAPI, settings: AppSettings):

    logger = logging.getLogger("main")

    @app.on_event("shutdown")
    async def exit_background_task_manager():
        logger.info("Stopping background tasks...")
        await app.state.bg_task_mgr.stop_tasks()
        logger.info("Stopping background tasks... OK")

    @app.on_event("shutdown")
    async def exit_external_api():
        logger.info("Closing external API sessions...")
        await app.state.external_api.close()
        logger.info("Closing external API sessions... OK")

    @app.on_event("shutdown")
    async def exit_object_storage():
        logger.info("Closing object storage...")
        await app.state.s3.close()
        logger.info("Closing object storage... OK")

    @app.on_event("shutdown")
    async def exit_message_queue():
        logger.info("Closing message queue...")
        timeout = settings.environment.shutdown_timeout
        await app.state.mq.shutdown(timeout)
        logger.info("Closing message queue... OK")

    @app.on_event("shutdown")
    async def export_unsent_messages():
        db: IDatabase = app.state.db
        mq_app: MQApp = app.state.mq
        logger.info("Saving MQ unsent messages...")
        messages = mq_app.export_unsent_messages()
        await db.unsent_mq.save_unsent_messages(messages)
        logger.info("Saving MQ unsent messages... OK")

    @app.on_event("shutdown")
    async def exit_database():
        logger.info("Closing database...")
        await app.state.db.close()
        logger.info("Closing database... OK")


def add_static_file(
    app: FastAPI,
    url: str,
    filepath: str,
    media_type: str,
):

    with open(filepath, "rb") as f:
        content = f.read()

    @app.get(url, include_in_schema=False)
    async def static_file_handler():
        return HTMLResponse(content=content, media_type=media_type)


def configure_routes(app: FastAPI):

    logger = logging.getLogger("main")
    logger.info("Configuring routes...")

    pfx = "/api/v1"
    app.include_router(api_handlers.user.router, prefix=pfx)
    app.include_router(api_handlers.admin.router, prefix=pfx)
    app.include_router(api_handlers.auth.router, prefix=pfx)
    app.include_router(api_handlers.security.router, prefix=pfx)

    add_static_file(app, "/", "index.html", "text/html")
    add_static_file(app, "/favicon.ico", "favicon.ico", "image/x-icon")
    add_static_file(app, "/robots.txt", "robots.txt", "text/plain")

    # Simplify openapi.json
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name

    logger.info("Configuring routes... OK")


def configure_static_files(app: FastAPI):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.mount("/locales", StaticFiles(directory="locales"), name="locales")
    app.mount("/book", StaticFiles(directory="book"), name="book")


def generate_api_spec():

    app = FastAPI()
    configure_routes(app)

    print("Generating openapi.json...")

    with open("openapi.json", "w") as f:
        json.dump(app.openapi(), f)

    print("Generating openapi.json... OK")
    sys.exit(0)


class EmptyJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        if content is None:
            content = dict()
        return super().render(content)


def create_app():

    settings = load_app_settings()

    swagger_url = "/docs"
    if settings.environment.name == "prod":
        swagger_url = None

    app = FastAPI(
        docs_url=swagger_url,
        default_response_class=EmptyJSONResponse,
    )

    logging.info("%-16s %s", "ENVIRONMENT", settings.environment.name)
    logging.info("%-16s %s", "SERVICE_NAME", settings.environment.service_name)
    logging.info("%-16s %s", "SERVICE_VERSION", settings.environment.service_version)
    logging.info("%-16s %s", "COMMIT_ID", settings.environment.commit_id)
    logging.info("%-16s %s", "BUILD_DATE", settings.environment.build_date)
    logging.info("%-16s %s", "COMMIT_DATE", settings.environment.commit_date)
    logging.info("%-16s %s", "GIT_BRANCH", settings.environment.git_branch)

    with open("index.html") as f:
        app.state.index_html = f.read()

    configure_routes(app)
    register_middlewares(app, settings)
    configure_startup_events(app, settings)
    configure_shutdown_events(app, settings)
    configure_exception_handlers(app)
    configure_static_files(app)

    app.state.settings = settings
    return app
