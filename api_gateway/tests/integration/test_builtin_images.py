from typing import List

from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMImage, ORMUser
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from .conftest import (
    IMAGE_FIELDS,
    ITEM_LIST_FIELDS,
    NO_SUCH_ID,
    ImageModel,
    ImageUpdateModel,
    LoginModel,
    UserModel,
    UserUpdateModel,
    gen_builtin_image,
    get_login_data,
    unordered_unique_match,
)


def test_administrator_required(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    usual_user: UserModel,
):
    """
    Description
        Checks account has sufficient access rights to manage builtin images

    Succeeds
        If only administrator is able to manage builtin images
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    resp = test_client.post(app.url_path_for("create_user"), json=usual_user.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Login as builtin image
    login_data = get_login_data(usual_user)
    resp = test_client.post(app.url_path_for("login"), json=login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Try to do some admin stuff
    resp = test_client.get(app.url_path_for("list_builtin_images"))
    json = resp.json()

    # Ensure, that usual user is not able to do admin stuff
    assert resp.status_code == HTTP_403_FORBIDDEN
    assert json["code"] == E_ADMIN_REQUIRED


def test_create_image_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Create image with provided API.
        Then checks that image was created correctly.

    Succeeds
        If no errors were encountered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    operation = "create_builtin_image"
    resp = test_client.post(app.url_path_for(operation), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED


def test_create_image_already_exists(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Try to create image which already exists

    Succeeds
        If creation failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    operation = "create_builtin_image"
    resp = test_client.post(app.url_path_for(operation), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Create builtin image twice
    resp = test_client.post(app.url_path_for(operation), json=builtin_image.dict())
    json = resp.json()

    # Ensure second creation failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_IMAGE_EXISTS


def test_get_image_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Try to get image

    Succeeds
        If no errors were encountered
    """

    operation = "create_builtin_image"
    operation_g = "get_builtin_image"

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    resp = test_client.post(app.url_path_for(operation), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Get image
    url = app.url_path_for(operation_g, image_id=json["id"])
    resp = test_client.get(url)
    json = resp.json()

    # Ensure record found and has data fields
    assert resp.status_code == HTTP_200_OK
    assert all(k in json for k in IMAGE_FIELDS)


def test_get_image_not_found(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
):
    """
    Description
        Try to get non existent image

    Succeeds
        If get operation failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Get image
    url = app.url_path_for("get_builtin_image", image_id=NO_SUCH_ID)
    assert test_client.get(url).status_code == HTTP_404_NOT_FOUND


def test_list_images_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Try to list images

    Succeeds
        If no errors were encountered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    operation = "create_builtin_image"
    resp = test_client.post(app.url_path_for(operation), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED

    # List images
    resp = test_client.get(app.url_path_for("list_builtin_images"))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # Ensure response contains list of users
    first_item = json["items"][0]
    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert all(k in first_item for k in IMAGE_FIELDS)


def test_count_images_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    list_of_builtin_images: List[ORMUser],
):
    """
    Description
        Try to get count of images

    Succeeds
        If no errors were encountered
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Count users with page size 10
    url = app.url_path_for("get_builtin_image_count")
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    pg_size = json["pg_size"]
    pg_total = json["pg_total"]
    cnt_total = json["cnt_total"]

    # Ensure count of records is equal to
    # count of created images + default image
    assert cnt_total == len(list_of_builtin_images) + 1
    assert pg_size == 10

    # Ensure count of pages is correct
    n_chunks = int(cnt_total / pg_size)
    assert pg_total == n_chunks or pg_total == n_chunks + 1


def test_list_image_pagination(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    list_of_builtin_images: List[ORMUser],
    default_image: ORMImage,
):
    """
    Description
        Try to list images, using pagination

    Succeeds
        If no errors were encountered
    """

    created_images = [img.name for img in list_of_builtin_images]
    fetched_images = []

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # List images using pagination
    created_images.append(default_image.name)
    url = app.url_path_for("list_builtin_images")
    pg_num = 0

    while True:

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        # Stop when page is empty
        if not json["items"]:
            break

        names = [user["name"] for user in json["items"]]
        fetched_images.extend(names)
        pg_num += 1

    # Ensure created images match fetched images
    assert unordered_unique_match(created_images, fetched_images)


def test_list_image_pagination_with_count(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    list_of_builtin_images: List[ORMUser],
    default_image: ORMImage,
):
    """
    Description
        Try to list images, using pagination and count endpoint

    Succeeds
        If no errors were encountered
    """

    created_images = [image.name for image in list_of_builtin_images]
    fetched_images = []

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Count images with page size 10
    created_images.append(default_image.name)
    url = app.url_path_for("get_builtin_image_count")
    resp = test_client.get(url, params=dict(pg_size=10))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # List images using pagination
    pg_size = json["pg_size"]
    pg_total = json["pg_total"]

    url = app.url_path_for("list_builtin_images")
    for pg_num in range(pg_total):

        # Each page contains up to `pg_size` records
        resp = test_client.get(url, params=dict(pg_num=pg_num, pg_size=pg_size))
        assert resp.status_code == HTTP_200_OK
        json = resp.json()

        names = [image["name"] for image in json["items"]]
        fetched_images.extend(names)

    # Ensure created images match fetched images
    assert unordered_unique_match(created_images, fetched_images)


def test_modify_image_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Try to modify image

    Succeeds
        If no errors were encountered
    """

    op_create = "create_builtin_image"
    op_update = "update_builtin_image"
    operation_g = "get_builtin_image"

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create image
    resp = test_client.post(app.url_path_for(op_create), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED
    created_image = resp.json()

    # Update image
    updated_name = "myimg"
    updates = ImageUpdateModel(name=updated_name)
    url = app.url_path_for(op_update, image_id=created_image["id"])
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
    assert resp.status_code == HTTP_200_OK

    # Get image
    url = app.url_path_for(operation_g, image_id=created_image["id"])
    resp = test_client.get(url)
    json = resp.json()

    # Ensure changes are correct (in fact)
    assert json["name"] == updated_name


def test_modify_image_not_found(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
):
    """
    Description
        Try to modify non existent image

    Succeeds
        If modify operation failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Update image which does not exist
    updates = UserUpdateModel(name="aaa")
    url = app.url_path_for("update_builtin_image", image_id=NO_SUCH_ID)
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_IMAGE_NOT_FOUND


def test_modify_image_name_exists(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
):
    """
    Description
        Try to modify image and update his imagename
        with another imagename of existent image

    Succeeds
        If modify operation failed
    """

    op_create = "create_builtin_image"
    op_update = "update_builtin_image"

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create image (1)
    image1 = gen_builtin_image()
    resp = test_client.post(app.url_path_for(op_create), json=image1.dict())
    assert resp.status_code == HTTP_201_CREATED

    # Create image (2)
    image2 = gen_builtin_image()
    resp = test_client.post(app.url_path_for(op_create), json=image2.dict())
    assert resp.status_code == HTTP_201_CREATED
    created_image2 = resp.json()

    # Update image with existing image name
    updates = UserUpdateModel(name=image1.name)
    url = app.url_path_for(op_update, image_id=created_image2["id"])
    resp = test_client.patch(url, json=updates.dict(exclude_unset=True))
    json = resp.json()

    # Ensure update failed
    assert resp.status_code == HTTP_409_CONFLICT
    assert json["code"] == E_IMAGE_EXISTS


def test_delete_image_ok(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Try to delete image

    Succeeds
        If no errors were encountered
    """

    op_create = "create_builtin_image"
    op_delete = "delete_builtin_image"

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    resp = test_client.post(app.url_path_for(op_create), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Delete image
    url = app.url_path_for(op_delete, image_id=json["id"])
    assert test_client.delete(url).status_code == HTTP_200_OK


def test_delete_image_not_found(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
):
    """
    Description
        Try to delete non existent image

    Succeeds
        If delete operation failed
    """

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Delete image
    url = app.url_path_for("delete_builtin_image", image_id=NO_SUCH_ID)
    resp = test_client.delete(url)
    json = resp.json()

    # Ensure delete operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_IMAGE_NOT_FOUND


def test_delete_image_twice(
    app: FastAPI,
    test_client: TestClient,
    root_login_data: LoginModel,
    builtin_image: ImageModel,
):
    """
    Description
        Try to delete image twice

    Succeeds
        If second delete operation failed
    """

    op_create = "create_builtin_image"
    op_delete = "delete_builtin_image"

    # Login as root
    resp = test_client.post(app.url_path_for("login"), json=root_login_data.dict())
    assert resp.status_code == HTTP_200_OK

    # Create builtin image
    resp = test_client.post(app.url_path_for(op_create), json=builtin_image.dict())
    assert resp.status_code == HTTP_201_CREATED
    json = resp.json()

    # Delete image
    url = app.url_path_for(op_delete, image_id=json["id"])
    assert test_client.delete(url).status_code == HTTP_200_OK

    # Delete image second time
    url = app.url_path_for(op_delete, image_id=json["id"])
    resp = test_client.delete(url)
    json = resp.json()

    # Ensure second delete operation failed
    assert resp.status_code == HTTP_404_NOT_FOUND
    assert json["code"] == E_IMAGE_NOT_FOUND
