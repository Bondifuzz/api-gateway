from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import ILangs
from api_gateway.app.database.errors import (
    DBLangNotFoundError,
    DBLangAlreadyExistsError,
)
from api_gateway.app.database.orm import (
    ORMLangID,
    ORMLang,
    Paginator,
)

from .base import DBBase
from .utils import id_to_dbkey, dbkey_to_id, maybe_already_exists, maybe_unknown_error, maybe_not_found

if TYPE_CHECKING:
    from typing import List, Optional

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.settings import CollectionSettings


class DBLangs(DBBase, ILangs):

    _col_langs: StandardCollection
    _col_engines: StandardCollection

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_langs = db[collections.langs]
        self._col_engines = db[collections.engines]
        super().__init__(db, collections)

    @maybe_unknown_error
    @maybe_not_found(DBLangNotFoundError)
    async def get_by_id(self, lang_id: ORMLangID) -> ORMLang:

        lang_dict: Optional[dict] = await self._col_langs.get(lang_id)
        if lang_dict is None:
            raise DBLangNotFoundError()
        
        return ORMLang(**dbkey_to_id(lang_dict))

    @maybe_unknown_error
    async def list(
        self,
        paginator: Optional[Paginator] = None,
    ) -> List[ORMLang]:

        cursor: Cursor = await self._col_langs.all(
            skip=paginator.offset if paginator else None,
            limit=paginator.limit if paginator else None,
        )

        return [ORMLang(**dbkey_to_id(doc)) async for doc in cursor]

    @maybe_unknown_error
    async def count(self) -> int:
        return await self._col_langs.count()

    @maybe_unknown_error
    @maybe_already_exists(DBLangAlreadyExistsError)
    async def create(
        self,
        id: ORMLangID,
        display_name: str,
    ) -> ORMLang:

        lang = ORMLang(
            id=id,
            display_name=display_name,
        )

        await self._col_langs.insert(
            id_to_dbkey(lang.dict()),
            silent=True,
        )

        return lang

    @maybe_unknown_error
    @maybe_not_found(DBLangNotFoundError)
    async def update(self, lang: ORMLang):
        lang_dict = id_to_dbkey(lang.dict())
        await self._col_langs.replace(lang_dict, silent=True)

    @maybe_unknown_error
    async def delete(self, lang: ORMLang):
        await self._col_langs.delete(lang.id, silent=True, ignore_missing=True)
        # fmt: off
        query, variables = """
            FOR engine IN @@col_engines
                FILTER @lang_id IN engine.langs
                UPDATE engine WITH {
                    langs: REMOVE_VALUE(engine.langs, @lang_id)
                } IN @@col_engines
        """, {
            "@col_engines": self._collections.engines,
            "lang_id": lang.id,
        }
        # fmt: on
        await self._db.aql.execute(query, bind_vars=variables)

