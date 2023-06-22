from contextlib import suppress
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import AnyHttpUrl, AnyUrl, BaseModel
from pydantic import BaseSettings as _BaseSettings
from pydantic import EmailStr, Field, root_validator

# fmt: off
with suppress(ModuleNotFoundError):
    import dotenv; dotenv.load_dotenv()
# fmt: on


class PlatformType(str, Enum):
    cloud = "cloud"
    onprem = "onprem"
    demo = "demo"


class BaseSettings(_BaseSettings):
    @root_validator
    def check_empty_strings(cls, data: Dict[str, Any]):
        for name, value in data.items():
            if isinstance(value, str):
                if len(value) == 0:
                    var = f"{cls.__name__}.{name}"
                    raise ValueError(f"Variable '{var}': empty string not allowed")

        return data


class EnvironmentSettings(BaseSettings):
    name: str = Field(env="ENVIRONMENT", regex=r"^(dev|prod|test)$")
    platform_type: PlatformType = Field(env="PLATFORM_TYPE")
    shutdown_timeout: int = Field(env="SHUTDOWN_TIMEOUT")
    service_name: Optional[str] = Field(env="SERVICE_NAME")
    service_version: Optional[str] = Field(env="SERVICE_VERSION")
    commit_id: Optional[str] = Field(env="COMMIT_ID")
    build_date: Optional[str] = Field(env="BUILD_DATE")
    commit_date: Optional[str] = Field(env="COMMIT_DATE")
    git_branch: Optional[str] = Field(env="GIT_BRANCH")

    @root_validator(skip_on_failure=True)
    def check_values_for_production(cls, data: Dict[str, Any]):

        if data["name"] != "prod":
            return data

        vars = []
        for name, value in data.items():
            if value is None:
                vars.append(name.upper())

        if vars:
            raise ValueError(f"Variables must be set in production mode: {vars}")

        return data


class DatabaseSettings(BaseSettings):

    engine: str = Field(regex=r"^arangodb$")
    url: AnyHttpUrl
    username: str
    password: str
    name: str

    class Config:
        env_prefix = "DB_"


class S3Buckets(BaseSettings):
    fuzzers: str
    data: str

    class Config:
        env_prefix = "S3_BUCKET_"


class ObjectStorageSettings(BaseSettings):

    url: AnyHttpUrl
    buckets: S3Buckets
    access_key: str
    secret_key: str

    class Config:
        env_prefix = "S3_"


class StatisticsCollections(BaseSettings):
    libfuzzer = "StatisticsLibFuzzer"
    afl = "StatisticsAFL"
    crashes = "StatisticsCrashes"


class CollectionSettings(BaseSettings):
    users = "Users"
    cookies = "Cookies"
    lockout = "UserLockout"
    projects = "Projects"
    fuzzers = "Fuzzers"
    revisions = "Revisions"
    images = "Images"
    engines = "Engines"
    langs = "Langs"
    statistics = StatisticsCollections()
    crashes = "Crashes"
    integrations = "Integrations"
    integration_types = "IntegrationTypes"
    unsent_messages = "UnsentMessages"


class MessageQueues(BaseSettings):
    jira_reporter: str
    youtrack_reporter: str
    crash_analyzer: str
    api_gateway: str
    scheduler: str
    dlq: str

    class Config:
        env_prefix = "MQ_QUEUE_"


class MessageQueueSettings(BaseSettings):

    queues: MessageQueues
    broker: str = Field(regex="^sqs$")
    url: AnyUrl
    region: str
    username: str
    password: str

    class Config:
        env_prefix = "MQ_"


class CookieSettings(BaseSettings):
    expiration_seconds: int = Field(gt=0)
    mode_secure: bool

    class Config:
        env_prefix = "COOKIE_"


class TrashBinSettings(BaseSettings):
    expiration_seconds: int = Field(gt=0, env="TRASHBIN_EXPIRATION_SECONDS")


class SystemAdminSettings(BaseSettings):
    username: str
    password: str
    email: EmailStr

    class Config:
        env_prefix = "SYSTEM_ADMIN_"


class DefaultUserSettings(BaseSettings):
    username: str
    password: str
    email: EmailStr

    class Config:
        env_prefix = "DEFAULT_ACCOUNT_"


class BruteforceProtectionSettings(BaseSettings):

    lockout_period_sec: int
    """ T - Time period for lockout duration/attempt counting """

    max_failed_logins: int
    """ N – Max number of failed authentication attempts allowed during T """

    cleanup_interval_sec: int = Field(gt=0)
    """ Time interval at which user lockout list cleanup is made """

    secret_key: str
    """ Secret key for encoding and decoding JWT tokens """

    class Config:
        env_prefix = "BFP_"


class CSRFProtectionSettings(BaseSettings):

    enabled: bool
    """ Whether CSRF protection is enabled or not """

    token_exp_seconds: int = Field(gt=0)
    """ CSRF token expiration time interval """

    secret_key: str
    """ Secret key for encoding and decoding JWT tokens """

    class Config:
        env_prefix = "CSRF_PROTECTION_"


class FuzzerSettings(BaseSettings):
    min_cpu_usage: int = Field(gt=0)
    min_ram_usage: int = Field(gt=0)
    min_tmpfs_size: int = Field(gt=0)

    class Config:
        env_prefix = "FUZZER_"


class RevisionSettings(BaseSettings):
    binaries_upload_limit: int = Field(gt=0)
    seeds_upload_limit: int = Field(gt=0)
    config_upload_limit: int = Field(gt=0)

    class Config:
        env_prefix = "REVISION_"


class APIEndpointSettings(BaseSettings):
    jira_reporter: AnyHttpUrl
    youtrack_reporter: AnyHttpUrl
    pool_manager: AnyHttpUrl
    public: AnyHttpUrl

    class Config:
        env_prefix = "API_URL_"


class APISettings(BaseSettings):
    client_module: str = Field(regex=r"^aiohttp$")
    endpoints: APIEndpointSettings

    class Config:
        env_prefix = "API_"


class AppSettings(BaseModel):
    api: APISettings
    environment: EnvironmentSettings
    object_storage: ObjectStorageSettings
    message_queue: MessageQueueSettings
    bfp: BruteforceProtectionSettings
    csrf_protection: CSRFProtectionSettings
    collections: CollectionSettings
    database: DatabaseSettings
    trashbin: TrashBinSettings
    default_user: DefaultUserSettings
    revision: RevisionSettings
    root: SystemAdminSettings
    cookies: CookieSettings
    fuzzer: FuzzerSettings


_app_settings = None


def get_app_settings() -> AppSettings:

    global _app_settings

    if _app_settings is None:
        _app_settings = AppSettings(
            database=DatabaseSettings(),
            collections=CollectionSettings(),
            object_storage=ObjectStorageSettings(buckets=S3Buckets()),
            message_queue=MessageQueueSettings(queues=MessageQueues()),
            api=APISettings(endpoints=APIEndpointSettings()),
            csrf_protection=CSRFProtectionSettings(),
            bfp=BruteforceProtectionSettings(),
            environment=EnvironmentSettings(),
            trashbin=TrashBinSettings(),
            default_user=DefaultUserSettings(),
            revision=RevisionSettings(),
            root=SystemAdminSettings(),
            cookies=CookieSettings(),
            fuzzer=FuzzerSettings(),
        )

    return _app_settings
