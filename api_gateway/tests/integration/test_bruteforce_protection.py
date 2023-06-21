from time import sleep

from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.settings import AppSettings
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from .conftest import LoginModel, UserModel


def test_simple_bruteforce(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
    settings: AppSettings,
):
    """
    Description
        Try to perform a simple bruteforce attack

    Succeeds
        If user lockout is triggered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED

    username = usual_user.name
    max_failed_logins = settings.bfp.max_failed_logins

    #
    # Imitate simple bruteforce attack
    # and exceed all login attempts
    #

    url = app.url_path_for("login")
    for i in range(max_failed_logins):

        bruteforce_login_data = {
            "username": username,
            "password": f"bfp-attempt-{i}",
            "session_metadata": "some meta",
        }

        resp = test_client.post(url, json=bruteforce_login_data)
        assert resp.status_code == HTTP_401_UNAUTHORIZED

    #
    # One more try. It must fail due to
    # account lockout which indicates that
    # bruteforce protection is working
    #

    final_login_data = {
        "username": username,
        "password": "bfp-attempt-final",
        "session_metadata": "some meta",
    }

    resp = test_client.post(url, json=final_login_data)
    assert resp.status_code == HTTP_403_FORBIDDEN

    json_data = resp.json()
    json_data["code"] == E_DEVICE_COOKIE_LOCKOUT

    #
    # Repeat the same after 1 second.
    # It must fail too, with same reason
    #

    sleep(1)

    resp = test_client.post(url, json=final_login_data)
    assert resp.status_code == HTTP_403_FORBIDDEN

    json_data = resp.json()
    json_data["code"] == E_DEVICE_COOKIE_LOCKOUT


def test_bruteforce_from_trusted_device(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
    settings: AppSettings,
):
    """
    Description
        Try to perform a bruteforce attack from a device
        that has already been successfully logged in.
        Bruteforce protection must be effective
        even on trusted devices

    Succeeds
        If user lockout is triggered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED

    username = usual_user.name
    password = usual_user.password
    max_failed_logins = settings.bfp.max_failed_logins

    #
    # Login, then logout. Ensure client
    # is trusted by given device cookie
    #

    url_login = app.url_path_for("login")
    url_logout = app.url_path_for("logout")

    user_login_data = {
        "username": username,
        "password": password,
        "session_metadata": "some meta",
    }

    resp = test_client.post(url_login, json=user_login_data)
    assert resp.status_code == HTTP_200_OK

    resp = test_client.post(url_logout, json=user_login_data)
    assert resp.status_code == HTTP_200_OK

    # Here's a device cookie
    assert "DEVICE_COOKIE" in test_client.cookies.keys()

    #
    # Imitate simple bruteforce attack
    # and exceed all login attempts
    #

    url = app.url_path_for("login")
    for i in range(max_failed_logins):

        bruteforce_login_data = {
            "username": username,
            "password": f"bfp-attempt-{i}",
            "session_metadata": "some meta",
        }

        resp = test_client.post(url, json=bruteforce_login_data)
        assert resp.status_code == HTTP_401_UNAUTHORIZED

    #
    # One more try. It must fail due to
    # account lockout which indicates that
    # bruteforce protection is working
    #

    final_login_data = {
        "username": username,
        "password": "bfp-attempt-final",
        "session_metadata": "some meta",
    }

    resp = test_client.post(url, json=final_login_data)
    assert resp.status_code == HTTP_403_FORBIDDEN

    json_data = resp.json()
    json_data["code"] == E_DEVICE_COOKIE_LOCKOUT


def test_lockout_dos(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
    settings: AppSettings,
):
    """
    Description
        Try to make login impossible for
        user by triggering account lockout.
        Legitimate user must be able to
        login despite such actions.

    Succeeds
        If legitimate user is still able to login
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED

    username = usual_user.name
    password = usual_user.password
    max_failed_logins = settings.bfp.max_failed_logins

    #
    # Login, then logout. Ensure client
    # is trusted by given device cookie
    #

    url_login = app.url_path_for("login")
    url_logout = app.url_path_for("logout")

    user_login_data = {
        "username": username,
        "password": password,
        "session_metadata": "some meta",
    }

    resp = test_client.post(url_login, json=user_login_data)
    assert resp.status_code == HTTP_200_OK

    resp = test_client.post(url_logout, json=user_login_data)
    assert resp.status_code == HTTP_200_OK

    # Here's a device cookie
    assert "DEVICE_COOKIE" in test_client.cookies.keys()

    #
    # Save the device cookie for future use
    # Clear cookie jar to login as untrusted client
    #

    device_cookie = test_client.cookies.get("DEVICE_COOKIE")
    test_client.cookies.clear()

    #
    # Imitate simple bruteforce attack
    # and exceed all login attempts (untrusted client)
    #

    url = app.url_path_for("login")
    for i in range(max_failed_logins):

        bruteforce_login_data = {
            "username": username,
            "password": f"bfp-attempt-{i}",
            "session_metadata": "some meta",
        }

        resp = test_client.post(url, json=bruteforce_login_data)
        assert resp.status_code == HTTP_401_UNAUTHORIZED

    #
    # One more try. It must fail due to
    # account lockout which indicates that
    # bruteforce protection is working
    #

    final_login_data = {
        "username": username,
        "password": "bfp-attempt-final",
        "session_metadata": "some meta",
    }

    resp = test_client.post(url, json=final_login_data)
    assert resp.status_code == HTTP_403_FORBIDDEN

    json_data = resp.json()
    json_data["code"] == E_DEVICE_COOKIE_LOCKOUT

    #
    # Despite untrusted client lockout
    # the trusted client must be able to login
    #

    test_client.cookies.set("DEVICE_COOKIE", device_cookie)

    user_login_data = {
        "username": username,
        "password": password,
        "session_metadata": "some meta",
    }

    resp = test_client.post(url_login, json=user_login_data)
    assert resp.status_code == HTTP_200_OK
