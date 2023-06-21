from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMUser
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import (
    NO_SUCH_ID,
    LoginModel,
    UserModel,
    UserUpdateModel,
    gen_admin_user,
    gen_usual_user,
    get_login_data,
    random_string,
)


def test_access_modify_user(
    app: FastAPI, test_client: TestClient, root_login_data: LoginModel
):
    """
    Description
        Checks that:
        1) Administrator can modify usual user and himself
        2) Administrator can't modify another administrator
        3) System administrator can modify usual user, administrator and himself

    Succeeds
        If all checks were passed
    """

    def try_update(user_id):
        updates = UserUpdateModel(display_name=random_string())
        url = app.url_path_for("update_user", user_id=user_id)
        resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
        return resp.status_code

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
    created_user = create_user(gen_usual_user())

    # (3) Root: update user
    status_code = try_update(created_user["id"])
    assert status_code == HTTP_200_OK

    # (3) Root: update admin
    status_code = try_update(created_admin2["id"])
    assert status_code == HTTP_200_OK

    # (3) Root: update self
    status_code = try_update(logged_in_root["user_id"])
    assert status_code == HTTP_200_OK

    # Login as admin
    admin_login_data = get_login_data(admin_user1)
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # (2) Admin: update another admin - fail
    status_code = try_update(created_admin2["id"])
    assert status_code == HTTP_403_FORBIDDEN

    # (1) Admin: update user
    status_code = try_update(created_user["id"])
    assert status_code == HTTP_200_OK

    # (1) Admin: update self
    status_code = try_update(created_admin1["id"])
    assert status_code == HTTP_200_OK


def test_modify_user_ok(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
):
    """
    Description
        Try to modify user

    Succeeds
        If no errors were encountered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Update user
    updated_name = "bob"
    updates = UserUpdateModel(name=updated_name)
    url = app.url_path_for("update_user", user_id=present_user.id)
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure changes are correct (in response)
    assert json["old"] == dict(name=present_user.name)
    assert json["new"] == dict(name=updated_name)

    # Get user
    url = app.url_path_for("get_user", user_id=present_user.id)
    resp = test_client.get(url)
    assert resp.status_code == HTTP_200_OK

    # Ensure changes are correct (in fact)
    assert resp.json()["name"] == updated_name


def test_modify_user_fail(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    trashbin_user: ORMUser,
    erasing_user: ORMUser,
):
    """
    Description
        Try to modify non existent user

    Succeeds
        If modify operation failed
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_modify_user(user_id: str, status: int, code: int):
        # Update user which does not exist
        updates = UserUpdateModel(name="aaa")
        url = app.url_path_for("update_user", user_id=user_id)
        resp = test_client.patch(url, json=updates.dict(exclude_unset=True))

        # Ensure update operation failed
        assert resp.status_code == status
        assert resp.json()["code"] == code

    _assert_modify_user(NO_SUCH_ID, HTTP_404_NOT_FOUND, E_USER_NOT_FOUND)
    _assert_modify_user(trashbin_user.id, HTTP_409_CONFLICT, E_USER_DELETED)
    _assert_modify_user(erasing_user.id, HTTP_409_CONFLICT, E_USER_DELETED)


def test_modify_user_username_exists(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_user: ORMUser,
):
    """
    Description
        Try to modify user and update his username
        with another username of existent user

    Succeeds
        If modify operation failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Try to update user name to used name(admin name)
    updates = UserUpdateModel(name=admin_login_data.username)
    url = app.url_path_for("update_user", user_id=present_user.id)
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))

    # Ensure update failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert resp.json()["code"] == E_USER_EXISTS
