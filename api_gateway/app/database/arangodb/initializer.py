import logging
from typing import List

from aioarangodb import ArangoClient
from aioarangodb.database import StandardDatabase
from aioarangodb.exceptions import IndexCreateError
from aioarangodb.job import BatchJob

from api_gateway.app.settings import AppSettings, CollectionSettings

from ..errors import DatabaseError

########################################
# ArangoDB Base Initializer
########################################


class ArangoDBBaseInitializer:

    _client: ArangoClient
    _db: StandardDatabase

    @staticmethod
    def get_logger():
        return logging.getLogger("db.init")

    async def _verify_auth(self):

        logger = self.get_logger()
        logger.info("Signing in as user '%s'", self._db.username)
        logger.info("Using database '%s'", self._db.name)

        try:
            await self._db.conn.ping()
        except Exception as e:
            msg = f"Failed to open database '{self._db.name}'. Reason - {e}"
            raise DatabaseError(msg) from e

    async def _check_user_permissions(self):

        permissions = await self._db.permission(self._db.username, self._db.name)

        if permissions != "rw":
            msg = f"Not enough permissions to administrate database: '{permissions}'"
            raise DatabaseError(msg)

    async def _create_collections(self, collections):

        logger = self.get_logger()
        batch_db = self._db.begin_batch_execution(return_result=False)
        existent_cols = [col["name"] for col in await self._db.collections()]

        for collection in collections:
            col_name = collection["name"]
            if col_name not in existent_cols:
                await batch_db.create_collection(**collection)
                logger.info("Collection '%s' does not exist. Creating...", col_name)
            else:
                logger.info("Collection '%s' already exists", col_name)

        await batch_db.commit()

    def get_init_tasks(self):
        yield "Authentication", self._verify_auth()
        yield "Check permissions", self._check_user_permissions()

    async def _init(self, settings: AppSettings):

        db_name = settings.database.name
        username = settings.database.username
        password = settings.database.password

        self._client = ArangoClient(settings.database.url)
        self._db = await self._client.db(db_name, username, password)

    @staticmethod
    async def create(settings):
        self = ArangoDBBaseInitializer()
        await self._init(settings)
        return self

    async def do_init(self):

        logger = self.get_logger()

        try:
            logger.info("Initializing database...")
            for name, task in self.get_init_tasks():
                logger.info("Performing '%s'", name)
                await task

            logger.info("Initializing database... OK")

        except:
            await self._client.close()
            raise

    @property
    def db(self):
        return self._db

    @property
    def client(self):
        return self._client


########################################
# ArangoDB Initializer
########################################


class ArangoDBInitializer(ArangoDBBaseInitializer):

    _collections: CollectionSettings

    async def _init(self, settings: AppSettings):
        await super()._init(settings)
        self._collections = settings.collections

    @staticmethod
    async def create(settings):
        self = ArangoDBInitializer()
        await self._init(settings)
        return self

    async def _create_all_collections(self):
        await self._create_collections(
            [
                {"name": self._collections.users},
                {"name": self._collections.cookies, "key_generator": "uuid"},
                {"name": self._collections.lockout},
                {"name": self._collections.projects},
                {"name": self._collections.fuzzers},
                {"name": self._collections.revisions},
                {"name": self._collections.images},
                {"name": self._collections.engines},
                {"name": self._collections.langs},
                {"name": self._collections.statistics.afl},
                {"name": self._collections.statistics.libfuzzer},
                {"name": self._collections.statistics.crashes},
                {"name": self._collections.crashes},
                {"name": self._collections.unsent_messages},
                {"name": self._collections.integrations},
                {"name": self._collections.integration_types},
            ]
        )

    async def _add_indexes(self):

        logger = self.get_logger()
        batch_db = self._db.begin_batch_execution()

        #
        # Create only lightweight indexes here
        # Heavyweight indexes will be created by administrator
        #

        await batch_db[self._collections.cookies].add_ttl_index(
            fields=["expires"], name="expire_cookies", expiry_time=0
        )

        # await batch_db[self._collections.cookies].add_hash_index(
        #     fields=["user_id"], name="list_user_cookies", unique=False
        # )

        # await batch_db[self._collections.images].add_hash_index(
        #     fields=["project_id"], name="find_image_project", unique=False
        # )

        jobs: List[BatchJob] = await batch_db.commit()

        try:
            for job in jobs:
                index = job.result()
                if index["new"]:
                    logger.info("Index '%s' created", index["name"])
                else:
                    logger.info("Index '%s' already exists", index["name"])

        except IndexCreateError as e:
            logger.warning("Failed to create indexes. Reason - %s", e)

    def get_init_tasks(self):
        yield from super().get_init_tasks()
        yield "Create collections", self._create_all_collections()
        yield "Add collection indexes", self._add_indexes()

    @property
    def collections(self):
        return self._collections
