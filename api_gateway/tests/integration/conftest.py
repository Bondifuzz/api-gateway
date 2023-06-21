import asyncio
import json
import random
import string
import tarfile
from io import BytesIO
from typing import Optional

import pytest
from api_gateway.app.api.models.engines import EngineResponseModel

from api_gateway.app.api.models.images import (
    CreateImageRequestModel,
    ImageResponseModel,
    UpdateImageRequestModel,
)
from api_gateway.app.api.models.integration_types import IntegrationTypeResponseModel
from api_gateway.app.api.models.langs import LangResponseModel
from api_gateway.app.api.models.users import (
    CreateUserRequestModel,
    UserResponseModel,
    AdminUpdateUserRequestModel,
)
from api_gateway.app.api.handlers.auth import LoginRequestModel
from api_gateway.app.api.base import BasePaginatorResponseModel, ItemCountResponseModel
from api_gateway.app.api.handlers.security.csrf import CSRFTokenManager
from api_gateway.app.api.models.fuzzers import (
    CreateFuzzerRequestModel,
    FuzzerResponseModel,
    UpdateFuzzerRequestModel,
)
from api_gateway.app.api.models.projects import (
    CreateProjectRequestModel,
    ProjectResponseModel,
    UpdateProjectRequestModel,
)
from api_gateway.app.api.models.revisions import (
    CreateRevisionRequestModel,
    RevisionResponseModel,
    UpdateRevisionInfoRequestModel,
    UpdateRevisionResourcesRequestModel,
)
from api_gateway.app.database import db_init
from api_gateway.app.database.abstract import IDatabase
from api_gateway.app.database.orm import (
    ORMEngine,
    ORMFuzzer,
    ORMEngineID,
    ORMIntegrationType,
    ORMIntegrationTypeID,
    ORMLang,
    ORMLangID,
    ORMHealth,
    ORMImage,
    ORMImageStatus,
    ORMImageType,
    ORMProject,
    ORMRevision,
    ORMRevisionStatus,
    ORMUploadStatus,
    ORMUser,
    Paginator,
)
from api_gateway.app.main import create_app
from api_gateway.app.message_queue import mq_init
from api_gateway.app.object_storage import ObjectStorage
from api_gateway.app.settings import AppSettings, DefaultUserSettings, load_app_settings
from api_gateway.app.utils import (
    ObjectRemovalState,
    datetime_utcnow,
    rfc3339_add,
    rfc3339_now,
)
from fastapi.applications import FastAPI
from fastapi.testclient import TestClient

USER_FIELDS = UserResponseModel.__fields__.keys()
LANG_FIELDS = LangResponseModel.__fields__.keys()
IMAGE_FIELDS = ImageResponseModel.__fields__.keys()
ENGINE_FIELDS = EngineResponseModel.__fields__.keys()
PROJECT_FIELDS = ProjectResponseModel.__fields__.keys()
FUZZER_FIELDS = FuzzerResponseModel.__fields__.keys()
REVISION_FIELDS = RevisionResponseModel.__fields__.keys()
INTEGRATION_TYPE_FIELDS = IntegrationTypeResponseModel.__fields__.keys()
ITEM_LIST_FIELDS = BasePaginatorResponseModel.__fields__.keys()
ITEM_COUNT_FIELDS = ItemCountResponseModel.__fields__.keys()
PROGRAMMING_LANGS = [lang.value for lang in ORMLangID]

NO_SUCH_ID = "77777777777777"
TEST_SET_SIZE = 50

_root_user: ORMUser = None
_admin_user: ORMUser
_default_user: ORMUser = None
_default_project: ORMProject = None
_default_fuzzer: ORMFuzzer = None
_default_revision: ORMRevision = None
_default_image: ORMImage = None
_default_lang: ORMLang = None
_default_engine: ORMEngine = None
_default_integration_type: ORMIntegrationType = None
_db: IDatabase = None
_app: FastAPI = None


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def settings():
    return load_app_settings()


@pytest.fixture(scope="session")
async def mq(settings):
    mq_app = await mq_init(settings)
    await mq_app.start()
    yield mq_app
    await mq_app.shutdown()


