import hashlib
from typing import List

import pytest
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from starlette.status import *

from api_gateway.app.api.base import DeleteActions, UserObjectRemovalState
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import (
    ORMFuzzer,
    ORMHealth,
    ORMImage,
    ORMProject,
    ORMRevision,
    ORMRevisionStatus,
    ORMUploadStatus,
    ORMUser,
)
from api_gateway.app.settings import AppSettings

from .conftest import (
    ITEM_LIST_FIELDS,
    NO_SUCH_ID,
    REVISION_FIELDS,
    LoginModel,
    RevisionModel,
    RevisionResUpdateModel,
    RevisionUpdateModel,
    UserModel,
    UserUpdateModel,
    big_tar,
    create_custom_revision,
    small_bytes,
    small_json,
    small_tar,
    unordered_unique_match,
)


def test_client_is_not_admin(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Checks that admin admin can not have revisions

    Succeeds
        If request failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # List revisions
    resp = test_client.get(app.url_path_for("list_revisions", **url_params))
    json = resp.json()

    # Ensure, that root can not have revisions
    assert json["code"] == E_CLIENT_ACCOUNT_REQUIRED
    assert resp.status_code == HTTP_403_FORBIDDEN


def test_create_revision_empty_desc_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    revision: RevisionModel,
):
    """
    Description
        Create revision with provided API.
        Then checks that revision was created correctly.

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Create revision
    url = app.url_path_for("create_revision", **url_params)
    revision.description = ""
    resp = test_client.post(url, json=revision.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Get revision
    url_params.update({"revision_id": json["id"]})
    resp = test_client.get(app.url_path_for("get_revision", **url_params))
    assert resp.status_code == HTTP_200_OK


def test_create_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    revision: RevisionModel,
):
    """
    Description
        Create revision with provided API.
        Then checks that revision was created correctly.

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Create revision
    url = app.url_path_for("create_revision", **url_params)
    resp = test_client.post(url, json=revision.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Get revision
    url_params.update({"revision_id": json["id"]})
    resp = test_client.get(app.url_path_for("get_revision", **url_params))
    assert resp.status_code == HTTP_200_OK


def test_create_revision_already_exists(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    revision: RevisionModel,
):
    """
    Description
        Try to create revision which already exists

    Succeeds
        If creation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Create revision
    url = app.url_path_for("create_revision", **url_params)
    resp = test_client.post(url, json=revision.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Create revision twice
    resp = test_client.post(url, json=revision.dict())
    json = resp.json()

    # Ensure second creation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_REVISION_EXISTS


def test_create_revision_in_trashbin(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    revision: RevisionModel,
):
    """
    Description
        Try to create revision which was moved to trash bin

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params_create = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Create revision
    url_create = app.url_path_for("create_revision", **url_params_create)
    resp = test_client.post(url_create, json=revision.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Set url params
    url_params_delete = {
        "revision_id": json["id"],
        **url_params_create,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision (will be moved to trash bin)
    url_delete = app.url_path_for("delete_revision", **url_params_delete)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Create revision again
    resp = test_client.post(url_create, json=revision.dict())

    # Ensure creation success
    assert resp.status_code == HTTP_201_CREATED


def test_get_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to get revision

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Get revision
    resp = test_client.get(app.url_path_for("get_revision", **url_params))
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in REVISION_FIELDS)


def test_get_revision_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to get non existent revision

    Succeeds
        If get operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": NO_SUCH_ID,
    }

    # Get revision
    url_get = app.url_path_for("get_revision", **url_params)
    assert test_client.get(url_get).status_code == HTTP_404_NOT_FOUND


def test_get_revision_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to get revision which has been deleted

    Succeeds
        If get operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision (will be moved to trash bin)
    url_delete = app.url_path_for("delete_revision", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Get deleted revision
    url_get = app.url_path_for("get_revision", **url_params)
    resp = test_client.get(url_get)
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in REVISION_FIELDS)


# TODO: active revision tests


def test_list_revisions_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to list revisions

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # List revisions
    resp = test_client.get(app.url_path_for("list_revisions", **url_params))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of users
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert all(k in json["items"][0] for k in REVISION_FIELDS)


@pytest.mark.parametrize(
    argnames="removal_state",
    argvalues=[UserObjectRemovalState.trash_bin, UserObjectRemovalState.all],
)
def test_list_revisions_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
    removal_state: UserObjectRemovalState,
):
    """
    Description
        Try to list revisions, with deleted ones

    Succeeds
        If deleted users were included in the results
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for list
    url_params_list = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Set url params for delete
    url_params_delete = {
        "revision_id": default_revision.id,
        **url_params_list,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url_delete = app.url_path_for("delete_revision", **url_params_delete)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # List revisions
    resp = test_client.get(
        url=app.url_path_for("list_revisions", **url_params_list),
        params=dict(
            pg_size=100,
            removal_state=removal_state,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of revisions with deleted one
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert len(json["items"]) == 1

    first_item = json["items"][0]
    assert first_item["name"] == default_revision.name


def test_count_revisions_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_revisions: List[ORMRevision],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to get count of revisions

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Count revisions with page size 10
    url = app.url_path_for("get_revision_count", **url_params)
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    pg_size = json["pg_size"]
    pg_total = json["pg_total"]
    cnt_total = json["cnt_total"]

    # Ensure count of records is equal to
    # count of created revisions + default revision
    assert cnt_total == len(list_of_revisions) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1


def test_count_revisions_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_revisions: List[ORMRevision],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
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

    # Set url params for count
    url_params_count = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Set url params for delete
    url_params_delete = {
        "revision_id": default_revision.id,
        **url_params_count,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url_delete = app.url_path_for("delete_revision", **url_params_delete)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Count users with page size 10
    resp = test_client.get(
        url=app.url_path_for("get_revision_count", **url_params_count),
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
    # created revisions + deleted revision
    assert cnt_total == len(list_of_revisions) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1

    # Count only deleted revisions
    resp = test_client.get(
        url=app.url_path_for("get_revision_count", **url_params_count),
        params=dict(
            removal_state=UserObjectRemovalState.trash_bin,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure count of records is correct
    assert json["cnt_total"] == 1


def test_list_revisions_pagination(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_revisions: List[ORMUser],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to list revisions, using pagination

    Succeeds
        If no errors were encountered
    """

    created_revisions = [revision.name for revision in list_of_revisions]
    fetched_revisions = []

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for list
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # List revisions using pagination
    created_revisions.append(default_revision.name)
    url = app.url_path_for("list_revisions", **url_params)
    pg_num = 0

    while True:

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        # Stop when page is empty
        if not json["items"]:
            break

        names = [revision["name"] for revision in json["items"]]
        fetched_revisions.extend(names)
        pg_num += 1

    # Ensure created revisions match fetched revisions
    assert unordered_unique_match(created_revisions, fetched_revisions)


