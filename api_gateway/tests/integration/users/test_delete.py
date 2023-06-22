from asyncio import AbstractEventLoop

from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from starlette.status import *

from api_gateway.app.api.base import DeleteActions
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.orm import ORMUser
from api_gateway.app.utils import rfc3339_expired

from ..conftest import (
    NO_SUCH_ID,
    LoginModel,
    UserModel,
    gen_admin_user,
    gen_usual_user,
    get_login_data,
)


def test_access_check(
    app: FastAPI, test_client: TestClient, root_login_data: LoginModel
):
    """
    Description
        Checks that:
        1) Administrator can delete usual user and himself
        2) Administrator can't delete another administrator
        3) System administrator can delete both usual user and administrator
        4) System administrator can't delete himself

    Succeeds
        If all checks were passed
    """

    def create_user(user: UserModel):
        resp = test_client.post(app.url_path_for("create_user"), json=user.dict())
        assert resp.status_code == HTTP_201_CREATED
        return resp.json()

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    logged_in_root = resp.json()

    # Create users
    admin_user1 = gen_admin_user()
    created_admin1 = create_user(admin_user1)
    created_admin2 = create_user(gen_admin_user())
    created_admin3 = create_user(gen_admin_user())
    created_user1 = create_user(gen_usual_user())
    created_user2 = create_user(gen_usual_user())

    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # (4) Root: delete self
    url = app.url_path_for("delete_user", user_id=logged_in_root["user_id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_403_FORBIDDEN

    # (3) Root: delete user
    url = app.url_path_for("delete_user", user_id=created_user2["id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # (3) Root: delete admin
    url = app.url_path_for("delete_user", user_id=created_admin2["id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Login as admin
    admin_login_data = get_login_data(admin_user1)
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # (2) Admin: delete admin - fail
    url = app.url_path_for("delete_user", user_id=created_admin3["id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_403_FORBIDDEN

    # (1) Admin: delete user
    url = app.url_path_for("delete_user", user_id=created_user1["id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # (1) Admin: delete self
    url = app.url_path_for("delete_user", user_id=created_admin1["id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK


def test_delete_user_ok(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
):
    """
    Description
        Try to delete user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Delete user
    url = app.url_path_for("delete_user", user_id=present_user.id)
    resp = test_client.delete(url, params=dict(action=DeleteActions.delete))
    assert resp.status_code == HTTP_200_OK

    # TODO: some check?


def test_delete_user_fail(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    trashbin_user: ORMUser,
    erasing_user: ORMUser,
):
    """
    Description
        Try to delete user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_delete_user(user_id: str, status: int, code: int):
        # Erase user
        url = app.url_path_for("delete_user", user_id=user_id)
        resp = test_client.delete(url, params=dict(action=DeleteActions.delete))

        # Ensure erase operation failed
        assert resp.status_code == status
        assert resp.json()["code"] == code

    _assert_delete_user(NO_SUCH_ID, HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)
    _assert_delete_user(trashbin_user.id, HTTP_409_CONFLICT, E_USER_DELETED)
    _assert_delete_user(erasing_user.id, HTTP_409_CONFLICT, E_USER_BEING_ERASED)


def test_erase_user_ok(
    app: FastAPI,
    db: IDatabase,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
    trashbin_user: ORMUser,
    event_loop: AbstractEventLoop,
):
    """
    Description
        Try to erase user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_erase_user(user_id: int):
        # Erase user
        url = app.url_path_for("delete_user", user_id=user_id)
        resp = test_client.delete(url, params=dict(action=DeleteActions.erase))
        assert resp.status_code == HTTP_200_OK

        # Ensure that erasure_date in db correct
        db_user: ORMUser = event_loop.run_until_complete(db.users.get_by_id(user_id))
        assert db_user.erasure_date is not None
        assert rfc3339_expired(db_user.erasure_date)

    _assert_erase_user(present_user.id)
    _assert_erase_user(trashbin_user.id)


def test_erase_user_fail(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    erasing_user: ORMUser,
):
    """
    Description
        Try to erase user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_erase_user(user_id: str, status: int, code: int):
        # Erase user
        url = app.url_path_for("delete_user", user_id=user_id)
        resp = test_client.delete(url, params=dict(action=DeleteActions.erase))

        # Ensure erase operation failed
        assert resp.status_code == status
        assert resp.json()["code"] == code

    _assert_erase_user(NO_SUCH_ID, HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)
    _assert_erase_user(erasing_user.id, HTTP_409_CONFLICT, E_USER_BEING_ERASED)


def test_restore_user_ok(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    trashbin_user: ORMUser,
):
    """
    Description
        Try to restore user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Restore user
    url = app.url_path_for("delete_user", user_id=trashbin_user.id)
    resp = test_client.delete(url, params=dict(action=DeleteActions.restore))
    assert resp.status_code == HTTP_200_OK


def test_restore_user_fail(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
    erasing_user: ORMUser,
):
    """
    Description
        Try to restore user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_restore_user(user_id: str, status: int, code: int):
        # Restore user
        url = app.url_path_for("delete_user", user_id=user_id)
        resp = test_client.delete(url, params=dict(action=DeleteActions.restore))

        # Ensure erase operation failed
        assert resp.status_code == status
        assert resp.json()["code"] == code

    _assert_restore_user(NO_SUCH_ID, HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)
    _assert_restore_user(present_user.id, HTTP_409_CONFLICT, E_USER_NOT_DELETED)
    _assert_restore_user(erasing_user.id, HTTP_409_CONFLICT, E_USER_BEING_ERASED)
