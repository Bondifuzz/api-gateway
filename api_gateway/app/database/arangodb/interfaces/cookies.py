from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import ICookies
from api_gateway.app.database.errors import DBCookieNotFoundError
from api_gateway.app.database.orm import ORMCookie

from .base import DBBase
from .utils import dbkey_to_id, maybe_unknown_error

if TYPE_CHECKING:
    from typing import List, Optional

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBCookies(DBBase, ICookies):

    _col_cookies: StandardCollection

    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        self._col_cookies = db[collections.cookies]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def create(
        self,
        user_id: str,
        metadata: str,
        expiration_seconds: int,
    ) -> ORMCookie:

        # fmt: off
        query, variables = """
            INSERT {
                user_id: @user_id,
                metadata: @metadata,
                expires: DATE_ISO8601(
                    DATE_ADD(DATE_NOW(), @expiration_seconds, "s")
                )
            } INTO @@collection
            RETURN NEW
        """, {
            "@collection": self._collections.cookies,
            "expiration_seconds": expiration_seconds,
            "metadata": metadata,
            "user_id": user_id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return ORMCookie(**dbkey_to_id(cursor.pop()))

    @maybe_unknown_error
    async def get(self, cookie_id: str, user_id: Optional[str] = None) -> ORMCookie:

        cookie_dict = await self._col_cookies.get(cookie_id)

        if not cookie_dict:
            raise DBCookieNotFoundError()

        cookie = ORMCookie(**dbkey_to_id(cookie_dict))

        if user_id is not None:
            if user_id != cookie.user_id:
                raise DBCookieNotFoundError()

        return cookie

    @maybe_unknown_error
    async def delete(self, cookie: ORMCookie):
        await self._col_cookies.delete(cookie.id, silent=True)

    @maybe_unknown_error
    async def delete_many(self, user_id: str):

        # fmt: off
        query, variables = """
            FOR cookie in @@collection
                FILTER cookie.user_id == @user_id
                REMOVE cookie IN @@col_cookies
        """, {
            "@collection": self._collections.cookies,
            "user_id": user_id,
        }
        # fmt: on

        await self._db.aql.execute(query, bind_vars=variables)

    @maybe_unknown_error
    async def list(self, paginator: Paginator, user_id=None) -> List[ORMCookie]:

        # fmt: off
        query, variables = """
            FOR cookie in @@collection
                <filter-user-cookie>
                SORT cookie.metadata
                LIMIT @offset, @limit
                RETURN MERGE(cookie, {
                    "id": cookie._key,
                })
        """, {
            "@collection": self._collections.cookies,
            "offset": paginator.offset,
            "limit": paginator.limit,
        }
        # fmt: on

        if user_id:
            variables.update({"user_id": user_id})
            filter_query = "FILTER cookie.user_id == @user_id"
            query = query.replace("<filter-user-cookie>", filter_query)
        else:
            query = query.replace("<filter-user-cookie>", "")

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMCookie(**doc) async for doc in cursor]
