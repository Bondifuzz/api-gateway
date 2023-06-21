from starlette.status import *

from api_gateway.app.api.base import DeleteActions
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMProject
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import NO_SUCH_ID, LoginModel


def test_delete_project_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to delete user

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


def test_delete_project_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
):
    """
    Description
        Try to delete non existent user

    Succeeds
        If delete operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Delete project
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": NO_SUCH_ID}
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}
    url_delete = app.url_path_for("delete_project", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    json = resp.json()

    # Ensure delete operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_PROJECT_NOT_FOUND


def test_delete_project_twice(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to delete project twice

    Succeeds
        If second delete operation failed
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

    # Delete project second time
    resp = test_client.delete(url_delete, params=body_params_delete)
    json = resp.json()

    # Ensure second delete operation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_PROJECT_DELETED