def test_list_revisions_pagination_with_count(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_revisions: List[ORMUser],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to list revisions, using pagination and count endpoint

    Succeeds
        If no errors were encountered
    """

    created_revisions = [revision.name for revision in list_of_revisions]
    fetched_revisions = []

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for list
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Count revisions with page size 10
    created_revisions.append(default_revision.name)
    url = app.url_path_for("get_revision_count", **url_params)
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # List revisions using pagination
    pg_size = json["pg_size"]
    pg_total = json["pg_total"]

    url = app.url_path_for("list_revisions", **url_params)
    for pg_num in range(pg_total):

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num, pg_size=pg_size))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        names = [revision["name"] for revision in json["items"]]
        fetched_revisions.extend(names)

    # Ensure created revisions match fetched revisions
    assert unordered_unique_match(created_revisions, fetched_revisions)


@pytest.mark.parametrize(
    argnames="updates",
    argvalues=(
        RevisionUpdateModel(name="myproj"),
        RevisionUpdateModel(name="myproj", description="My description"),
    ),
)
def test_update_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
    updates: RevisionUpdateModel,
):
    """
    Description
        Try to update revision

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Update revision
    url_update = app.url_path_for("update_revision_information", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK

    # Get revision
    resp = test_client.get(app.url_path_for("get_revision", **url_params))
    json = resp.json()

    # Ensure changes are correct (in fact)
    assert json["name"] == updates.name


@pytest.mark.parametrize(
    argnames="updates",
    argvalues=(
        RevisionResUpdateModel(cpu_usage=1000),
        RevisionResUpdateModel(cpu_usage=1000, ram_usage=1000),
        RevisionResUpdateModel(cpu_usage=1000, ram_usage=1000, tmpfs_size=100),
    ),
)
def test_update_revision_resources_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
    updates: RevisionResUpdateModel,
):
    """
    Description
        Try to update fuzzer resources

    Succeeds
        If no errors were encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Update revision
    url_update = app.url_path_for("update_revision_resources", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK

    # Get revision
    resp = test_client.get(app.url_path_for("get_revision", **url_params))
    json = resp.json()

    # Ensure changes are correct (in fact)
    assert json["cpu_usage"] == updates.cpu_usage


def test_update_revision_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to update non existent user

    Succeeds
        If update operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": NO_SUCH_ID,
    }

    # Update revision which does not exist
    updates = UserUpdateModel(name="aaa")
    url_update = app.url_path_for("update_revision_information", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_REVISION_NOT_FOUND


def test_update_revision_name_exists(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
    revision: RevisionModel,
):
    """
    Description
        Try to update revision and update his name
        with another name of existent revision

    Succeeds
        If update operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for create
    url_params_create = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Set url params for update
    url_params_update = {
        "revision_id": default_revision.id,
        **url_params_create,
    }

    # Create another revision
    url_create = app.url_path_for("create_revision", **url_params_create)
    resp = test_client.post(url_create, json=revision.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Update revision with existing revision name
    updates = RevisionUpdateModel(name=revision.name)
    url_update = app.url_path_for("update_revision_information", **url_params_update)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_REVISION_EXISTS


def test_update_revision_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to update revision moved to trash bin

    Succeeds
        If update operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url_delete = app.url_path_for("delete_revision", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Update revision which was deleted
    updates = RevisionUpdateModel(name="aaa")
    url_update = app.url_path_for("update_revision_information", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_REVISION_DELETED


def test_delete_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
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

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url_delete = app.url_path_for("delete_revision", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Get revision
    url_get = app.url_path_for("get_revision", **url_params)
    assert test_client.get(url_get).status_code == HTTP_200_OK


def test_delete_revision_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
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

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": NO_SUCH_ID,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url_delete = app.url_path_for("delete_revision", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    json = resp.json()

    # Ensure delete operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_REVISION_NOT_FOUND


def test_delete_revision_twice(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to delete revision twice

    Succeeds
        If second delete operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url_delete = app.url_path_for("delete_revision", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Delete revision second time
    resp = test_client.delete(url_delete, params=body_params_delete)
    json = resp.json()

    # Ensure second delete operation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_REVISION_DELETED


def test_delete_running_revision(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_image: ORMImage,
):
    """
    Description
        Try to delete revision.
        But it can not be deleted in running state

    Succeeds
        If operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create revision with custom status
    revision = create_custom_revision(
        "custom",
        default_fuzzer.id,
        default_image.id,
        status=ORMRevisionStatus.running,
    )

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": revision.id,
    }
    body_params_delete = {
        "action": DeleteActions.delete,
        "no_backup": False,
    }

    # Delete revision
    url = app.url_path_for("delete_revision", **url_params)
    resp = test_client.delete(url, params=body_params_delete)
    json = resp.json()

    # Ensure delete succeeded
    assert resp.status_code == HTTP_200_OK


def test_access_admin(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_user: ORMUser,
    usual_user: UserModel,
):
    """
    Description
        Checks that administrator can view
        and manage any objects created by client

    Succeeds
        If check was passed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create user
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Set url params
    url_params = {
        "user_id": default_user.id,
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # List revisions
    resp = test_client.get(app.url_path_for("list_revisions", **url_params))
    assert resp.status_code == HTTP_200_OK


def test_access_another_user(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    root_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
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

    # Set url params
    url_params = {
        "user_id": json["id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
    }

    # Try to list revisions belonging to another user
    resp = test_client.get(app.url_path_for("list_revisions", **url_params))
    assert resp.status_code == HTTP_403_FORBIDDEN


def test_upload_files_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Uploads fuzzer files

    Succeeds
        If upload succeeded
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Upload binaries
    url_binaries = app.url_path_for("upload_revision_binaries", **url_params)
    resp = test_client.put(url_binaries, data=small_tar())
    assert resp.status_code == HTTP_200_OK

    # Upload seeds
    url_seeds = app.url_path_for("upload_revision_seeds", **url_params)
    resp = test_client.put(url_seeds, data=small_tar())
    assert resp.status_code == HTTP_200_OK

    # Upload config
    url_config = app.url_path_for("upload_revision_config", **url_params)
    resp = test_client.put(url_config, data=small_json())
    assert resp.status_code == HTTP_200_OK


def test_upload_files_failed_content_invalid(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Uploads malformed fuzzer files

    Succeeds
        If upload failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Upload binaries
    url_binaries = app.url_path_for("upload_revision_binaries", **url_params)
    resp = test_client.put(url_binaries, data=small_bytes())
    assert resp.status_code == HTTP_422_UNPROCESSABLE_ENTITY

    # Upload seeds
    url_seeds = app.url_path_for("upload_revision_seeds", **url_params)
    resp = test_client.put(url_seeds, data=small_bytes())
    assert resp.status_code == HTTP_422_UNPROCESSABLE_ENTITY

    # Upload config
    url_config = app.url_path_for("upload_revision_config", **url_params)
    resp = test_client.put(url_config, data=small_bytes())
    assert resp.status_code == HTTP_422_UNPROCESSABLE_ENTITY


def test_upload_files_failed_limit_exceeded(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
    settings: AppSettings,
):
    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Upload binaries
    upload_limit = settings.revision.binaries_upload_limit
    url_binaries = app.url_path_for("upload_revision_binaries", **url_params)
    resp = test_client.put(url_binaries, data=big_tar(upload_limit))
    assert resp.status_code == HTTP_413_REQUEST_ENTITY_TOO_LARGE

    # Upload seeds
    upload_limit = settings.revision.seeds_upload_limit
    url_seeds = app.url_path_for("upload_revision_seeds", **url_params)
    resp = test_client.put(url_seeds, data=big_tar(upload_limit))
    assert resp.status_code == HTTP_413_REQUEST_ENTITY_TOO_LARGE

    # Upload config
    upload_limit = settings.revision.config_upload_limit
    headers = {"Content-Length": str(upload_limit)}
    url_config = app.url_path_for("upload_revision_config", **url_params)
    resp = test_client.put(url_config, data=big_tar(upload_limit), headers=headers)
    assert resp.status_code == HTTP_413_REQUEST_ENTITY_TOO_LARGE


def test_download_files_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Downloads fuzzer files

    Succeeds
        If download succeeded
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    def upload_download_compare(name_upload: str, name_download: str, data: bytes):

        url_upload = app.url_path_for(name_upload, **url_params)
        resp = test_client.put(url_upload, data=data)
        assert resp.status_code == HTTP_200_OK

        result = bytes()
        url_download = app.url_path_for(name_download, **url_params)
        with test_client.get(url_download, stream=True) as resp:
            assert resp.status_code == HTTP_200_OK
            for chunk in resp.iter_content():
                result += chunk

        src_hash = hashlib.md5(data).hexdigest()
        dst_hash = hashlib.md5(result).hexdigest()
        assert src_hash == dst_hash

    # Check binaries
    url_upload = "upload_revision_binaries"
    url_download = "download_revision_binaries"
    upload_download_compare(url_upload, url_download, small_tar())

    # Check seeds
    url_upload = "upload_revision_seeds"
    url_download = "download_revision_seeds"
    upload_download_compare(url_upload, url_download, small_tar())

    # Check config
    url_upload = "upload_revision_config"
    url_download = "download_revision_config"
    upload_download_compare(url_upload, url_download, small_json())


def test_download_files_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to download files of not existent fuzzer

    Succeeds
        If download failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    url = app.url_path_for("download_revision_binaries", **url_params)
    with test_client.get(url, stream=True) as resp:
        assert resp.status_code == HTTP_404_NOT_FOUND

    url = app.url_path_for("download_revision_seeds", **url_params)
    with test_client.get(url, stream=True) as resp:
        assert resp.status_code == HTTP_404_NOT_FOUND

    url = app.url_path_for("download_revision_config", **url_params)
    with test_client.get(url, stream=True) as resp:
        assert resp.status_code == HTTP_404_NOT_FOUND


def test_download_files_not_found_in_s3(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_image: ORMImage,
):
    """
    Description
        Try to download files of not existent fuzzer

    Succeeds
        If download failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create revision with custom status
    revision = create_custom_revision(
        "custom",
        default_fuzzer.id,
        default_image.id,
        status=ORMRevisionStatus.unverified,
        health=ORMHealth.ok,
        binaries=ORMUploadStatus(uploaded=True),
        seeds=ORMUploadStatus(uploaded=True),
        config=ORMUploadStatus(uploaded=True),
    )

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": revision.id,
    }

    url = app.url_path_for("download_revision_binaries", **url_params)
    with test_client.get(url, stream=True) as resp:
        assert resp.status_code == HTTP_404_NOT_FOUND

    url = app.url_path_for("download_revision_seeds", **url_params)
    with test_client.get(url, stream=True) as resp:
        assert resp.status_code == HTTP_404_NOT_FOUND

    url = app.url_path_for("download_revision_config", **url_params)
    with test_client.get(url, stream=True) as resp:
        assert resp.status_code == HTTP_404_NOT_FOUND


def test_switch_start_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_image: ORMImage,
):
    """
    Description
        Try to start revision while other already running

    Succeeds
        If no errors occurred
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    running_revision = create_custom_revision(
        "running",
        default_fuzzer.id,
        default_image.id,
        status=ORMRevisionStatus.running,
        binaries=ORMUploadStatus(uploaded=True),
    )

    rev_to_start = create_custom_revision(
        "to start",
        default_fuzzer.id,
        default_image.id,
        status=ORMRevisionStatus.unverified,
        binaries=ORMUploadStatus(uploaded=True),
    )

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": rev_to_start.id,
    }

    # Start revision(restart for unverified state)
    url_start = app.url_path_for("restart_revision", **url_params)
    resp = test_client.post(url_start)
    assert resp.status_code == HTTP_200_OK


def test_start_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
):
    """
    Description
        Try to start revision which is in stopped state

    Succeeds
        If no errors occurred
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Upload binaries
    url_binaries = app.url_path_for("upload_revision_binaries", **url_params)
    resp = test_client.put(url_binaries, data=small_tar())
    assert resp.status_code == HTTP_200_OK

    # Start revision(restart for unverified state)
    url_start = app.url_path_for("restart_revision", **url_params)
    resp = test_client.post(url_start)
    assert resp.status_code == HTTP_200_OK


def test_start_revision_failed_not_uploaded(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_revision: ORMRevision,
    settings: AppSettings,
):
    """
    Description
        Try to start revision.
        But binaries have not been uploaded yet

    Succeeds
        If operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": default_revision.id,
    }

    # Upload seeds
    headers = {"content-length": str(settings.revision.seeds_upload_limit)}
    url_seeds = app.url_path_for("upload_revision_seeds", **url_params)
    config = {"seeds": ("seeds.tar.gz", small_bytes(), "application/tar+gzip")}
    resp = test_client.put(url_seeds, files=config, headers=headers)
    assert resp.status_code == HTTP_422_UNPROCESSABLE_ENTITY

    # Upload config
    url_config = app.url_path_for("upload_revision_config", **url_params)
    config = {"config": ("config.json", small_bytes(), "application/json")}
    resp = test_client.put(url_config, files=config)
    assert resp.status_code == HTTP_422_UNPROCESSABLE_ENTITY

    # Start revision (binaries not uploaded)
    url_start = app.url_path_for("start_revision", **url_params)
    resp = test_client.post(url_start)
    assert resp.status_code == HTTP_409_CONFLICT


@pytest.mark.parametrize(
    argnames="status",
    argvalues=[
        ORMRevisionStatus.running,
    ],
)
def test_start_revision_failed_bad_status(
    status: ORMRevisionStatus,
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_image: ORMImage,
):
    """
    Description
        Try to start revision.
        But it can not be run in current status

    Succeeds
        If operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create revision with custom status
    revision = create_custom_revision(
        "custom",
        default_fuzzer.id,
        default_image.id,
        status=status,
        binaries=ORMUploadStatus(uploaded=True),
    )

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": revision.id,
    }

    # Start revision (bad status)
    url_start = app.url_path_for("start_revision", **url_params)
    resp = test_client.post(url_start)
    json = resp.json()

    # Ensure start failed
    assert resp.status_code == HTTP_409_CONFLICT
    if revision.status == ORMRevisionStatus.running:
        assert json["code"] == E_REVISION_ALREADY_RUNNING
    else:
        assert json["code"] == E_REVISION_CAN_ONLY_RESTART


def test_stop_revision_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_image: ORMImage,
):
    """
    Description
        Try to stop revision.

    Succeeds
        If no errors encountered
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create revision to start
    revision = create_custom_revision(
        "custom",
        default_fuzzer.id,
        default_image.id,
        status=ORMRevisionStatus.running,
        is_verified=True,
    )

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": revision.id,
    }

    # Stop revision
    url_start = app.url_path_for("stop_revision", **url_params)
    assert test_client.post(url_start).status_code == HTTP_200_OK


@pytest.mark.parametrize(
    argnames="status",
    argvalues=[
        ORMRevisionStatus.unverified,
        ORMRevisionStatus.stopped,
    ],
)
def test_stop_revision_failed_bad_status(
    status: ORMRevisionStatus,
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    default_image: ORMImage,
):
    """
    Description
        Try to stop revision.
        But it can not be stopped in current status

    Succeeds
        If operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Create revision with custom status
    revision = create_custom_revision(
        "custom", default_fuzzer.id, default_image.id, status=status
    )

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": default_fuzzer.id,
        "revision_id": revision.id,
    }

    # Stop revision (bad status)
    url = app.url_path_for("stop_revision", **url_params)
    resp = test_client.post(url)
    json = resp.json()

    # Ensure stop failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_REVISION_IS_NOT_RUNNING
