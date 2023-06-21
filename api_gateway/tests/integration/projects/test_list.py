from typing import List

import pytest
from starlette.status import *

from api_gateway.app.api.base import DeleteActions, UserObjectRemovalState
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMProject, ORMUser
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import (
    ITEM_LIST_FIELDS,
    PROJECT_FIELDS,
    LoginModel,
    UserModel,
    unordered_unique_match,
)


def test_access_another_user(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    root_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Checks that user can't view and manage objects created by another client

    Succeeds
        If check was passed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create another user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Try to list projects belonging to another user
    user_id = json["id"]
    resp = test_client.get(app.url_path_for("list_projects", user_id=user_id))
    assert resp.status_code == HTTP_403_FORBIDDEN


def test_list_projects_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
):
    """
    Description
        Try to list projects

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # List projects
    user_id = json["user_id"]
    resp = test_client.get(app.url_path_for("list_projects", user_id=user_id))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of users
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert all(k in json["items"][0] for k in PROJECT_FIELDS)


@pytest.mark.parametrize(
    argnames="removal_state",
    argvalues=[UserObjectRemovalState.trash_bin, UserObjectRemovalState.all],
)
def test_list_projects_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    removal_state: UserObjectRemovalState,
):
    """
    Description
        Try to list projects, with deleted ones

    Succeeds
        If deleted users were included in the results
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Delete project
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": default_project.id}
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}
    url_delete = app.url_path_for("delete_project", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # List projects
    resp = test_client.get(
        url=app.url_path_for("list_projects", user_id=user_id),
        params=dict(
            pg_size=100,
            removal_state=removal_state,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of projects with deleted one
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert len(json["items"]) == 1

    first_item = json["items"][0]
    assert first_item["name"] == default_project.name


def test_list_project_pagination(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_projects: List[ORMUser],
    default_project: ORMProject,
):
    """
    Description
        Try to list projects, using pagination

    Succeeds
        If no errors were encountered
    """

    created_projects = [project.name for project in list_of_projects]
    fetched_projects = []

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # List projects using pagination
    user_id = json["user_id"]
    created_projects.append(default_project.name)
    url = app.url_path_for("list_projects", user_id=user_id)
    pg_num = 0

    while True:

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        # Stop when page is empty
        if not json["items"]:
            break

        names = [project["name"] for project in json["items"]]
        fetched_projects.extend(names)
        pg_num += 1

    # Ensure created projects match fetched projects
    assert unordered_unique_match(created_projects, fetched_projects)


def test_list_project_pagination_with_count(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_projects: List[ORMUser],
    default_project: ORMProject,
):
    """
    Description
        Try to list projects, using pagination and count endpoint

    Succeeds
        If no errors were encountered
    """

    created_projects = [project.name for project in list_of_projects]
    fetched_projects = []

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Count projects with page size 10
    user_id = json["user_id"]
    created_projects.append(default_project.name)
    url = app.url_path_for("get_project_count", user_id=user_id)
    resp = test_client.get(url=url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # List projects using pagination
    pg_size = json["pg_size"]
    pg_total = json["pg_total"]

    url = app.url_path_for("list_projects", user_id=user_id)
    for pg_num in range(pg_total):

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num, pg_size=pg_size))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        names = [project["name"] for project in json["items"]]
        fetched_projects.extend(names)

    # Ensure created projects match fetched projects
    assert unordered_unique_match(created_projects, fetched_projects)


def test_access_admin(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Checks that administrator can view and manage any objects created by client

    Succeeds
        If check was passed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # List projects
    user_id = json["id"]
    resp = test_client.get(app.url_path_for("list_projects", user_id=user_id))
    assert resp.status_code == HTTP_200_OK
