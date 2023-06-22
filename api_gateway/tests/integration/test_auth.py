from typing import Dict

from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from requests.cookies import RequestsCookieJar
from starlette.status import *

from api_gateway.app.api.base import DeleteActions
from api_gateway.app.api.error_codes import *

from .conftest import LoginModel, UserModel, UserUpdateModel, get_login_data


def test_login_ok(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
):
    """
    Description
        Try to log in.

    Succeeds
        If login was successful
    """

    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    user_id = resp.json()["user_id"]

    cookies: Dict[str, str] = test_client.cookies.get_dict()
    assert all(cookie in cookies for cookie in ["SESSION_ID", "USER_ID"])
    assert cookies["USER_ID"] == user_id


def test_login_invalid_username(
    app: FastAPI,
    test_client: TestClient,
    user_login_data: LoginModel,
):
    """
    Description
        Try to log in with invalid username

    Succeeds
        If login failed
    """

    user_login_data.username = "no-such-username"
    resp = test_client.post(app.url_path_for("login"), json=user_login_data.dict())
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert resp.json()["code"] == E_LOGIN_FAILED


def test_login_invalid_password(
    app: FastAPI,
    test_client: TestClient,
    user_login_data: LoginModel,
):
    """
    Description
        Try to log in with invalid password

    Succeeds
        If login failed and error encountered
    """

    user_login_data.password = "invalid-password"
    resp = test_client.post(app.url_path_for("login"), json=user_login_data.dict())
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert resp.json()["code"] == E_LOGIN_FAILED


def test_login_user_not_confirmed(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Try to login to unconfirmed account

    Succeeds
        If login failed and error encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Make user unconfirmed
    updates = UserUpdateModel(is_confirmed=False)
    url = app.url_path_for("update_user", user_id=json["id"])
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK

    # Try to login as user
    login_data = get_login_data(usual_user)
    resp = test_client.post(app.url_path_for("login"), json=login_data.dict())

    # Ensure login failed
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert resp.json()["code"] == E_ACCOUNT_NOT_CONFIRMED


def test_login_user_deleted(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Try to login to deleted account

    Succeeds
        If login failed and error encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Delete user
    body_params_delete = dict(action=DeleteActions.delete)
    url = app.url_path_for("delete_user", user_id=json["id"])
    resp = test_client.delete(url, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Try to login as user
    login_data = get_login_data(usual_user)
    resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
    json = resp.json()

    # Ensure login failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_LOGIN_FAILED

    # Try to login as user
    login_data.password = "invalid-password"
    resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
    json = resp.json()

    # Ensure login failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_LOGIN_FAILED


def test_login_user_disabled(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Try to login to disabled account

    Succeeds
        If login failed and error encountered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Make user disabled
    updates = UserUpdateModel(is_disabled=True)
    url = app.url_path_for("update_user", user_id=json["id"])
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK

    # Try to login as user
    login_data = get_login_data(usual_user)
    resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
    json = resp.json()

    # Ensure login failed
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert json["code"] == E_ACCOUNT_DISABLED


def test_cookie_login_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Try to log in, using cookie.

    Succeeds
        If login was successful
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Try to create user
    # Requests (TestClient) module manages cookies automatically
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED


def test_cookie_invalid_session(
    app: FastAPI, test_client: TestClient, root_login_data: LoginModel
):
    """
    Description
        Try to log in, using malformed cookie.

    Succeeds
        If login failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Modify cookie (1) and do some stuff
    cookies: RequestsCookieJar = resp.cookies.copy()
    cookies.set("USER_ID", "no_such_id")
    resp = test_client.get(app.url_path_for("list_users"), cookies=cookies)
    json = resp.json()

    # Ensure auth failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_SESSION_NOT_FOUND

    # Modify cookie (2) and do some stuff
    cookies: RequestsCookieJar = resp.cookies.copy()
    cookies.set("SESSION_ID", "no_such_id")
    resp = test_client.get(app.url_path_for("list_users"), cookies=cookies)
    json = resp.json()

    # Ensure auth failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_SESSION_NOT_FOUND

    # Clear cookies and do some stuff
    test_client.cookies.clear()
    resp = test_client.get(app.url_path_for("list_users"))
    json = resp.json()

    # Ensure auth failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_AUTHORIZATION_REQUIRED


def test_logout_ok(app: FastAPI, test_client: TestClient, root_login_data: LoginModel):
    """
    Description
        Create new user. Try to log in and log out

    Succeeds
        If no errors were encountered
    """

    # Login
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Logout
    resp = test_client.post(app.url_path_for("logout"))
    assert resp.status_code == HTTP_200_OK

    # Try to do some stuff after logout
    resp = test_client.get(app.url_path_for("list_users"))
    json = resp.json()

    # Ensure tries are failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_AUTHORIZATION_REQUIRED


def test_logout_invalid_session(
    app: FastAPI, test_client: TestClient, root_login_data: LoginModel
):
    """
    Description
        Try to logout using malformed values

    Succeeds
        If all errors are catched
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Modify cookie (1) and try to logout
    cookies: RequestsCookieJar = resp.cookies.copy()
    cookies.set("USER_ID", "no_such_id")
    resp = test_client.post(app.url_path_for("logout"), cookies=cookies)
    json = resp.json()

    # Ensure logout failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_SESSION_NOT_FOUND

    # Modify cookie (2) and try to logout
    cookies: RequestsCookieJar = resp.cookies.copy()
    cookies.set("SESSION_ID", "no_such_id")
    resp = test_client.post(app.url_path_for("logout"), cookies=cookies)
    json = resp.json()

    # Ensure logout failed
    assert resp.status_code == HTTP_401_UNAUTHORIZED
    assert json["code"] == E_SESSION_NOT_FOUND

    # Clear cookies and try to logout
    test_client.cookies.clear()
    resp = test_client.post(app.url_path_for("logout"))

    # Ensure logout failed
    assert resp.status_code == HTTP_422_UNPROCESSABLE_ENTITY
