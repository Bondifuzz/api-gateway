import pytest
from starlette.status import *

from api_gateway.app.api.error_codes import *
from api_gateway.app.database.orm import ORMEngineID, ORMLangID, ORMImageType, ORMLang
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

from .conftest import ITEM_LIST_FIELDS, LANG_FIELDS, ENGINE_FIELDS, INTEGRATION_TYPE_FIELDS, LoginModel, create_custom_image


def test_list_platform_config_langs(
    app: FastAPI,
    test_client: TestClient,
):
    """
    Description
        Try to list all registered langs

    Succeeds
        If no errors encountered
    """

    resp = test_client.get(app.url_path_for("list_platform_langs"))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()


    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert len(json["items"]) == 1 # default lang
    assert all(k in json["items"][0] for k in LANG_FIELDS)


def test_list_platform_config_engines(
    app: FastAPI,
    test_client: TestClient,
):
    """
    Description
        Try to list all registered engines

    Succeeds
        If no errors encountered
    """

    resp = test_client.get(app.url_path_for("list_platform_engines"))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()


    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert len(json["items"]) == 1 # default engine
    assert all(k in json["items"][0] for k in ENGINE_FIELDS)


def test_list_platform_config_integration_types(
    app: FastAPI,
    test_client: TestClient,
):
    """
    Description
        Try to list all registered integration types

    Succeeds
        If no errors encountered
    """

    resp = test_client.get(app.url_path_for("list_platform_integration_types"))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()


    assert all(k in json for k in ITEM_LIST_FIELDS)
    assert len(json["items"]) == 1 # default integration type
    assert all(k in json["items"][0] for k in INTEGRATION_TYPE_FIELDS)


def test_get_platform_config(
    app: FastAPI,
    test_client: TestClient,
):
    """
    Description
        Try to get platform configuration

    Succeeds
        If no errors encountered
    """

    resp = test_client.get(app.url_path_for("list_platform_integration_types"))
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    # TODO: some validation?


# TODO: rewrite
@pytest.mark.skip
def test_list_available_images(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
):
    """
    Description
        Try to list available images corresponding to provided fuzzer type, lang

    Succeeds
        If list of available images is correct
    """

    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    user_id = resp.json()["user_id"]

    #
    # Create a set of different images
    #

    for i, image_type in enumerate(ORMImageType):
        for j, lang in enumerate(ORMLangID):
            for k, engine in enumerate(ORMEngineID):
                create_custom_image(
                    owner_id=user_id,
                    name=f"image-{i}-{j}-{k}",
                    image_type=image_type,
                    engine=engine,
                    lang=lang,
                )

    #
    # Now find available
    #

    lang = ORMLangID.python
    engine = ORMEngineID.libfuzzer

    query_params = {
        "user_id": user_id,
        "engine": engine.value,
        "lang": lang.value,
    }

    url = app.url_path_for("list_available_fuzzer_images")
    resp = test_client.get(url, params=query_params)
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    #
    # Ensure number of available images is correct
    #

    items = json["items"]
    assert len(items) == 2

    assert items[0]["engine"] == engine
    assert items[0]["lang"] == lang
    assert items[1]["engine"] == engine
    assert items[1]["lang"] == lang


# TODO: rewrite
@pytest.mark.skip
def test_count_available_images(
    app: FastAPI,
    test_client: TestClient,
    default_login_data: LoginModel,
):
    """
    Description
        Try to list available images corresponding to provided fuzzer engine, lang

    Succeeds
        If list of available images is correct
    """

    resp = test_client.post(app.url_path_for("login"), json=default_login_data.dict())
    assert resp.status_code == HTTP_200_OK
    user_id = resp.json()["user_id"]

    #
    # Create a set of different images
    #

    for i, image_type in enumerate(ORMImageType):
        for j, lang in enumerate(ORMLangID):
            for k, engine in enumerate(ORMEngineID):
                create_custom_image(
                    owner_id=user_id,
                    name=f"image-{i}-{j}-{k}",
                    image_type=image_type,
                    engine=engine,
                    lang=lang,
                )

    #
    # Now find available
    #

    lang = ORMLangID.python
    engine = ORMEngineID.libfuzzer

    query_params = {
        "user_id": user_id,
        "engine": engine.value,
        "lang": lang.value,
    }

    url = app.url_path_for("count_available_fuzzer_images")
    resp = test_client.get(url, params=query_params)
    assert resp.status_code == HTTP_200_OK
    json = resp.json()

    #
    # Ensure number of available images is correct
    #

    assert json["cnt_total"] == 2
