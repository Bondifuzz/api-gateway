import logging

from api_gateway.app.settings import AppSettings

from .abstract import IDatabase
from .arangodb.database import ArangoDB


async def db_init(settings: AppSettings) -> IDatabase:

    logger = logging.getLogger("db")
    db_engine = settings.database.engine.lower()

    if db_engine == "arangodb":
        logger.info("Using ArangoDB driver")
        db = await ArangoDB.create(settings)
    # elif db_engine == "mongodb":
    #     logger.info("Using MongoDB driver")
    #     db = await MongoDB.create(settings)
    else:
        raise ValueError(f"Invalid database engine '{db_engine}'")

    return db
