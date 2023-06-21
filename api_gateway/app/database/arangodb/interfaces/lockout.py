from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IUserLockout
from api_gateway.app.database.orm import ORMDeviceCookie

from .base import DBBase
from .utils import maybe_unknown_error

if TYPE_CHECKING:
    pass

    from aioarangodb.collection import StandardCollection
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.settings import CollectionSettings


class DBUserLockout(DBBase, IUserLockout):

    _col_lockout: StandardCollection

    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        self._col_lockout = db[collections.lockout]
        super().__init__(db, collections)

    @staticmethod
    def _make_key(dc: ORMDeviceCookie):
        return f"{dc.username}:{dc.nonce}"

    @maybe_unknown_error
    async def add(self, device_cookie: ORMDeviceCookie, exp_seconds: str):

        # fmt: off
        query, variables = """
            INSERT {
                _key: @key,
                exp_date: DATE_ISO8601(
                    DATE_ADD(DATE_NOW(), @exp_seconds, "s")
                )
            } INTO @@collection
            RETURN NEW
        """, {
            "@collection": self._col_lockout.name,
            "key": self._make_key(device_cookie),
            "exp_seconds": exp_seconds,
        }
        # fmt: on

        await self._db.aql.execute(query, bind_vars=variables)

    @maybe_unknown_error
    async def has(self, device_cookie: ORMDeviceCookie):
        key = self._make_key(device_cookie)
        return await self._col_lockout.has(key)

    @maybe_unknown_error
    async def remove_expired(self):

        # fmt: off
        query, variables  ="""
            FOR lockout in @@collection
                FILTER DATE_ISO8601(DATE_NOW()) > lockout.exp_date
                REMOVE lockout IN @@collection
        """, {
            "@collection": self._col_lockout.name
        }
        # fmt: on

        await self._db.aql.execute(query, bind_vars=variables)
