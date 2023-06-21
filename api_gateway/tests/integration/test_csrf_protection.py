from contextlib import contextmanager

from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.api.handlers.security.csrf import CSRFTokenManager
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from .conftest import NO_SUCH_ID, LoginModel


@contextmanager
def no_csrf_token_in_cookies(test_client: TestClient):
    token = test_client.cookies.pop("CSRF_TOKEN")
    yield
    test_client.cookies["CSRF_TOKEN"] = token


@contextmanager
def no_csrf_token_in_headers(test_client: TestClient):
    token = test_client.headers.pop("X-CSRF-TOKEN")
    yield
    test_client.headers["X-CSRF-TOKEN"] = token


@contextmanager
def custom_csrf_token_in_headers(test_client: TestClient, token: str):
    old_token = test_client.headers.pop("X-CSRF-TOKEN")
    test_client.headers["X-CSRF-TOKEN"] = token
    yield
    test_client.headers["X-CSRF-TOKEN"] = old_token


@contextmanager
def custom_csrf_token(test_client: TestClient, token: str):
    old_token = test_client.headers.pop("X-CSRF-TOKEN")
    test_client.headers["X-CSRF-TOKEN"] = token
    test_client.cookies["CSRF_TOKEN"] = token
    yield
    test_client.headers["X-CSRF-TOKEN"] = old_token
    test_client.cookies["CSRF_TOKEN"] = old_token


def test_login_ok(
    app: FastAPI,
    test_client: TestClient,
    user_login_data: LoginModel,
):
    """
    Description
        Try to log in. Ensure that CSRF token was issued

    Succeeds
        If CSRF token is present in cookies and response headers
    """

    url = app.url_path_for("login")
    json_data = user_login_data.dict()
    resp = test_client.post(url, json=json_data)
    assert resp.status_code == HTTP_200_OK

    assert "CSRF_TOKEN" in resp.cookies.keys()
    assert "X-CSRF-TOKEN" in resp.headers.keys()


def test_unsafe_operation(
    app: FastAPI,
    test_client: TestClient,
    user_login_data: LoginModel,
    csrf_token_mgr: CSRFTokenManager,
):
    """
    Description
        Try to perform unsafe operations with and without CSRF token

    Succeeds
        If unsafe operations succeed if
        CSRF token is present and fail otherwise
    """

    def unsafe_operation():
        resp = test_client.post(app.url_path_for("logout"))
        return resp.status_code, resp.json()

    url = app.url_path_for("login")
    json_data = user_login_data.dict()
    resp = test_client.post(url, json=json_data)
    assert resp.status_code == HTTP_200_OK

    user_id = resp.json()["user_id"]
    test_client.headers["X-CSRF-TOKEN"] = resp.headers["X-CSRF-TOKEN"]

    #
    # CSRF token must be present in both cookies and request headers
    # If not, unsafe operation must not succeed
    #

    with no_csrf_token_in_cookies(test_client):
        status_code, json_data = unsafe_operation()
        assert status_code == HTTP_403_FORBIDDEN
        assert json_data["code"] == E_CSRF_TOKEN_MISSING

    with no_csrf_token_in_headers(test_client):
        status_code, json_data = unsafe_operation()
        assert status_code == HTTP_403_FORBIDDEN
        assert json_data["code"] == E_CSRF_TOKEN_MISSING

    with no_csrf_token_in_cookies(test_client):
        with no_csrf_token_in_headers(test_client):
            status_code, json_data = unsafe_operation()
            assert status_code == HTTP_403_FORBIDDEN
            assert json_data["code"] == E_CSRF_TOKEN_MISSING

    #
    # CSRF token must be valid.
    # If not, unsafe operation must not succeed
    #

    token = "12345"
    with custom_csrf_token(test_client, token):
        status_code, json_data = unsafe_operation()
        assert status_code == HTTP_403_FORBIDDEN
        assert json_data["code"] == E_CSRF_TOKEN_INVALID

    #
    # CSRF token in cookies must be exactly the same as in request headers
    # If not, unsafe operation must not succeed
    #

    token = csrf_token_mgr.create_csrf_token(user_id)
    with custom_csrf_token_in_headers(test_client, token):
        status_code, json_data = unsafe_operation()
        assert status_code == HTTP_403_FORBIDDEN
        assert json_data["code"] == E_CSRF_TOKEN_MISMATCH

    #
    # CSRF token must belong to current user
    # If not, unsafe operation must not succeed
    #

    token = csrf_token_mgr.create_csrf_token(NO_SUCH_ID)
    with custom_csrf_token(test_client, token):
        status_code, json_data = unsafe_operation()
        assert status_code == HTTP_403_FORBIDDEN
        assert json_data["code"] == E_CSRF_TOKEN_USER_MISMATCH

    #
    # Valid CSRF token is present
    # Now unsafe operation must succeed
    #

    status_code, json_data = unsafe_operation()
    assert status_code == HTTP_200_OK


def test_refresh_csrf_token(
    app: FastAPI,
    test_client: TestClient,
    user_login_data: LoginModel,
):
    """
    Description
        CSRF token has short lifetime, so user
        must be able to obtain new token if he's logged in

    Succeeds
        If logged in user can obtain new CSRF token
    """

    url = app.url_path_for("login")
    json_data = user_login_data.dict()
    resp = test_client.post(url, json=json_data)
    assert resp.status_code == HTTP_200_OK

    #
    # Remove CSRF token after login
    # and refresh CSRF token
    #

    test_client.cookies.pop("CSRF_TOKEN")
    resp = test_client.post(app.url_path_for("refresh_csrf_token"))
    assert resp.status_code == HTTP_200_OK

    #
    # Ensure, new CSRF token was obtained
    #

    assert "CSRF_TOKEN" in resp.cookies.keys()
    assert "X-CSRF-TOKEN" in resp.headers.keys()

    #
    # This route must be accessable only for logged-in user
    # Remove all cookies and test it there
    #

    test_client.cookies.clear()
    resp = test_client.post(app.url_path_for("refresh_csrf_token"))
    assert resp.status_code == HTTP_401_UNAUTHORIZED
