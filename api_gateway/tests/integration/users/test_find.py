from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMUser
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import (
    NO_SUCH_ID,
    USER_FIELDS,
    LoginModel,
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
        1) Logged user can get self information
        2) Logged admin can get information of any user

    Succeeds
        If all checks were passed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create admin
    admin_user = gen_admin_user()
    resp = test_client.post(app.url_path_for("create_user"), json=admin_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    admin_id = resp.json()["id"]

    # Create normal user
    usual_user = gen_usual_user()
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    user_id = resp.json()["id"]

    #
    # Check admin
    #

    # Login as admin
    admin_login_data = get_login_data(admin_user)
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Get self info (ok)
    resp = test_client.get(app.url_path_for("get_user", user_id=admin_id))
    assert resp.status_code == HTTP_200_OK

    # Get other user info (ok)
    resp = test_client.get(app.url_path_for("get_user", user_id=user_id))
    assert resp.status_code == HTTP_200_OK

    #
    # Check user
    #

    # Login as normal user
    usual_login_data = get_login_data(usual_user)
    resp = test_client.post(app.url_path_for("login"), json=usual_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Get self info (fail)
    resp = test_client.get(app.url_path_for("get_user", user_id=user_id))
    json = resp.json()
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert json["code"] == E_ADMIN_REQUIRED

    # Get other user info (fail)
    resp = test_client.get(app.url_path_for("get_user", user_id=admin_id))
    json = resp.json()
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert json["code"] == E_ADMIN_REQUIRED


def test_get_user_ok(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
    trashbin_user: ORMUser,
    erasing_user: ORMUser,
):
    """
    Description
        Try to get present/trashbin user

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_get_user(user_id: str):
        # Get user
        url = app.url_path_for("get_user", user_id=user_id)
        resp = test_client.get(url)

        # Ensure record found and has data fields
        assert resp.status_code == HTTP_200_OK
        assert all(k in resp.json() for k in USER_FIELDS)

    _assert_get_user(present_user.id)
    _assert_get_user(trashbin_user.id)
    _assert_get_user(erasing_user.id)


def test_get_user_fail(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
):
    """
    Description
        Try to get non existent/erasing user

    Succeeds
        If get operation failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_get_user(user_id: str, status: int, code: int):
        # Get user
        url = app.url_path_for("get_user", user_id=user_id)
        resp = test_client.get(url)

        # Ensure get operation failed
        assert resp.status_code == status
        assert resp.json()["code"] == code

    _assert_get_user(NO_SUCH_ID, HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)
