from __future__ import annotations

from typing import TYPE_CHECKING, Set, Tuple

from api_gateway.app.database.abstract import IFuzzers
from api_gateway.app.database.errors import (
    DBFuzzerAlreadyExistsError,
    DBFuzzerNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMFuzzer,
    ORMEngineID,
    ORMLangID,
    ORMHealth,
    ORMRevision,
    ORMRevisionStatus,
)
from api_gateway.app.utils import ObjectRemovalState, rfc3339_now, testing_only

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

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBFuzzers(DBBase, IFuzzers):

    _col_fuzzers: StandardCollection

    """Used for managing fuzzers"""

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_fuzzers = db[collections.fuzzers]
        super().__init__(db, collections)

    async def _get(
        self,
        removal_state: ObjectRemovalState,
        fuzzer_id: Optional[str] = None,
        fuzzer_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        assert fuzzer_id or (fuzzer_name and project_id)

        # fmt: off
        query, variables = """
            FOR fuzzer in @@col_fuzzers
                <filter-options>
                LIMIT 1

                LET active_revision = FIRST(
                    FOR revision IN @@col_revisions
                        FILTER revision._key == fuzzer.active_revision
                        FILTER revision.fuzzer_id == fuzzer._key
                        FILTER revision.erasure_date == null
                    
                        LIMIT 1 RETURN MERGE(revision, {
                            "id": revision._key,
                        })
                )
                
                RETURN MERGE(fuzzer, {
                    "id": fuzzer._key,
                    "active_revision": active_revision
                })
        """, {
            "@col_fuzzers": self._collections.fuzzers,
            "@col_revisions": self._collections.revisions,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query=query,
            variables=variables,
            fuzzer_id=fuzzer_id,
            fuzzer_name=fuzzer_name,
            project_id=project_id,
            removal_state=removal_state,
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)

        if cursor.empty():
            raise DBFuzzerNotFoundError()

        return ORMFuzzer(**cursor.pop())

    @maybe_unknown_error
    @maybe_not_found(DBFuzzerNotFoundError)
    async def get_by_id(
        self,
        fuzzer_id: str,
        project_id: Optional[str] = None,
        include_erasing: bool = False,
    ) -> ORMFuzzer:
        if include_erasing:
            removal_state = ObjectRemovalState.all
        else:
            removal_state = ObjectRemovalState.visible

        return await self._get(
            fuzzer_id=fuzzer_id,
            project_id=project_id,
            removal_state=removal_state,
        )

    @maybe_unknown_error
    @maybe_not_found(DBFuzzerNotFoundError)
    async def get_by_name(
        self,
        fuzzer_name: str,
        project_id: str,
    ) -> ORMFuzzer:
        return await self._get(
            fuzzer_name=fuzzer_name,
            project_id=project_id,
            removal_state=ObjectRemovalState.present,
        )

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        fuzzer_id: Optional[str] = None,
        fuzzer_name: Optional[str] = None,
        project_id: Optional[str] = None,
        engines: Optional[Set[ORMEngineID]] = None,
        langs: Optional[Set[ORMLangID]] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        if fuzzer_id:
            filters.append("FILTER fuzzer._key == @fuzzer_id")
            variables["fuzzer_id"] = fuzzer_id

        if fuzzer_name:
            filters.append("FILTER fuzzer.name == @fuzzer_name")
            variables["fuzzer_name"] = fuzzer_name

        if project_id:
            filters.append("FILTER fuzzer.project_id == @project_id")
            variables.update({"project_id": project_id})

        if removal_state is None:
            removal_state = ObjectRemovalState.present

        if removal_state == ObjectRemovalState.present:
            filters.append("FILTER fuzzer.erasure_date == null")
        elif removal_state == ObjectRemovalState.trash_bin:
            filters.append("FILTER fuzzer.erasure_date != null")
            filters.append("FILTER fuzzer.erasure_date > @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.erasing:
            filters.append("FILTER fuzzer.erasure_date != null")
            filters.append("FILTER fuzzer.erasure_date <= @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.visible:
            filters.append(
                "FILTER fuzzer.erasure_date == null OR fuzzer.erasure_date > @date_now"
            )
            variables["date_now"] = rfc3339_now()

        if engines:
            filters.append("FILTER fuzzer.engine IN @engines")
            variables.update({"engines": list(engines)})

        if langs:
            filters.append("FILTER fuzzer.lang IN @langs")
            variables.update({"langs": list(langs)})

        if filters:
            query = query.replace("<filter-options>", "\n\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    async def _list(
        self,
        paginator: Optional[Paginator] = None,
        project_id: Optional[str] = None,
        engines: Optional[Set[ORMEngineID]] = None,
        langs: Optional[Set[ORMLangID]] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> Cursor:

        # fmt: off
        query, variables = """
            FOR fuzzer in @@col_fuzzers
                <filter-options>
                SORT DATE_TIMESTAMP(fuzzer.created) DESC
                <limit>

                LET active_revision = FIRST(
                    FOR revision IN @@col_revisions
                        FILTER revision._key == fuzzer.active_revision
                        FILTER revision.fuzzer_id == fuzzer._key
                        FILTER revision.erasure_date == null
                    
                        LIMIT 1 RETURN MERGE(revision, {
                            "id": revision._key,
                        })
                )

                RETURN MERGE(fuzzer, {
                    "id": fuzzer._key,
                    "active_revision": active_revision,
                })
        """, {
            "@col_fuzzers": self._collections.fuzzers,
            "@col_revisions": self._collections.revisions,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query=query,
            variables=variables,
            project_id=project_id,
            engines=engines,
            langs=langs,
            removal_state=removal_state,
        )

        if paginator is not None:
            query = query.replace("<limit>", "LIMIT @offset, @limit")
            variables["offset"] = paginator.offset
            variables["limit"] = paginator.limit
        else:
            query = query.replace("<limit>", "")

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor

    @maybe_unknown_error
    async def list(
        self,
        paginator: Optional[Paginator] = None,
        project_id: Optional[str] = None,
        engines: Optional[Set[ORMEngineID]] = None,
        langs: Optional[Set[ORMLangID]] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> List[ORMFuzzer]:

        cursor = await self._list(
            paginator=paginator,
            project_id=project_id,
            engines=engines,
            langs=langs,
            removal_state=removal_state,
        )
        return [ORMFuzzer(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def list_internal(
        self,
        project_id: str,
    ):

        cursor = await self._list(
            project_id=project_id,
        )

        async def async_iter():
            async for doc in cursor:
                yield ORMFuzzer(**doc)

        return async_iter()

    @maybe_unknown_error
    async def count(
        self,
        project_id: Optional[str] = None,
        engines: Optional[Set[ORMEngineID]] = None,
        langs: Optional[Set[ORMLangID]] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> int:

        # fmt: off
        query, variables = """
            FOR fuzzer IN @@collection
                <filter-options>
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._col_fuzzers.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query=query,
            variables=variables,
            project_id=project_id,
            engines=engines,
            langs=langs,
            removal_state=removal_state,
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return 0 if cursor.empty() else cursor.pop()

    @maybe_unknown_error
    async def create(
        self,
        name: str,
        description: str,
        project_id: str,
        engine: ORMEngineID,
        lang: ORMLangID,
        ci_integration: bool,
        created: str,
        active_revision: Optional[ORMRevision],
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMFuzzer:
        
        fuzzer = ORMFuzzer(
            id="", # filled from meta
            name=name,
            description=description,
            project_id=project_id,
            engine=engine,
            lang=lang,
            ci_integration=ci_integration,
            created=created,
            active_revision=active_revision,
            erasure_date=erasure_date,
            no_backup=no_backup,
        )

        doc = fuzzer.dict(exclude={"id", "active_revision"})
        if fuzzer.active_revision is not None:
            doc["active_revision"] = fuzzer.active_revision.id
        
        meta = await self._col_fuzzers.insert(doc)
        fuzzer.id = meta["_key"]

        return fuzzer

    @maybe_unknown_error
    @maybe_already_exists(DBFuzzerAlreadyExistsError)
    async def update(self, fuzzer: ORMFuzzer):
        doc = fuzzer.dict(exclude={"active_revision"})
        if fuzzer.active_revision is not None:
            doc["active_revision"] = fuzzer.active_revision.id
        await self._col_fuzzers.replace(id_to_dbkey(doc), silent=True)

    @maybe_unknown_error
    async def delete(self, fuzzer: ORMFuzzer):

        # fmt: off
        query, variables = """
            FOR revision IN @@collection
                FILTER revision.fuzzer_id == @fuzzer_id
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._collections.revisions,
            "fuzzer_id": fuzzer.id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        revisions_in_db: int = cursor.pop()
        if revisions_in_db != 0:
            raise Exception("TODO: ")

        await self._col_fuzzers.delete(fuzzer.id)

    @testing_only
    @maybe_unknown_error
    async def create_default_fuzzer(self, project_id: str) -> ORMFuzzer:
        return await self.create(
            name="default",
            description="Default fuzzer",
            engine=ORMEngineID.libfuzzer,
            lang=ORMLangID.cpp,
            created=rfc3339_now(),
            project_id=project_id,
            ci_integration=False,
            active_revision=None,
        )

    @testing_only
    @maybe_unknown_error
    async def generate_test_set(self, n: int) -> List[ORMFuzzer]:

        # fmt: off
        query, variables = """

            // Copy owner id from default project
            LET project_id = FIRST(@@collection).project_id

            FOR i in 1..@count
                INSERT {
                    name: CONCAT("fuzzer", i),
                    description: CONCAT("Description ", i),
                    created: DATE_ISO8601(DATE_NOW()),
                    project_id: project_id,
                    engine: @engine_libfuzzer,
                    lang: @lang_cpp,
                    ci_integration: false,
                } INTO @@collection

                RETURN MERGE(NEW, {
                    "id": NEW._key
                })
        """, {
            "@collection": self._collections.fuzzers,
            "engine_libfuzzer": ORMEngineID.libfuzzer,
            "lang_cpp": ORMLangID.cpp,
            "count": n,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMFuzzer(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def trashbin_list(
        self, paginator: Paginator, project_id: str
    ) -> List[ORMFuzzer]:

        # fmt: off
        query, variables = """

            FOR fuzzer in @@col_fuzzers
                FILTER fuzzer.project_id == @project_id

                LET revs_in_trashbin = FIRST(
                    FOR rev in @@col_revisions
                        FILTER rev.fuzzer_id == fuzzer._key
                        FILTER rev.erasure_date != null
                        FILTER rev.erasure_date > @date_now

                        COLLECT WITH COUNT INTO rev_count
                        RETURN rev_count
                )

                FILTER (fuzzer.erasure_date != null AND fuzzer.erasure_date > @date_now)
                    OR (fuzzer.erasure_date == null AND revs_in_trashbin > 0)

                SORT DATE_TIMESTAMP(fuzzer.created) DESC
                LIMIT @offset, @limit

                LET active_revision = FIRST(
                    FOR revision IN @@col_revisions
                        FILTER revision._key == fuzzer.active_revision
                        FILTER revision.fuzzer_id == fuzzer._key
                        FILTER revision.erasure_date == null
                    
                        LIMIT 1 RETURN MERGE(revision, {
                            "id": revision._key,
                        })
                )

                RETURN MERGE(fuzzer, {
                    "id": fuzzer._key,
                    "active_revision": active_revision,
                })
        """, {
            "@col_fuzzers": self._collections.fuzzers,
            "@col_revisions": self._collections.revisions,
            "project_id": project_id,
            "offset": paginator.offset,
            "date_now": rfc3339_now(),
            "limit": paginator.limit,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMFuzzer(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def trashbin_count(self, project_id: str) -> int:

        # fmt: off
        query, variables = """

            FOR fuzzer in @@col_fuzzers
                FILTER fuzzer.project_id == @project_id

                LET revs_in_trashbin = FIRST(
                    FOR rev in @@col_revisions
                        FILTER rev.fuzzer_id == fuzzer._key
                        FILTER rev.erasure_date != null
                        FILTER rev.erasure_date > @date_now

                        COLLECT WITH COUNT INTO rev_count
                        RETURN rev_count
                )

                FILTER (fuzzer.erasure_date != null AND fuzzer.erasure_date > @date_now)
                    OR (fuzzer.erasure_date == null AND revs_in_trashbin > 0)

                COLLECT WITH COUNT INTO fuzz_count
                RETURN fuzz_count
        """, {
            "@col_fuzzers": self._collections.fuzzers,
            "@col_revisions": self._collections.revisions,
            "project_id": project_id,
            "date_now": rfc3339_now(),
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    @maybe_unknown_error
    async def trashbin_empty(
        self, project_id: str, fuzzer_id: Optional[str] = None
    ) -> Tuple[int, int]:

        # fmt: off
        query, variables = """
            LET erased_revisions = FIRST(
                FOR fuzzer IN @@col_fuzzers
                    FILTER fuzzer.project_id == @project_id
                    <fuzzer-id-filter>
                    FILTER fuzzer.erasure_date == null
                    FOR rev in @@col_revisions
                        FILTER rev.fuzzer_id == fuzzer._key
                        FILTER rev.erasure_date != null
                        FILTER rev.erasure_date > @date_now
                        UPDATE rev WITH {
                            erasure_date: @date_now
                        } IN @@col_revisions
                        COLLECT WITH COUNT INTO erased_revisions_cnt
                        RETURN erased_revisions_cnt
            )
            LET erased_fuzzers = FIRST(
                FOR fuzzer IN @@col_fuzzers
                    FILTER fuzzer.project_id == @project_id
                    <fuzzer-id-filter>
                    FILTER fuzzer.erasure_date != null
                    FILTER fuzzer.erasure_date > @date_now
                    UPDATE fuzzer WITH {
                        erasure_date: @date_now
                    } IN @@col_fuzzers
                    COLLECT WITH COUNT INTO erased_fuzzers_cnt
                    RETURN erased_fuzzers_cnt
            )
            RETURN {
                erased_fuzzers: erased_fuzzers,
                erased_revisions: erased_revisions,
            }
        """, {
            "@col_fuzzers": self._collections.fuzzers,
            "@col_revisions": self._collections.revisions,
            "project_id": project_id,
            "date_now": rfc3339_now(),
        }
        # fmt: on

        if fuzzer_id is None:
            query = query.replace("<fuzzer-id-filter>", "")
        else:
            query = query.replace(
                "<fuzzer-id-filter>", "FILTER fuzzer._key == @fuzzer_id"
            )
            variables["fuzzer_id"] = fuzzer_id

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        result = cursor.pop()
        return (result["erased_fuzzers"], result["erased_revisions"])

    @maybe_unknown_error
    async def set_active_revision(
        self,
        fuzzer: ORMFuzzer,
        revision: Optional[ORMRevision],
        start: bool = False,
        restart: bool = False,
    ):
        start |= restart

        trx_db = await self._db.begin_transaction(
            write=[
                self._collections.fuzzers,
                self._collections.revisions,
            ]
        )

        col_fuzzers = trx_db.collection(self._collections.fuzzers)
        col_revisions = trx_db.collection(self._collections.revisions)

        try:
            #
            # stop previous active revision
            #

            if fuzzer.active_revision is not None:
                if revision is None or revision.id != fuzzer.active_revision.id:
                    status = ORMRevisionStatus.stopped
                    if not fuzzer.active_revision.is_verified:
                        status = ORMRevisionStatus.unverified
                    await col_revisions.update(
                        dict(
                            _key=fuzzer.active_revision.id,
                            status=status,
                            last_stop_date=rfc3339_now(),
                        )
                    )

            #
            # set active revision id to fuzzer
            #

            fuzzer.active_revision = revision
            await col_fuzzers.update(
                dict(
                    _key=fuzzer.id,
                    active_revision=revision.id if revision else None,
                )
            )

            #
            # (re)start new active revision(if need)
            #

            if start:
                if revision.status not in [
                    ORMRevisionStatus.running,
                    ORMRevisionStatus.verifying,
                ]:
                    revision.feedback = None
                    revision.last_start_date = rfc3339_now()
                    if revision.status == ORMRevisionStatus.unverified:
                        revision.status = ORMRevisionStatus.verifying
                    else:
                        revision.status = ORMRevisionStatus.running

                if restart:
                    revision.health = ORMHealth.ok

                await col_revisions.update(
                    dict(
                        _key=revision.id,
                        feedback=revision.feedback,
                        last_start_date=revision.last_start_date,
                        status=revision.status,
                        health=revision.health,
                    )
                )
        except:
            await trx_db.abort_transaction()
            raise
        else:
            await trx_db.commit_transaction()
