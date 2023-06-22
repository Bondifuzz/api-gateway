from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMUser

from ..conftest import LoginModel, gen_admin_user, gen_usual_user, get_login_data


def test_access_check(
    app: FastAPI,
    test_client: TestClient,
    sys_admin_login_data: LoginModel,
):
    """
    Description
        Checks that:
        1) Administrator can create usual user
        2) Administrator can't create another administrator
        3) System administrator can create both usual user and administrator
        4) System administrator can't create another system administrator

    Succeeds
        If all checks were passed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=sys_admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # (3) Create user
    usual_user1 = gen_usual_user()
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user1.dict())
    assert resp.status_code == HTTP_201_CREATED

    # (3) Create admin
    admin_user1 = gen_admin_user()
    resp = test_client.post(app.url_path_for("create_user"), json=admin_user1.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Login as admin
    admin_login_data = get_login_data(admin_user1)
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user (1)
    usual_user2 = gen_usual_user()
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user2.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Create admin (2) - fail
    admin_user2 = gen_admin_user()
    resp = test_client.post(app.url_path_for("create_user"), json=admin_user2.dict())
    assert resp.status_code == HTTP_403_FORBIDDEN

    # (4) No `is_system` field in CreateUserRequestModel
    # So, nobody is possible to create system users


def test_create_user_ok(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
):
    """
    Description
        Create user with provided API.
        Then checks that user was created correctly.

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create usual user
    usual_user = gen_usual_user()
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED

    # TODO: check user by get info or by login?


def test_create_user_already_exists(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
    trashbin_user: ORMUser,
    erasing_user: ORMUser,
):
    """
    Description
        Try to create user with username that in use

    Succeeds
        If creation failed
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_create_user(username: str):
        # Try to create user
        user_login_data = gen_usual_user()
        user_login_data.name = username
        resp = test_client.post(
            app.url_path_for("create_user"), json=user_login_data.dict()
        )

        # Ensure creation failed
        assert resp.status_code == HTTP_409_CONFLICT
        assert resp.json()["code"] == E_USER_EXISTS

    _assert_create_user(present_user.name)
    _assert_create_user(trashbin_user.name)
    _assert_create_user(erasing_user.name)
