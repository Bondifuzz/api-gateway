from typing import List

import pytest
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient
from starlette.status import *

from api_gateway.app.api.base import DeleteActions, UserObjectRemovalState
from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMFuzzer, ORMProject, ORMUser

from .conftest import (
    FUZZER_FIELDS,
    ITEM_LIST_FIELDS,
    NO_SUCH_ID,
    FuzzerModel,
    FuzzerUpdateModel,
    LoginModel,
    UserModel,
    UserUpdateModel,
    unordered_unique_match,
)


def test_client_is_not_admin(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Checks that admin admin can not have fuzzers

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
    }

    # List fuzzers
    resp = test_client.get(app.url_path_for("list_fuzzers", **url_params))
    json = resp.json()

    # Ensure, that root can not have fuzzers
    assert json["code"] == E_CLIENT_ACCOUNT_REQUIRED
    assert resp.status_code == HTTP_403_FORBIDDEN


def test_create_fuzzer_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    fuzzer: FuzzerModel,
):
    """
    Description
        Create fuzzer with provided API.
        Then checks that fuzzer was created correctly.

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
    }

    # Create fuzzer
    url = app.url_path_for("create_fuzzer", **url_params)
    resp = test_client.post(url, json=fuzzer.dict())
    assert resp.status_code == HTTP_201_CREATED


def test_create_fuzzer_already_exists(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    fuzzer: FuzzerModel,
):
    """
    Description
        Try to create fuzzer which already exists

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
    }

    # Create fuzzer
    url = app.url_path_for("create_fuzzer", **url_params)
    resp = test_client.post(url, json=fuzzer.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Create fuzzer twice
    resp = test_client.post(url, json=fuzzer.dict())
    json = resp.json()

    # Ensure second creation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_FUZZER_EXISTS


def test_create_fuzzer_in_trashbin(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    fuzzer: FuzzerModel,
):
    """
    Description
        Try to create fuzzer which was moved to trash bin

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
    }

    # Create fuzzer
    url_create = app.url_path_for("create_fuzzer", **url_params_create)
    resp = test_client.post(url_create, json=fuzzer.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Set url params
    url_params_delete = {
        "fuzzer_id": json["id"],
        **url_params_create,
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer (will be moved to trash bin)
    url_delete = app.url_path_for("delete_fuzzer", **url_params_delete)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Create fuzzer again
    resp = test_client.post(url_create, json=fuzzer.dict())

    # Ensure creation success
    assert resp.status_code == HTTP_201_CREATED


def test_get_fuzzer_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to get fuzzer

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

    # Get fuzzer
    resp = test_client.get(app.url_path_for("get_fuzzer", **url_params))
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in FUZZER_FIELDS)


def test_get_fuzzer_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to get non existent fuzzer

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
        "fuzzer_id": NO_SUCH_ID,
    }

    # Get fuzzer
    url_get = app.url_path_for("get_fuzzer", **url_params)
    assert test_client.get(url_get).status_code == HTTP_404_NOT_FOUND


def test_get_fuzzer_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to get fuzzer which has been deleted

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
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer (will be moved to trash bin)
    url_delete = app.url_path_for("delete_fuzzer", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Get deleted fuzzer
    url_get = app.url_path_for("get_fuzzer", **url_params)
    resp = test_client.get(url_get)
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in FUZZER_FIELDS)


def test_list_fuzzers_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
):
    """
    Description
        Try to list fuzzers

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
    }

    # List fuzzers
    resp = test_client.get(app.url_path_for("list_fuzzers", **url_params))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of users
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert all(k in json["items"][0] for k in FUZZER_FIELDS)


@pytest.mark.parametrize(
    argnames="removal_state",
    argvalues=[UserObjectRemovalState.trash_bin, UserObjectRemovalState.all],
)
def test_list_fuzzers_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    removal_state: UserObjectRemovalState,
):
    """
    Description
        Try to list fuzzers, with deleted ones

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
    }

    # Set url params for delete
    url_params_delete = {
        "fuzzer_id": default_fuzzer.id,
        **url_params_list,
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer
    url_delete = app.url_path_for("delete_fuzzer", **url_params_delete)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # List fuzzers
    resp = test_client.get(
        url=app.url_path_for("list_fuzzers", **url_params_list),
        params=dict(
            pg_size=100,
            removal_state=removal_state,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of fuzzers with deleted one
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert len(json["items"]) == 1

    first_item = json["items"][0]
    assert first_item["name"] == default_fuzzer.name


def test_count_fuzzers_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_fuzzers: List[ORMFuzzer],
    default_project: ORMProject,
):
    """
    Description
        Try to get count of fuzzers

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
    }

    # Count fuzzers with page size 10
    url = app.url_path_for("get_fuzzer_count", **url_params)
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    pg_size = json["pg_size"]
    pg_total = json["pg_total"]
    cnt_total = json["cnt_total"]

    # Ensure count of records is equal to
    # count of created fuzzers + default fuzzer
    assert cnt_total == len(list_of_fuzzers) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1


