from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from starlette.status import *

from api_gateway.app.api.error_codes import *

from ..conftest import USER_FIELDS, LoginModel


def test_self_info_unauthorized(app: FastAPI, test_client: TestClient):
    """
    Description
        Get self info

    Succeeds
        If all checks were passed
    """

    # Get self info (fail)
    resp = test_client.get(app.url_path_for("get_self_user"))
    json = resp.json()

    # Ensure operation failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_AUTHORIZATION_REQUIRED


def test_self_info_ok(
    app: FastAPI,
    test_client: TestClient,
    sys_admin_login_data: LoginModel,
    admin_login_data: LoginModel,
    user_login_data: LoginModel,
):
    """
    Description
        Get self info as admin

    Succeeds
        If all checks were passed
    """

    def _assert_get_self_user(login_data: LoginModel):

        # Login as admin
        resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
        assert resp.status_code == HTTP_200_OK

        # Get self info (ok)
        resp = test_client.get(app.url_path_for("get_self_user"))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        # Ensure response correct
        assert all(k in json for k in USER_FIELDS)
        assert json["name"] == login_data.username

    _assert_get_self_user(sys_admin_login_data)
    _assert_get_self_user(admin_login_data)
    _assert_get_self_user(user_login_data)
