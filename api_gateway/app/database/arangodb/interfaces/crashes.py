from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from api_gateway.app.database.abstract import ICrashes
from api_gateway.app.database.errors import DBCrashNotFoundError
from api_gateway.app.database.orm import ORMCrash

from .base import DBBase
from .utils import dbkey_to_id, maybe_not_found, maybe_unknown_error

if TYPE_CHECKING:
    from typing import List

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBCrashes(DBBase, ICrashes):

    _col_crashes: StandardCollection

    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        self._col_crashes = db[collections.crashes]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def create(
        self,
        created: str,
        fuzzer_id: str,
        revision_id: str,
        preview: str,
        input_id: Optional[str],
        input_hash: str,
        type: str,
        brief: str,
        output: str,
        reproduced: bool,
        archived: bool,
        duplicate_count: int,
    ) -> ORMCrash:
        
        crash = ORMCrash(
            id="", # filled from meta
            created=created,
            fuzzer_id=fuzzer_id,
            revision_id=revision_id,
            preview=preview,
            input_id=input_id,
            input_hash=input_hash,
            type=type,
            brief=brief,
            output=output,
            reproduced=reproduced,
            archived=archived,
            duplicate_count=duplicate_count,
        )

        meta = await self._col_crashes.insert(crash.dict(exclude={"id"}))
        crash.id = meta["_key"]

        return crash

    @maybe_unknown_error
    async def get(
        self,
        crash_id: str,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
    ) -> ORMCrash:

        crash_dict = await self._col_crashes.get(crash_id)

        if not crash_dict:
            raise DBCrashNotFoundError()

        crash = ORMCrash(**dbkey_to_id(crash_dict))

        # revision_id is globally unique
        # Specifying both fuzzer_id and revision_id is redundant
        if fuzzer_id and revision_id:
            fuzzer_id = None

        if fuzzer_id is not None:
            if crash.fuzzer_id != fuzzer_id:
                raise DBCrashNotFoundError()

        if revision_id is not None:
            if crash.revision_id != revision_id:
                raise DBCrashNotFoundError()

        return crash

    @maybe_unknown_error
    @maybe_not_found(DBCrashNotFoundError)
    async def inc_duplicate_count(
        self,
        fuzzer_id: str,
        revision_id: str,
        input_hash: str,
    ) -> ORMCrash:

        # fmt: off
        query, variables = """
            FOR crash in @@collection
                FILTER crash.fuzzer_id == @fuzzer_id
                FILTER crash.revision_id == @revision_id
                FILTER crash.input_hash == @input_hash
                UPDATE crash WITH {
                    duplicate_count: crash.duplicate_count + 1
                } IN @@collection
                RETURN crash

        """, {
            "@collection": self._collections.crashes,
            "fuzzer_id": fuzzer_id,
            "revision_id": revision_id,
            "input_hash": input_hash,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)

        if cursor.empty():
            raise DBCrashNotFoundError()

        return ORMCrash(**dbkey_to_id(cursor.pop()))

    @maybe_unknown_error
    async def update_archived(
        self,
        crash_id: str,
        fuzzer_id: str,
        archived: bool,
    ) -> bool:
        # fmt: off
        query, variables = """
            FOR crash IN @@collection
                FILTER crash._key == @crash_id
                FILTER crash.fuzzer_id == @fuzzer_id
                UPDATE crash WITH {
                    "archived": @archived,
                } IN @@collection

                RETURN OLD.archived
        """, {
            "@collection": self._collections.crashes,
            "crash_id": crash_id,
            "fuzzer_id": fuzzer_id,
            "archived": archived,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        if cursor.empty():
            raise DBCrashNotFoundError()

        return cursor.pop()

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        date_begin: Optional[str] = None,
        date_end: Optional[str] = None,
        archived: Optional[bool] = None,
        reproduced: Optional[bool] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        # revision_id is globally unique
        # Specifying both fuzzer_id and revision_id is redundant
        if fuzzer_id and revision_id:
            fuzzer_id = None

        if fuzzer_id:
            filters.append("FILTER crash.fuzzer_id == @fuzzer_id")
            variables.update({"fuzzer_id": fuzzer_id})

        if revision_id:
            filters.append("FILTER crash.revision_id == @revision_id")
            variables.update({"revision_id": revision_id})

        if date_begin:
            filters.append("FILTER crash.created >= DATE_TRUNC(@date_begin, 'day')")
            variables.update({"date_begin": date_begin})

        if date_end:
            filters.append(
                "FILTER crash.created < DATE_ADD(DATE_TRUNC(@date_end, 'day'), 1, 'day')"
            )
            variables.update({"date_end": date_end})

        if archived is not None:
            filters.append("FILTER crash.archived == @archived")
            variables["archived"] = archived

        if reproduced is not None:
            filters.append("FILTER crash.reproduced == @reproduced")
            variables["reproduced"] = reproduced

        if filters:
            query = query.replace("<filter-options>", "\n\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    @maybe_unknown_error
    async def list(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        date_begin: Optional[str] = None,
        date_end: Optional[str] = None,
        archived: Optional[bool] = None,
        reproduced: Optional[bool] = None,
    ) -> List[ORMCrash]:

        assert fuzzer_id or revision_id

        # fmt: off
        query, variables = """
            FOR crash in @@collection
                <filter-options>
                SORT crash.created DESC
                LIMIT @offset, @limit
                RETURN MERGE(crash, {
                    "id": crash._key,
                })
        """, {
            "@collection": self._collections.crashes,
            "offset": paginator.offset,
            "limit": paginator.limit,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query,
            variables,
            fuzzer_id=fuzzer_id,
            revision_id=revision_id,
            date_begin=date_begin,
            date_end=date_end,
            archived=archived,
            reproduced=reproduced,
        )

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMCrash(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def count(
        self,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        date_begin: Optional[str] = None,
        date_end: Optional[str] = None,
        archived: Optional[bool] = None,
        reproduced: Optional[bool] = None,
    ) -> int:

        assert fuzzer_id or revision_id

        # fmt: off
        query, variables = """
            FOR crash IN @@collection
                <filter-options>
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._col_crashes.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query,
            variables,
            fuzzer_id=fuzzer_id,
            revision_id=revision_id,
            date_begin=date_begin,
            date_end=date_end,
            archived=archived,
            reproduced=reproduced,
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()
