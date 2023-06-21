from typing import List

from starlette.status import *

from api_gateway.app.api.base import DeleteActions, UserObjectRemovalState
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMProject
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import LoginModel, UserModel


def test_access_check(
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


def test_count_projects_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_projects: List[ORMProject],
):
    """
    Description
        Try to get count of projects

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Count projects with page size 10
    user_id = json["user_id"]
    url = app.url_path_for("get_project_count", user_id=user_id)
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    pg_size = json["pg_size"]
    pg_total = json["pg_total"]
    cnt_total = json["cnt_total"]

    # Ensure count of records is equal to
    # count of created projects + default project
    assert cnt_total == len(list_of_projects) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1


def test_count_project_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_projects: List[ORMProject],
    default_project: ORMProject,
):
    """
    Description
        Try to get count of users, including deleted ones

    Succeeds
        If no errors were encountered
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

    # Count users with page size 10
    resp = test_client.get(
        url=app.url_path_for("get_project_count", user_id=user_id),
        params=dict(
            pg_size=10,
            removal_state=UserObjectRemovalState.all,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    pg_size = json["pg_size"]
    pg_total = json["pg_total"]
    cnt_total = json["cnt_total"]

    # Ensure count of records is equal to count of
    # created projects plus deleted project
    assert cnt_total == len(list_of_projects) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1

    # Count only deleted projects
    resp = test_client.get(
        url=app.url_path_for("get_project_count", user_id=user_id),
        params=dict(
            removal_state=UserObjectRemovalState.trash_bin,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure count of records is correct
    assert json["cnt_total"] == 1
