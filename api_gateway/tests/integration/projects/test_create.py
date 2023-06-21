from starlette.status import *

from api_gateway.app.api.base import DeleteActions
from api_gateway.app.api.error_codes import *
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import LoginModel, ProjectModel


def test_create_project_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    project: ProjectModel,
):
    """
    Description
        Create project with provided API.
        Then checks that project was created correctly.

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create project
    user_id = json["user_id"]
    url = app.url_path_for("create_project", user_id=user_id)
    resp = test_client.post(url, json=project.dict())
    assert resp.status_code == HTTP_201_CREATED


def test_create_project_already_exists(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    project: ProjectModel,
):
    """
    Description
        Try to create project which already exists

    Succeeds
        If creation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create project
    user_id = json["user_id"]
    url = app.url_path_for("create_project", user_id=user_id)
    resp = test_client.post(url, json=project.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Create project twice
    resp = test_client.post(url, json=project.dict())
    json = resp.json()

    # Ensure second creation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_PROJECT_EXISTS


def test_create_project_in_trashbin(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    project: ProjectModel,
):
    """
    Description
        Try to create project which was moved to trash bin

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create project
    user_id = json["user_id"]
    url_create = app.url_path_for("create_project", user_id=user_id)
    resp = test_client.post(url_create, json=project.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Delete project (will be moved to trash bin)
    project_id = json["id"]
    url_params = {"user_id": user_id, "project_id": project_id}
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}
    url_delete = app.url_path_for("delete_project", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Create project again
    resp = test_client.post(url_create, json=project.dict())

    # Ensure creation success
    assert resp.status_code == HTTP_201_CREATED
