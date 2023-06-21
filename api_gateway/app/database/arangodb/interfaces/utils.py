import functools
from typing import Type

from aioarangodb.errno import DOCUMENT_NOT_FOUND, UNIQUE_CONSTRAINT_VIOLATED, CONFLICT
from aioarangodb.exceptions import (
    ArangoError,
    CursorEmptyError,
    DocumentDeleteError,
    ArangoServerError,
)
from aiohttp.client_exceptions import ClientConnectionError

from api_gateway.app.database.errors import DatabaseError
from api_gateway.app.settings import CollectionSettings


def dbkey_to_id(data: dict):
    data["id"] = data["_key"]
    del data["_key"]
    del data["_id"]
    del data["_rev"]
    return data


def id_to_dbkey(data: dict):
    data["_key"] = data["id"]
    del data["id"]
    return data


def maybe_unknown_error(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            res = await func(*args, **kwargs)
        except (ArangoError, ClientConnectionError) as e:
            raise DatabaseError(e) from e

        return res

    return wrapper


def retry_on_write_conflict(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        for _ in range(5):
            try:
                res = await func(*args, **kwargs)
                return res
            
            except ArangoServerError as e:
                if e.error_code != CONFLICT:
                    raise DatabaseError(e) from e
        
        raise DatabaseError("Failed to do operation after 5 conflicts")

    return wrapper


def maybe_not_found(ExceptionRaised: Type[DatabaseError]):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            try:
                res = await func(*args, **kwargs)
            except CursorEmptyError as e:
                raise ExceptionRaised() from e
            except DocumentDeleteError as e:
                if e.error_code == DOCUMENT_NOT_FOUND:
                    raise ExceptionRaised() from e
                raise

            return res

        return wrapped

    return wrapper


def maybe_not_found_none(ExceptionRaised: Type[DatabaseError]):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            res = await func(*args, **kwargs)
            if not res:
                raise ExceptionRaised()

            return res

        return wrapped

    return wrapper


def maybe_already_exists(ExceptionRaised: Type[DatabaseError]):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            try:
                res = await func(*args, **kwargs)
            except ArangoServerError as e:
                if e.error_code == UNIQUE_CONSTRAINT_VIOLATED:
                    raise ExceptionRaised() from e
                raise
            return res

        return wrapped

    return wrapper


def aql_delete_fuzzer_data(fuzzer_id: str, collections: CollectionSettings):

    # fmt: off
    query, variables = """
        FOR revision in @@col_revisions
            FILTER revision.fuzzer_id == @fuzzer_id
            REMOVE revision IN @@col_revisions
    """, {
        "@col_fuzzers": collections.fuzzers,
        "@col_revisions": collections.revisions,
        "fuzzer_id": fuzzer_id,
    }
    # fmt: on

    return query, variables


def aql_delete_project_data(project_id: str, collections: CollectionSettings):

    # fmt: off
    query, variables = """
        FOR fuzzer in @@col_fuzzers
            FILTER fuzzer.project_id == @project_id
            FOR revision in @@col_revisions
                FILTER revision.fuzzer_id == fuzzer._key
                REMOVE revision IN @@col_revisions
            REMOVE fuzzer IN @@col_fuzzers
    """, {
        "@col_fuzzers": collections.fuzzers,
        "@col_revisions": collections.revisions,
        "project_id": project_id,
    }
    # fmt: on

    return query, variables


def aql_delete_user_data(user_id: str, collections: CollectionSettings):

    # fmt: off
    query, variables = """
        FOR cookie in @@col_cookies
            FILTER cookie.user_id == @user_id
            REMOVE cookie IN @@col_cookies
        FOR project in @@col_projects
            FILTER project.owner_id == @user_id
            FOR fuzzer in @@col_fuzzers
                FILTER fuzzer.project_id == project._key
                FOR revision in @@col_revisions
                    FILTER revision.fuzzer_id == fuzzer._key
                    REMOVE revision IN @@col_revisions
                REMOVE fuzzer IN @@col_fuzzers
            REMOVE project IN @@col_projects
    """, {
        "@col_cookies": collections.cookies,
        "@col_projects": collections.projects,
        "@col_fuzzers": collections.fuzzers,
        "@col_revisions": collections.revisions,
        "user_id": user_id,
    }
    # fmt: on

    return query, variables
