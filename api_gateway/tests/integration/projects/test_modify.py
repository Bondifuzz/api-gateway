from starlette.status import *

from api_gateway.app.api.base import DeleteActions
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMProject
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from ..conftest import (
    NO_SUCH_ID,
    LoginModel,
    ProjectModel,
    ProjectUpdateModel,
    UserUpdateModel,
)


def test_modify_project_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to modify project

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Update project
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": default_project.id}
    url_update = app.url_path_for("update_project", **url_params)

    updated_name = "myproj"
    updates = ProjectUpdateModel(name=updated_name)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure changes are correct (in response)
    assert json["old"] == {"name": default_project.name}
    assert json["new"] == {"name": updated_name}

    # Get project
    resp = test_client.get(app.url_path_for("get_project", **url_params))
    json = resp.json()

    # Ensure changes are correct (in fact)
    assert json["name"] == updated_name


def test_modify_project_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
):
    """
    Description
        Try to modify non existent user

    Succeeds
        If modify operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Update project which does not exist
    user_id = json["user_id"]
    url_params = {"user_id": user_id, "project_id": NO_SUCH_ID}
    url_update = app.url_path_for("update_project", **url_params)

    updates = UserUpdateModel(name="aaa")
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_PROJECT_NOT_FOUND


def test_modify_project_name_exists(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    project: ProjectModel,
):
    """
    Description
        Try to modify project and update his name
        with another name of existent project

    Succeeds
        If modify operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create another project
    user_id = json["user_id"]
    url_create = app.url_path_for("create_project", user_id=user_id)
    resp = test_client.post(url_create, json=project.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Update project with existing project name
    url_params = {"user_id": user_id, "project_id": default_project.id}
    url_update = app.url_path_for("update_project", **url_params)

    updates = ProjectUpdateModel(name=project.name)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_PROJECT_EXISTS


def test_modify_project_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to modify project moved to trash bin

    Succeeds
        If modify operation failed
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

    # Update project which was deleted
    updates = ProjectUpdateModel(name="aaa")
    url_update = app.url_path_for("update_project", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_PROJECT_DELETED
