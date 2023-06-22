from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IEngines
from api_gateway.app.database.errors import (
    DBEngineAlreadyExistsError,
    DBEngineNotFoundError,
    DBLangAlreadyEnabledError,
    DBLangNotEnabledError,
    DBLangNotFoundError,
    DBLangsNotFoundError,
)
from api_gateway.app.database.orm import ORMEngine, ORMEngineID, ORMLangID, Paginator

from .base import DBBase
from .utils import (
    dbkey_to_id,
    id_to_dbkey,
    maybe_already_exists,
    maybe_not_found,
    maybe_unknown_error,
)

if TYPE_CHECKING:
    from typing import List, Optional

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.settings import CollectionSettings


class DBEngines(DBBase, IEngines):
    _col_images: StandardCollection
    _col_engines: StandardCollection
    _col_langs: StandardCollection

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_images = db[collections.images]
        self._col_engines = db[collections.engines]
        self._col_langs = db[collections.langs]
        super().__init__(db, collections)

    @maybe_unknown_error
    @maybe_not_found(DBEngineNotFoundError)
    async def get_by_id(self, engine_id: ORMEngineID) -> ORMEngine:
        doc_dict = await self._col_engines.get(engine_id)
        if doc_dict is None:
            raise DBEngineNotFoundError()

        return ORMEngine(**dbkey_to_id(doc_dict))

    @maybe_unknown_error
    async def list(
        self,
        paginator: Optional[Paginator] = None,
        lang_id: Optional[ORMLangID] = None,
    ) -> List[ORMEngine]:
        # fmt: off
        query, variables = """
            FOR engine in @@col_engines
                // no filter or if lang present for engine
                FILTER @lang_id == null OR @lang_id IN engine.langs

                <limit>
                RETURN MERGE(engine, {
                    "id": engine._key,
                })
        """, {
            "@col_engines": self._collections.engines,
            "lang_id": lang_id,
        }
        # fmt: on

        if paginator:
            query = query.replace("<limit>", "LIMIT @offset, @limit")
            variables["offset"] = paginator.offset
            variables["limit"] = paginator.limit
        else:
            query = query.replace("<limit>", "")

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMEngine(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def count(
        self,
        lang_id: Optional[ORMLangID] = None,
    ) -> int:
        # fmt: off
        query, variables = """
            FOR engine IN @@col_engines
                FILTER @lang_id == null OR @lang_id in engine.langs
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@col_engines": self._collections.engines,
            "lang_id": lang_id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    async def _get_unknown_langs(self, lang_ids: List[ORMLangID]) -> List[ORMLangID]:
        # fmt: off
        query, variables = """
            FOR lang IN @@col_langs
                FILTER lang._key IN @lang_ids
                RETURN lang._key
        """, {
            "@col_langs": self._collections.langs,
            "lang_ids": lang_ids,
        }
        # fmt: on
        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        known_lang_ids = [ORMLangID(doc) async for doc in cursor]
        unknown_lang_ids = set(lang_ids) - set(known_lang_ids)
        return list(unknown_lang_ids)

    @maybe_unknown_error
    @maybe_already_exists(DBEngineAlreadyExistsError)
    async def create(
        self,
        id: ORMEngineID,
        display_name: str,
        lang_ids: List[ORMLangID],
    ) -> ORMEngine:
        engine = ORMEngine(
            id=id,
            display_name=display_name,
            langs=lang_ids,
        )

        unknown_langs = await self._get_unknown_langs(lang_ids)
        if len(unknown_langs) > 0:
            raise DBLangsNotFoundError(langs=unknown_langs)

        await self._col_engines.insert(
            id_to_dbkey(engine.dict()),
            silent=True,
        )

        return engine

    @maybe_unknown_error
    @maybe_not_found(DBEngineNotFoundError)
    async def update(self, engine: ORMEngine):
        engine_dict = id_to_dbkey(engine.dict())
        await self._col_engines.replace(engine_dict, silent=True)

    @maybe_unknown_error
    async def delete(self, engine: ORMEngine):
        await self._col_engines.delete(engine.id, silent=True, ignore_missing=True)
        # fmt: off
        query, variables = """
            FOR image IN @@col_images
                FILTER @engine_id IN image.engines
                UPDATE image WITH {
                    engines: REMOVE_VALUE(image.engines, @engine_id)
                } IN @@col_images
        """, {
            "@col_images": self._collections.images,
            "engine_id": engine.id,
        }
        # fmt: on
        await self._db.aql.execute(query, bind_vars=variables)

    @maybe_unknown_error
    @maybe_not_found(DBEngineNotFoundError)  # current engine deleted
    async def enable_lang(self, engine: ORMEngine, lang_id: ORMLangID):

        if lang_id in engine.langs:
            raise DBLangAlreadyEnabledError()

        # fmt: off
        query, variables = """
            FOR lang IN @@col_langs
                FILTER lang._key == @lang_id

                UPDATE @engine_id WITH {
                    langs: PUSH(@current_lang_ids, @lang_id, true)
                } IN @@col_engines
                RETURN true
        """, {
            "@col_langs": self._collections.langs,
            "@col_engines": self._collections.engines,
            "lang_id": lang_id,
            "current_lang_ids": engine.langs,
            "engine_id": engine.id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        if cursor.empty():
            raise DBLangNotFoundError()

        engine.langs.append(lang_id)

    @maybe_unknown_error
    @maybe_not_found(DBEngineNotFoundError)  # current engine deleted
    async def disable_lang(self, engine: ORMEngine, lang_id: ORMLangID):

        if lang_id not in engine.langs:
            raise DBLangNotEnabledError()

        new_langs = list(engine.langs)
        new_langs.remove(lang_id)

        await self._col_engines.update(
            {
                "_key": engine.id,
                "langs": new_langs,
            }
        )

        engine.langs = new_langs

    @maybe_unknown_error
    @maybe_not_found(DBEngineNotFoundError)  # current engine deleted
    async def set_langs(self, engine: ORMEngine, lang_ids: List[ORMLangID]):

        unknown_langs = await self._get_unknown_langs(lang_ids)
        if len(unknown_langs) > 0:
            raise DBLangsNotFoundError(langs=unknown_langs)

        await self._col_engines.update(
            {
                "_key": engine.id,
                "langs": lang_ids,
            }
        )

        engine.langs = lang_ids