# TODO: clear s3, mq
@pytest.fixture(scope="session")
async def s3(settings):
    _s3 = await ObjectStorage.create(settings)
    yield _s3
    await _s3.close()


@pytest.fixture(scope="session")
async def db(settings: AppSettings):
    global _db
    _db = await db_init(settings)
    yield _db
    await _db.truncate_all_collections()
    await _db.close()


@pytest.fixture(scope="session")
def app(db, s3, mq):
    global _app
    _app = create_app()
    _app.state.db = db
    _app.state.s3 = s3
    _app.state.mq = mq
    return _app


@pytest.fixture(scope="session")
def test_client(app: FastAPI):
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def reset_test_client(test_client: TestClient):
    test_client.cookies.clear()


@pytest.fixture(autouse=True)
async def reset_database(settings: AppSettings, db: IDatabase):

    global _root_user
    global _admin_user
    global _default_user
    global _default_project
    global _default_fuzzer
    global _default_revision
    global _default_image
    global _default_lang
    global _default_engine
    global _default_integration_type

    await db.truncate_all_collections()

    # default integration type
    integration_type = await db.integration_types.create(
        id=ORMIntegrationTypeID.jira,
        display_name="Jira",
        twoway=True,
    )

    # default lang
    lang = await db.langs.create(
        id=ORMLangID.cpp, 
        display_name="C++",
    )

    # default engine
    engine = await db.engines.create(
        id=ORMEngineID.libfuzzer,
        display_name="LibFuzzer",
        lang_ids=[lang.id]
    )

    # default image
    image = await db.images.create(
        name="default",
        description="Default image",
        project_id=None, # shared
        engines=[engine.id],
        status=ORMImageStatus.ready,
    )

    root = await db.users.create_system_admin(settings.root)
    user = await db.users.create_default_user(settings.default_user)

    # TODO: default pool id/rewrite
    project = await db.projects.create_default_project(user.id, "default")
    fuzzer = await db.fuzzers.create_default_fuzzer(project.id)
    revision = await db.revisions.create_default(fuzzer.id, image.id)

    admin = await db.users.create_default_user(
        DefaultUserSettings(
            username=settings.default_user.username + "_admin",
            password=settings.default_user.password + "_admin",
            email=settings.default_user.email,
        )
    )
    admin.is_admin = True
    await db.users.update(admin)

    _root_user = root
    _admin_user = admin
    _default_user = user
    _default_project = project
    _default_fuzzer = fuzzer
    _default_revision = revision
    _default_image = image
    _default_lang = lang
    _default_engine = engine
    _default_integration_type = integration_type


class UserModel(CreateUserRequestModel):
    pass


class UserUpdateModel(AdminUpdateUserRequestModel):
    pass


class LoginModel(LoginRequestModel):
    pass


class ImageModel(CreateImageRequestModel):
    pass


class ImageUpdateModel(UpdateImageRequestModel):
    pass


class ProjectModel(CreateProjectRequestModel):
    pass


class ProjectUpdateModel(UpdateProjectRequestModel):
    pass


class FuzzerModel(CreateFuzzerRequestModel):
    pass


class FuzzerUpdateModel(UpdateFuzzerRequestModel):
    pass


class RevisionModel(CreateRevisionRequestModel):
    pass


class RevisionUpdateModel(UpdateRevisionInfoRequestModel):
    pass


class RevisionResUpdateModel(UpdateRevisionResourcesRequestModel):
    pass


def get_login_data(user: UserModel):
    return LoginModel(
        username=user.name,
        password=user.password,
        session_metadata=random_string(),
    )


@pytest.fixture()
def root_login_data(settings: AppSettings):
    return LoginModel(
        username=settings.root.username,
        password=settings.root.password,
        session_metadata=random_string(),
    )


@pytest.fixture()
def sys_admin_login_data(root_login_data: LoginModel):
    return root_login_data


@pytest.fixture()
def admin_login_data(settings: AppSettings):
    return LoginModel(
        username=settings.default_user.username + "_admin",
        password=settings.default_user.username + "_admin",
        session_metadata=random_string(),
    )


@pytest.fixture()
def user_login_data(default_login_data: LoginModel):
    return default_login_data