def test_count_fuzzer_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_fuzzers: List[ORMFuzzer],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
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
    }

    # Set url params for delete
    url_params_delete = {
        "fuzzer_id": default_fuzzer.id,
        **url_params_count,
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer
    url_delete = app.url_path_for("delete_fuzzer", **url_params_delete)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Count users with page size 10
    resp = test_client.get(
        url=app.url_path_for("get_fuzzer_count", **url_params_count),
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
    # created fuzzers + deleted fuzzer
    assert cnt_total == len(list_of_fuzzers) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1

    # Count only deleted fuzzers
    resp = test_client.get(
        url=app.url_path_for("get_fuzzer_count", **url_params_count),
        params=dict(
            removal_state=UserObjectRemovalState.trash_bin,
        ),
    )
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure count of records is correct
    assert json["cnt_total"] == 1


def test_list_fuzzer_pagination(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_fuzzers: List[ORMUser],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to list fuzzers, using pagination

    Succeeds
        If no errors were encountered
    """

    created_fuzzers = [fuzzer.name for fuzzer in list_of_fuzzers]
    fetched_fuzzers = []

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for list
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
    }

    # List fuzzers using pagination
    created_fuzzers.append(default_fuzzer.name)
    url = app.url_path_for("list_fuzzers", **url_params)
    pg_num = 0

    while True:

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        # Stop when page is empty
        if not json["items"]:
            break

        names = [fuzzer["name"] for fuzzer in json["items"]]
        fetched_fuzzers.extend(names)
        pg_num += 1

    # Ensure created fuzzers match fetched fuzzers
    assert unordered_unique_match(created_fuzzers, fetched_fuzzers)


def test_list_fuzzer_pagination_with_count(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    list_of_fuzzers: List[ORMUser],
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to list fuzzers, using pagination and count endpoint

    Succeeds
        If no errors were encountered
    """

    created_fuzzers = [fuzzer.name for fuzzer in list_of_fuzzers]
    fetched_fuzzers = []

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for list
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
    }

    # Count fuzzers with page size 10
    created_fuzzers.append(default_fuzzer.name)
    url = app.url_path_for("get_fuzzer_count", **url_params)
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # List fuzzers using pagination
    pg_size = json["pg_size"]
    pg_total = json["pg_total"]

    url = app.url_path_for("list_fuzzers", **url_params)
    for pg_num in range(pg_total):

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num, pg_size=pg_size))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        names = [fuzzer["name"] for fuzzer in json["items"]]
        fetched_fuzzers.extend(names)

    # Ensure created fuzzers match fetched fuzzers
    assert unordered_unique_match(created_fuzzers, fetched_fuzzers)


def test_modify_fuzzer_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to modify fuzzer

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

    # Update fuzzer
    updated_name = "myproj"
    updates = FuzzerUpdateModel(name=updated_name)
    url_update = app.url_path_for("update_fuzzer", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK

    # Get fuzzer
    resp = test_client.get(app.url_path_for("get_fuzzer", **url_params))
    json = resp.json()

    # Ensure changes are correct (in fact)
    assert json["name"] == updated_name


def test_modify_fuzzer_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
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

    # Set url params
    url_params = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
        "fuzzer_id": NO_SUCH_ID,
    }

    # Update fuzzer which does not exist
    updates = UserUpdateModel(name="aaa")
    url_update = app.url_path_for("update_fuzzer", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_FUZZER_NOT_FOUND


def test_modify_fuzzer_name_exists(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
    fuzzer: FuzzerModel,
):
    """
    Description
        Try to modify fuzzer and update his name
        with another name of existent fuzzer

    Succeeds
        If modify operation failed
    """

    # Login as default user
    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Set url params for create
    url_params_create = {
        "user_id": json["user_id"],
        "project_id": default_project.id,
    }

    # Set url params for update
    url_params_update = {
        "fuzzer_id": default_fuzzer.id,
        **url_params_create,
    }

    # Create another fuzzer
    url_create = app.url_path_for("create_fuzzer", **url_params_create)
    resp = test_client.post(url_create, json=fuzzer.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Update fuzzer with existing fuzzer name
    updates = FuzzerUpdateModel(name=fuzzer.name)
    url_update = app.url_path_for("update_fuzzer", **url_params_update)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_FUZZER_EXISTS


def test_modify_fuzzer_deleted(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to modify fuzzer moved to trash bin

    Succeeds
        If modify operation failed
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
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer
    url_delete = app.url_path_for("delete_fuzzer", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Update fuzzer which was deleted
    updates = FuzzerUpdateModel(name="aaa")
    url_update = app.url_path_for("update_fuzzer", **url_params)
    resp = test_client.patch(url_update, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_FUZZER_DELETED


def test_delete_fuzzer_ok(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
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
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer
    url_delete = app.url_path_for("delete_fuzzer", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK


def test_delete_fuzzer_not_found(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
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
        "fuzzer_id": NO_SUCH_ID,
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer
    url_delete = app.url_path_for("delete_fuzzer", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    json = resp.json()

    # Ensure delete operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_FUZZER_NOT_FOUND


def test_delete_fuzzer_twice(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    default_project: ORMProject,
    default_fuzzer: ORMFuzzer,
):
    """
    Description
        Try to delete fuzzer twice

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
    }
    body_params_delete = {"action": DeleteActions.delete, "no_backup": False}

    # Delete fuzzer
    url_delete = app.url_path_for("delete_fuzzer", **url_params)
    resp = test_client.delete(url_delete, params=body_params_delete)
    assert resp.status_code == HTTP_200_OK

    # Delete fuzzer second time
    resp = test_client.delete(url_delete, params=body_params_delete)
    json = resp.json()

    # Ensure second delete operation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_FUZZER_DELETED


def test_access_admin(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    default_project: ORMProject,
    default_user: ORMUser,
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

    # Set url params
    url_params = {
        "user_id": default_user.id,
        "project_id": default_project.id,
    }

    # List fuzzers
    resp = test_client.get(app.url_path_for("list_fuzzers", **url_params))
    assert resp.status_code == HTTP_200_OK


def test_access_another_user(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
    root_login_data: LoginModel,
    default_project: ORMProject,
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
    }

    # Try to list fuzzers belonging to another user
    resp = test_client.get(app.url_path_for("list_fuzzers", **url_params))
    assert resp.status_code == HTTP_403_FORBIDDEN
