from math import ceil
from typing import List

import pytest
from requests import Response
from starlette.status import *

from api_gateway.app.api.base import UserObjectRemovalState
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMUser
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import ITEM_LIST_FIELDS, USER_FIELDS, LoginModel, unordered_unique_match


def test_access(
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

    def _list_users(login_data: LoginModel) -> Response:
        # Login
        resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
        assert resp.status_code == HTTP_200_OK

        # List users
        resp = test_client.get(app.url_path_for("list_users"))
        return resp

    resp = _list_users(sys_admin_login_data)
    assert resp.status_code == HTTP_200_OK

    resp = _list_users(admin_login_data)
    assert resp.status_code == HTTP_200_OK

    resp = _list_users(user_login_data)
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert resp.json()["code"] == E_ADMIN_REQUIRED


def test_format(
    app: FastAPI,
    test_client: TestClient,
    admin_login_data: LoginModel,
):
    """
    Description
        Try to list users

    Succeeds
        If no errors were encountered
    """

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # List users
    resp = test_client.get(app.url_path_for("list_users"))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of users
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert all(k in json["items"][0] for k in USER_FIELDS)


@pytest.mark.parametrize("pg_size", [10, 13, 50, 100])
def test_pagination(
    app: FastAPI,
    pg_size: int,
    test_client: TestClient,
    admin_login_data: LoginModel,
    present_users: List[ORMUser],
    trashbin_users: List[ORMUser],
):
    """
    Description
        Try to list users, using pagination

    Succeeds
        If no errors were encountered
    """

    present_users = [user.name for user in present_users]
    trashbin_users = [user.name for user in trashbin_users]
    all_users = [*present_users, *trashbin_users]

    # Login as admin
    resp = test_client.post(app.url_path_for("login"), json=admin_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    def _assert_list_users(
        removal_state: UserObjectRemovalState, user_names: List[str]
    ):
        fetched_users = []
        users_count = len(user_names)
        pg_total = ceil(users_count / pg_size)

        for pg_num in range(pg_total):

            # Each page contains up to `pg_size` records
            resp = test_client.get(
                url=app.url_path_for("list_users"),
                params=dict(
                    pg_num=pg_num,
                    pg_size=pg_size,
                    removal_state=removal_state,
                ),
            )
            assert resp.status_code == HTTP_200_OK
            json = resp.json()

            users_left = users_count - pg_num * pg_size
            assert len(json["items"]) == min(pg_size, users_left)

            names = [user["name"] for user in json["items"]]
            fetched_users.extend(names)

        # Check non existent page to return empty list
        resp = test_client.get(
            url=app.url_path_for("list_users"),
            params=dict(
                pg_num=pg_total,
                pg_size=pg_size,
                removal_state=removal_state,
            ),
        )
        assert resp.status_code == HTTP_200_OK
        assert len(resp.json()["items"]) == 0

        # Compare users from api with users from db
        assert unordered_unique_match(fetched_users, user_names)

    _assert_list_users(UserObjectRemovalState.all, all_users)
    _assert_list_users(UserObjectRemovalState.present, present_users)
    _assert_list_users(UserObjectRemovalState.trash_bin, trashbin_users)