@pytest.fixture()
def csrf_token_mgr(settings: AppSettings):
    return CSRFTokenManager(settings)


@pytest.fixture()
def default_login_data(settings: AppSettings):
    return LoginModel(
        username=settings.default_user.username,
        password=settings.default_user.password,
        session_metadata=random_string(),
    )


def gen_usual_user():
    return UserModel(
        name=random_string(),
        password=random_string(),
        display_name="Diplay Name",
        email="sample@mail.ru",
        is_admin=False,
    )


def gen_admin_user():
    user = gen_usual_user()
    user.is_admin = True
    return user


def gen_builtin_image():
    return ImageModel(
        name=random_string(),
        description=random_string(),
        engine=ORMEngineID.libfuzzer,
        lang=ORMLangID.cpp,
    )


def gen_project():
    return ProjectModel(
        name=random_string(),
        description=random_string(),
    )


def gen_fuzzer():
    return FuzzerModel(
        name=random_string(),
        description=random_string(),
        engine=ORMEngineID.libfuzzer,
        lang=ORMLangID.cpp,
        ci_integration=False,
    )


def gen_revision(image_id: Optional[str] = None):

    if not image_id:
        image_id = _default_image.id

    return RevisionModel(
        name=random_string(),
        description=random_string(),
        image_id=image_id,
        cpu_usage=1000,
        ram_usage=1000,
        tmpfs_size=200,
    )


@pytest.fixture()
def builtin_image():
    return gen_builtin_image()


@pytest.fixture()
def default_image():
    return _default_image


@pytest.fixture()
def usual_user():
    return gen_usual_user()


@pytest.fixture()
def admin_user():
    return gen_admin_user()


@pytest.fixture()
def default_user():
    return _default_user


@pytest.fixture()
def default_lang():
    return _default_lang


@pytest.fixture()
def default_engine():
    return _default_engine


@pytest.fixture()
def default_integration_type():
    return _default_integration_type


@pytest.fixture()
def root_user():
    return _root_user


@pytest.fixture()
def project():
    return gen_project()


@pytest.fixture()
def default_project():
    return _default_project


@pytest.fixture()
def fuzzer():
    return gen_fuzzer()


@pytest.fixture()
def default_fuzzer():
    return _default_fuzzer


@pytest.fixture()
def revision():
    return gen_revision()


@pytest.fixture()
def default_revision():
    return _default_revision


def create_custom_image(
    name: str,
    project_id: Optional[str] = None,
    image_type=ORMImageType.custom,
    engine=ORMEngineID.libfuzzer,
    lang=ORMLangID.cpp,
    image_status=ORMImageStatus.ready,
):
    # TODO: rewrite
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        _db.images.create(
            name=name,
            project_id=project_id,
            description="Some image",
            engines=[engine],
            status=image_status,
        )
    )


def create_custom_revision(
    name: str,
    fuzzer_id: str,
    image_id: str,
    status=ORMRevisionStatus.unverified,
    health=ORMHealth.err,
    binaries=ORMUploadStatus(uploaded=False),
    seeds=ORMUploadStatus(uploaded=False),
    config=ORMUploadStatus(uploaded=False),
    last_start_date: Optional[str] = None,
    last_stop_date: Optional[str] = None,
    is_verified=False,
):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        _db.revisions.create(
            name=name,
            description="Some revision",
            fuzzer_id=fuzzer_id,
            image_id=image_id,
            status=status,
            health=health,
            binaries=binaries,
            seeds=seeds,
            config=config,
            is_verified=is_verified,
            created=rfc3339_now(),
            last_start_date=last_start_date,
            last_stop_date=last_stop_date,
            cpu_usage=1000,
            ram_usage=1000,
            tmpfs_size=1000,
        )
    )


@pytest.fixture()
async def present_users(db: IDatabase):
    await db.users.generate_test_set(TEST_SET_SIZE, "present_users")
    yield await db.users.list(
        paginator=Paginator(0, 0xFFFFFFFF),
        removal_state=ObjectRemovalState.present,
    )


@pytest.fixture()
async def present_user(db: IDatabase):
    users = await db.users.generate_test_set(1, "present_user")
    yield users[0]


