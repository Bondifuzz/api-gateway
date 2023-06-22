from math import ceil
from typing import List

import pytest
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from requests import Response
from starlette.status import *

from api_gateway.app.api.base import UserObjectRemovalState
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMUser

from ..conftest import ITEM_COUNT_FIELDS, LoginModel


def test_users_access(
    app: FastAPI,
    test_client: TestClient,
    sys_admin_login_data: LoginModel,
    admin_login_data: LoginModel,
    user_login_data: LoginModel,
):
    """
    Description
        Checks that administrator can query info about all users

    Succeeds
        If all checks were passed
    """

    def _get_user_count(login_data: LoginModel) -> Response:
        # Login
        resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
        assert resp.status_code == HTTP_200_OK

        # Get users count
        resp = test_client.get(app.url_path_for("get_user_count"))
        return resp

    resp = _get_user_count(sys_admin_login_data)
    assert resp.status_code == HTTP_200_OK

    resp = _get_user_count(admin_login_data)
    assert resp.status_code == HTTP_200_OK

    resp = _get_user_count(user_login_data)
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert resp.json()["code"] == E_ADMIN_REQUIRED


@pytest.mark.parametrize("pg_size", [10, 13, 50, 100])
def test_users_count_format(
    app: FastAPI,
    pg_size: int,
    test_client: TestClient,
    admin_login_data: LoginModel,
):

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Ensure response success has all data fields
    resp = test_client.get(
        app.url_path_for("get_user_count"),
        params=dict(
            pg_size=pg_size,
            removal_state=UserObjectRemovalState.all,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    assert all(k in resp.json() for k in ITEM_COUNT_FIELDS)


@pytest.mark.parametrize("pg_size", [10, 13, 50, 100])
def test_users_count(
    app: FastAPI,
    pg_size: int,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_users: List[ORMUser],
    trashbin_users: List[ORMUser],
):
    """
    Description
        Try to get count of users, including deleted ones

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_users_count(removal_state: UserObjectRemovalState, users_count: int):
        resp = test_client.get(
            app.url_path_for("get_user_count"),
            params=dict(
                pg_size=pg_size,
                removal_state=removal_state,
            ),
        )
        assert resp.status_code == HTTP_200_OK

        result = resp.json()
        assert result["pg_size"] == pg_size
        assert result["cnt_total"] == users_count
        assert result["pg_total"] == ceil(users_count / pg_size)

    _assert_users_count(
        UserObjectRemovalState.all, len(present_users) + len(trashbin_users)
    )
    _assert_users_count(UserObjectRemovalState.present, len(present_users))
    _assert_users_count(UserObjectRemovalState.trash_bin, len(trashbin_users))
