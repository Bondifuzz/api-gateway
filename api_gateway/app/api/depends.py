from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from mqtransport import MQApp

    from api_gateway.app.api.handlers.security.csrf import CSRFTokenManager
    from api_gateway.app.background.tasks.user_lockout import FailedLoginCounter
    from api_gateway.app.database import IDatabase
    from api_gateway.app.external_api import ExternalAPI
    from api_gateway.app.object_storage import ObjectStorage
    from api_gateway.app.settings import AppSettings

    from .handlers.auth.device_cookie import DeviceCookieManager
else:
    MQApp = object
    ObjectStorage = object
    IDatabase = object
    DeviceCookieManager = object
    ExternalAPI = object
    AppSettings = object
    FailedLoginCounter = object
    CSRFTokenManager = object

from fastapi import Cookie, Depends, Path, Request
from starlette.status import *

from api_gateway.app.api.constants import C_MAX_COOKIE_LENGTH
from api_gateway.app.database.errors import (
    DBCookieNotFoundError,
    DBFuzzerNotFoundError,
    DBProjectNotFoundError,
    DBRevisionNotFoundError,
    DBUserNotFoundError,
)
from api_gateway.app.database.orm import ORMUser

from .error_codes import *
from .error_model import DependencyException
from .utils import check_user_status, max_length


def CookieHelper(name: str, optional: bool = False):
    return Cookie(
        alias=name,
        default=None if optional else Ellipsis,
        **max_length(C_MAX_COOKIE_LENGTH),
        include_in_schema=False,
    )


class Operation:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, request: Request) -> str:
        request.state.operation = self.name
        return self.name


def get_mq(request: Request) -> MQApp:
    return request.app.state.mq


def get_s3(request: Request) -> ObjectStorage:
    return request.app.state.s3


def get_db(request: Request) -> IDatabase:
    return request.app.state.db


def get_external_api(request: Request) -> ExternalAPI:
    return request.app.state.external_api


def get_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_login_counter(request: Request) -> FailedLoginCounter:
    return request.app.state.bg_task_mgr.get_task("FailedLoginCounter")


def get_device_cookie_mgr(request: Request) -> DeviceCookieManager:
    return request.app.state.device_cookie_manager


def get_csrf_token_mgr(request: Request) -> CSRFTokenManager:
    return request.app.state.csrf_token_manager


async def current_user(
    db: IDatabase = Depends(get_db),
    _user_id: Optional[str] = CookieHelper("USER_ID", optional=True),
    _cookie_id: Optional[str] = CookieHelper("SESSION_ID", optional=True),
) -> ORMUser:

    """Check auth"""

    def auth_error(status_code: int, error_code: int):
        raise DependencyException(status_code, error_code)

    if not _cookie_id or not _user_id:
        auth_error(HTTP_401_UNAUTHORIZED, E_AUTHORIZATION_REQUIRED)

    try:
        cookie = await db.cookies.get(_cookie_id)
    except DBCookieNotFoundError:
        auth_error(HTTP_401_UNAUTHORIZED, E_SESSION_NOT_FOUND)

    if cookie.user_id != _user_id:
        auth_error(HTTP_401_UNAUTHORIZED, E_SESSION_NOT_FOUND)

    try:
        user = await db.users.get_by_id(_user_id)
    except DBUserNotFoundError:
        auth_error(HTTP_401_UNAUTHORIZED, E_SESSION_NOT_FOUND)

    # Check if deleted, banned, etc.
    status_code, error_code = check_user_status(user)
    if error_code != E_NO_ERROR:
        auth_error(status_code, error_code)

    return user


async def current_admin(user: ORMUser = Depends(current_user)):
    if not user.is_admin:
        raise DependencyException(HTTP_403_FORBIDDEN, E_ADMIN_REQUIRED)
    return user


async def current_system_admin(admin: ORMUser = Depends(current_admin)):
    if not admin.is_system:
        raise DependencyException(HTTP_403_FORBIDDEN, E_SYSTEM_ADMIN_REQUIRED)
    return admin


async def check_user_exists(
    request: Request,
    user_id: str = Path(..., regex=r"^\d+$"),
    current_user: ORMUser = Depends(current_user),
    db: IDatabase = Depends(get_db),
):
    if current_user.id == user_id:
        return

    try:
        user = await db.users.get_by_id(user_id)
        if user.erasure_date and request.method.upper() not in ["GET", "DELETE"]:
            raise DependencyException(HTTP_409_CONFLICT, E_USER_DELETED)

    except DBUserNotFoundError:
        raise DependencyException(HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)


async def check_client_is_not_admin(
    user_id: str = Path(..., regex=r"^\d+$"),
    current_user: ORMUser = Depends(current_user),
):
    if current_user.is_admin:
        if current_user.id == user_id:
            raise DependencyException(HTTP_403_FORBIDDEN, E_CLIENT_ACCOUNT_REQUIRED)


async def check_user_access_permissions(
    user_id: str = Path(..., regex=r"^\d+$"),
    current_user: ORMUser = Depends(current_user),
):
    if not current_user.is_admin:
        if current_user.id != user_id:
            raise DependencyException(HTTP_403_FORBIDDEN, E_ACCESS_DENIED)


async def parent_project(request: Request):
    return request.state.project


async def check_parent_project(
    request: Request,
    user_id: str = Path(..., regex=r"^\d+$"),
    project_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    try:
        project = await db.projects.get_by_id(project_id, user_id)
        request.state.project = project

        if project.erasure_date and request.method.upper() not in ["GET", "DELETE"]:
            raise DependencyException(HTTP_409_CONFLICT, E_PROJECT_DELETED)

    except DBProjectNotFoundError:
        raise DependencyException(HTTP_404_NOT_FOUND, E_PROJECT_NOT_FOUND)


async def parent_fuzzer(request: Request):
    return request.state.fuzzer


async def check_parent_fuzzer(
    request: Request,
    project_id: str = Path(..., regex=r"^\d+$"),
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    try:
        fuzzer = await db.fuzzers.get_by_id(fuzzer_id, project_id)
        request.state.fuzzer = fuzzer

        if fuzzer.erasure_date and request.method.upper() not in ["GET", "DELETE"]:
            raise DependencyException(HTTP_409_CONFLICT, E_FUZZER_DELETED)

    except DBFuzzerNotFoundError:
        raise DependencyException(HTTP_404_NOT_FOUND, E_FUZZER_NOT_FOUND)


async def parent_revision(request: Request):
    return request.state.revision


async def check_parent_revision(
    request: Request,
    fuzzer_id: str = Path(..., regex=r"^\d+$"),
    revision_id: str = Path(..., regex=r"^\d+$"),
    db: IDatabase = Depends(get_db),
):
    try:
        revision = await db.revisions.get_by_id(revision_id, fuzzer_id)
        request.state.revision = revision

        if revision.erasure_date and request.method.upper() not in ["GET", "DELETE"]:
            raise DependencyException(HTTP_409_CONFLICT, E_REVISION_DELETED)

    except DBRevisionNotFoundError:
        raise DependencyException(HTTP_404_NOT_FOUND, E_REVISION_NOT_FOUND)