@pytest.fixture()
async def present_admin(db: IDatabase):
    users = await db.users.generate_test_set(1, "present_admin")
    users[0].is_admin = True
    await db.users.update(users[0])
    yield users[0]


@pytest.fixture()
async def trashbin_users(db: IDatabase, settings: AppSettings):
    tb_users = await db.users.generate_test_set(TEST_SET_SIZE, "trashbin_users")
    erasure_date = rfc3339_add(datetime_utcnow(), settings.trashbin.expiration_seconds)
    for user in tb_users:
        user.erasure_date = erasure_date
        await db.users.update(user)

    yield await db.users.list(
        paginator=Paginator(0, 0xFFFFFFFF),
        removal_state=ObjectRemovalState.trash_bin,
    )


@pytest.fixture()
async def trashbin_user(db: IDatabase, settings: AppSettings):
    users = await db.users.generate_test_set(1, "trashbin_user")
    users[0].erasure_date = rfc3339_add(
        datetime_utcnow(), settings.trashbin.expiration_seconds
    )
    await db.users.update(users[0])
    yield users[0]


@pytest.fixture()
async def trashbin_admin(db: IDatabase, settings: AppSettings):
    users = await db.users.generate_test_set(1, "trashbin_admin")
    users[0].is_admin = True
    users[0].erasure_date = rfc3339_add(
        datetime_utcnow(), settings.trashbin.expiration_seconds
    )
    await db.users.update(users[0])
    yield users[0]


@pytest.fixture()
async def erasing_users(db: IDatabase):
    er_users = await db.users.generate_test_set(TEST_SET_SIZE, "erasing_users")
    erasure_date = rfc3339_now()
    for user in er_users:
        user.erasure_date = erasure_date
        await db.users.update(user)

    yield await db.users.list(
        paginator=Paginator(0, 0xFFFFFFFF),
        removal_state=ObjectRemovalState.erasing,
    )


@pytest.fixture()
async def erasing_user(db: IDatabase):
    users = await db.users.generate_test_set(1, "erasing_user")
    users[0].erasure_date = rfc3339_now()
    await db.users.update(users[0])
    yield users[0]


@pytest.fixture()
async def erasing_admin(db: IDatabase):
    users = await db.users.generate_test_set(1, "erasing_admin")
    users[0].is_admin = True
    users[0].erasure_date = rfc3339_now()
    await db.users.update(users[0])
    yield users[0]


@pytest.fixture()
async def list_of_builtin_images(db: IDatabase):
    yield await db.images.generate_builtin_test_set(TEST_SET_SIZE)


@pytest.fixture()
async def list_of_projects(db: IDatabase):
    # TODO: add this
    # yield await db.projects.generate_test_set(TEST_SET_SIZE) + [_default_project]
    yield await db.projects.generate_test_set(TEST_SET_SIZE)


@pytest.fixture()
async def list_of_fuzzers(db: IDatabase):
    yield await db.fuzzers.generate_test_set(TEST_SET_SIZE)


@pytest.fixture()
async def list_of_revisions(db: IDatabase):
    yield await db.revisions.generate_test_set(TEST_SET_SIZE)


def small_json():
    return json.dumps({"a": "b"}).encode()


def small_bytes():
    return b"A" * 100


def small_tar():

    f = BytesIO()
    with tarfile.open(fileobj=f, mode="w:gz") as tar:
        blob = b"A" * 1000
        info = tarfile.TarInfo("bin")
        info.size = len(blob)
        tar.addfile(info, BytesIO(blob))

    return f.getvalue()


def big_tar(gt: int):

    chunk_size = 4096
    chunks = gt // chunk_size

    yield small_tar()
    for _ in range(chunks + 1):
        yield b"A" * chunk_size


def unordered_unique_match(left: list, right: list):
    set_left = set(left)
    set_right = set(right)
    no_duplicates_left = len(left) == len(set_left)
    no_duplicates_right = len(right) == len(set_right)
    return set_left == set_right and no_duplicates_left and no_duplicates_right


def random_string(size=24, chars=string.ascii_lowercase):
    return "".join(random.choice(chars) for _ in range(size))


def app_url_for(name: str, **kwargs):
    return _app.url_path_for(name, **kwargs)
