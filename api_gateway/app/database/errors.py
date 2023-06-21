# TODO: hierarchy
from typing import List

from api_gateway.app.database.orm import ORMEngineID, ORMLangID


class DatabaseError(Exception):
    """Base exception for all database errors"""


class DBUserError(DatabaseError):
    pass


class DBUserNotFoundError(DBUserError):
    pass


class DBUserAlreadyExistsError(DBUserError):
    pass


class DBImageError(DatabaseError):
    pass


class DBImageNotFoundError(DBImageError):
    pass


class DBEngineNotEnabledError(DBImageError):
    pass


class DBImageAlreadyExistsError(DBImageError):
    pass


class DBEngineAlreadyEnabledError(DBImageError):
    pass


class DBEngineError(DatabaseError):
    pass


class DBEngineNotFoundError(DBEngineError):
    pass


class DBEnginesNotFoundError(DBEngineError):
    engines: List[ORMEngineID]

    def __init__(self, engines: List[ORMEngineID]):
        self.engines = engines


class DBLangNotEnabledError(DBEngineError):
    pass


class DBEngineAlreadyExistsError(DBEngineError):
    pass


class DBLangAlreadyEnabledError(DBEngineError):
    pass


class DBLangError(DatabaseError):
    pass


class DBLangNotFoundError(DBLangError):
    pass


class DBLangsNotFoundError(DBLangError):
    langs: List[ORMLangID]

    def __init__(self, langs: List[ORMLangID]):
        self.langs = langs


class DBLangAlreadyExistsError(DBLangError):
    pass


class DBCookieError(DatabaseError):
    pass


class DBCookieNotFoundError(DBCookieError):
    pass


class DBCookieAlreadyExistsError(DBCookieError):
    pass


class DBProjectError(DatabaseError):
    pass


class DBProjectNotFoundError(DBProjectError):
    pass


class DBProjectAlreadyExistsError(DBProjectError):
    pass


class DBFuzzerError(DatabaseError):
    pass


class DBFuzzerNotFoundError(DBFuzzerError):
    pass


class DBFuzzerAlreadyExistsError(DBFuzzerError):
    pass


class DBRevisionError(DatabaseError):
    pass


class DBRevisionNotFoundError(DBRevisionError):
    pass


class DBRevisionAlreadyExistsError(DBRevisionError):
    pass


class DBCrashError(DatabaseError):
    pass


class DBCrashNotFoundError(DBCrashError):
    pass


class DBCrashAlreadyExistsError(DBCrashError):
    pass


class DBIntegrationError(DatabaseError):
    pass


class DBIntegrationNotFoundError(DBIntegrationError):
    pass


class DBIntegrationAlreadyExistsError(DBIntegrationError):
    pass


class DBIntegrationTypeError(DatabaseError):
    pass


class DBIntegrationTypeNotFoundError(DBIntegrationTypeError):
    pass


class DBIntegrationTypeAlreadyExistsError(DBIntegrationTypeError):
    pass
