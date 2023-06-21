from starlette.status import *

from api_gateway.app.api.base import DeleteActions
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMProject
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import NO_SUCH_ID, PROJECT_FIELDS, LoginModel, UserModel


def test_get_project_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to get project

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Get project
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": default_project.id}
    resp = test_client.get(app.url_path_for("get_project", **url_params))
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in PROJECT_FIELDS)


def test_get_project_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
):
    """
    Description
        Try to get non existent project

    Succeeds
        If get operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Get project
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": NO_SUCH_ID}
    url_get = app.url_path_for("get_project", **url_params)
    assert test_client.get(url_get).status_code == HTTP_404_NOT_FOUND


def test_get_project_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to get project which has been deleted

    Succeeds
        If get operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Delete project (will be moved to trash bin)
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": default_project.id}
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}
    url_delete = app.url_path_for("delete_project", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Get deleted project
    user_id = json["user_id"]
    url_get = app.url_path_for("get_project", **url_params)
    resp = test_client.get(url_get)
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in PROJECT_FIELDS)


def test_client_is_not_admin(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
):
    """
    Description
        Checks that admin admin can not have projects, fuzzers, e.t.c

    Succeeds
        If request failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    user_id = resp.json()["user_id"]

    # Ensure, that root can not have projects
    resp = test_client.get(app.url_path_for("list_projects", user_id=user_id))
    json = resp.json()

    assert json["code"] == E_CLIENT_ACCOUNT_REQUIRED
    assert resp.status_code == HTTP_403_FORBIDDEN


def test_default_project(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
):

    """
    Description
        Checks that default project is present
        in newly created client account

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
    json = resp.json()

    # Check default project is present
    assert resp.status_code == HTTP_200_OK
    assert len(json["items"]) == 1

    # Count projects
    resp = test_client.get(app.url_path_for("get_project_count", user_id=user_id))
    json = resp.json()

    # Check count is ok
    assert resp.status_code == HTTP_200_OK
    assert json["pg_total"] == 1
