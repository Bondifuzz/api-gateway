from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from aioarangodb.client import ArangoClient
from aioarangodb.database import StandardDatabase

from api_gateway.app.database.arangodb.interfaces.integrations import DBIntegrations
from api_gateway.app.database.arangodb.interfaces.lockout import DBUserLockout
from api_gateway.app.database.arangodb.interfaces.statistics.crashes import (
    DBStatisticsCrashes,
)
from api_gateway.app.database.errors import DBUserAlreadyExistsError
from api_gateway.app.utils import testing_only

from ..abstract import (
    ICookies,
    ICrashes,
    IDatabase,
    IEngines,
    IFuzzers,
    IImages,
    IIntegrations,
    IIntegrationTypes,
    ILangs,
    IProjects,
    IRevisions,
    IStatistics,
    IStatisticsAFL,
    IStatisticsCrashes,
    IStatisticsLibFuzzer,
    IUnsentMessages,
    IUsers,
)
from .initializer import ArangoDBInitializer
from .interfaces.cookies import DBCookies
from .interfaces.crashes import DBCrashes
from .interfaces.engines import DBEngines
from .interfaces.fuzzers import DBFuzzers
from .interfaces.images import DBImages
from .interfaces.integration_types import DBIntegrationTypes
from .interfaces.langs import DBLangs
from .interfaces.projects import DBProjects
from .interfaces.revisions import DBRevisions
from .interfaces.statistics.afl import DBStatisticsAFL
from .interfaces.statistics.libfuzzer import DBStatisticsLibFuzzer
from .interfaces.unsent_mq import DBUnsentMessages
from .interfaces.users import DBUsers

if TYPE_CHECKING:
    from api_gateway.app.settings import AppSettings, CollectionSettings


class DBStatistics(IStatistics):

    _crashes: DBStatisticsCrashes
    _libfuzzer: DBStatisticsLibFuzzer
    _afl: DBStatisticsAFL

    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        self._crashes = DBStatisticsCrashes(db, collections)
        self._libfuzzer = DBStatisticsLibFuzzer(db, collections)
        self._afl = DBStatisticsAFL(db, collections)

    @property
    def crashes(self) -> IStatisticsCrashes:
        return self._crashes

    @property
    def libfuzzer(self) -> IStatisticsLibFuzzer:
        return self._libfuzzer

    @property
    def afl(self) -> IStatisticsAFL:
        return self._afl


class ArangoDB(IDatabase):

    _db_users: IUsers
    _db_cookies: ICookies
    _db_projects: IProjects
    _db_fuzzers: IFuzzers
    _db_revisions: IRevisions
    _db_images: IImages
    _db_engines: IEngines
    _db_langs: ILangs
    _db_statistics: IStatistics
    _db_crashes: ICrashes
    _db_unsent_mq: IUnsentMessages
    _db_integrations: IIntegrations
    _db_integration_types: IIntegrationTypes

    _logger: logging.Logger
    _collections: CollectionSettings
    _client: Optional[ArangoClient]
    _db: StandardDatabase
    _is_closed: bool

    @property
    def unsent_mq(self):
        return self._db_unsent_mq

    @property
    def users(self):
        return self._db_users

    @property
    def lockout(self):
        return self._db_lockout

    @property
    def cookies(self):
        return self._db_cookies

    @property
    def projects(self):
        return self._db_projects

    @property
    def fuzzers(self):
        return self._db_fuzzers

    @property
    def revisions(self):
        return self._db_revisions

    @property
    def images(self):
        return self._db_images

    @property
    def engines(self):
        return self._db_engines

    @property
    def langs(self):
        return self._db_langs

    @property
    def statistics(self):
        return self._db_statistics

    @property
    def crashes(self):
        return self._db_crashes

    @property
    def integrations(self):
        return self._db_integrations

    @property
    def integration_types(self):
        return self._db_integration_types

    async def _init(self, settings: AppSettings):

        self._client = None
        self._is_closed = True
        self._logger = logging.getLogger("db")

        db_initializer = await ArangoDBInitializer.create(settings)
        await db_initializer.do_init()

        db = db_initializer.db
        client = db_initializer.client
        collections = db_initializer.collections

        db_users = DBUsers(db, collections)
        db_lockout = DBUserLockout(db, collections)
        db_cookies = DBCookies(db, collections)
        db_projects = DBProjects(db, collections)
        db_fuzzers = DBFuzzers(db, collections)
        db_revisions = DBRevisions(db, collections)
        db_images = DBImages(db, collections)
        db_engines = DBEngines(db, collections)
        db_langs = DBLangs(db, collections)
        db_statistics = DBStatistics(db, collections)
        db_crashes = DBCrashes(db, collections)
        db_unsent_mq = DBUnsentMessages(db, collections)
        db_integrations = DBIntegrations(db, collections)
        db_integration_types = DBIntegrationTypes(db, collections)

        try:
            await db_users.create_system_admin(settings.root)
        except DBUserAlreadyExistsError:
            self._logger.info("System administrator already exists")
        else:
            self._logger.info("System administrator created")

        try:
            await db_users.create_default_user(settings.default_user)

        except DBUserAlreadyExistsError:
            self._logger.info("Default user already exists")
        else:
            self._logger.info("Default user created")

        self._db_users = db_users
        self._db_lockout = db_lockout
        self._db_cookies = db_cookies
        self._db_projects = db_projects
        self._db_fuzzers = db_fuzzers
        self._db_revisions = db_revisions
        self._db_unsent_mq = db_unsent_mq
        self._db_integrations = db_integrations
        self._db_integration_types = db_integration_types
        self._db_images = db_images
        self._db_engines = db_engines
        self._db_langs = db_langs
        self._db_statistics = db_statistics
        self._db_crashes = db_crashes

        self._is_closed = False
        self._collections = collections
        self._client = client
        self._db = db

    @staticmethod
    async def create(settings):
        _self = ArangoDB()
        await _self._init(settings)
        return _self

    @testing_only
    async def truncate_all_collections(self):
        self._logger.warning("Clearing all collections...")
        async with self._db.begin_batch_execution(return_result=False) as db:
            for col_name in [col["name"] for col in await self._db.collections()]:
                await db.collection(col_name).truncate()

    async def close(self):

        assert not self._is_closed, "Database connection has been already closed"

        if self._client:
            await self._client.close()
            self._client = None

        self._is_closed = True

    def __del__(self):
        if not self._is_closed:
            self._logger.error("Database connection has not been closed")
