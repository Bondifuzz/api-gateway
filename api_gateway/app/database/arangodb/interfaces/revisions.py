from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IRevisions
from api_gateway.app.database.errors import DBRevisionNotFoundError
from api_gateway.app.database.orm import (
    ORMFeedback,
    ORMHealth,
    ORMRevision,
    ORMRevisionStatus,
    ORMUploadStatus,
)
from api_gateway.app.utils import (
    ObjectRemovalState,
    rfc3339_expired,
    rfc3339_now,
    testing_only,
)

from .base import DBBase
from .utils import dbkey_to_id, id_to_dbkey, maybe_unknown_error

if TYPE_CHECKING:
    from typing import List, Optional, Set

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBRevisions(DBBase, IRevisions):

    _col_revisions: StandardCollection

    """Used for managing revisions"""

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_revisions = db[collections.revisions]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def get_by_id(
        self,
        revision_id: str,
        fuzzer_id: Optional[str] = None,
        include_erasing: bool = False,
    ) -> ORMRevision:

        revision_dict = await self._col_revisions.get(revision_id)

        if not revision_dict:
            raise DBRevisionNotFoundError()

        revision = ORMRevision(**dbkey_to_id(revision_dict))

        if fuzzer_id is not None:
            if fuzzer_id != revision.fuzzer_id:
                raise DBRevisionNotFoundError()

        if not include_erasing and revision.erasure_date:
            if rfc3339_expired(revision.erasure_date):
                raise DBRevisionNotFoundError()

        return revision

    @maybe_unknown_error
    async def get_by_name(
        self,
        revision_name: str,
        fuzzer_id: str,
    ) -> ORMRevision:

        filters = {
            "name": revision_name,
            "fuzzer_id": fuzzer_id,
            "erasure_date": None,  # filter out trashbin objects
        }

        cursor: Cursor = await self._col_revisions.find(filters, limit=1)

        if cursor.empty():
            raise DBRevisionNotFoundError()

        return ORMRevision(**dbkey_to_id(cursor.pop()))

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        fuzzer_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
        statuses: Optional[Set[ORMRevisionStatus]] = None,
        health: Optional[Set[ORMHealth]] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        if fuzzer_id:
            filters.append("FILTER revision.fuzzer_id == @fuzzer_id")
            variables.update({"fuzzer_id": fuzzer_id})

        if removal_state is None:
            removal_state = ObjectRemovalState.present

        if removal_state == ObjectRemovalState.present:
            filters.append("FILTER revision.erasure_date == null")
        elif removal_state == ObjectRemovalState.trash_bin:
            filters.append("FILTER revision.erasure_date != null")
            filters.append("FILTER revision.erasure_date > @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.erasing:
            filters.append("FILTER revision.erasure_date != null")
            filters.append("FILTER revision.erasure_date <= @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.visible:
            filters.append(
                "FILTER revision.erasure_date == null OR revision.erasure_date > @date_now"
            )
            variables["date_now"] = rfc3339_now()

        if statuses:
            filters.append("FILTER revision.status IN @statuses")
            variables.update({"statuses": list(statuses)})

        if health:
            filters.append("FILTER revision.health IN @health")
            variables.update({"health": list(health)})

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
        removal_state: Optional[ObjectRemovalState] = None,
        statuses: Optional[Set[ORMRevisionStatus]] = None,
        health: Optional[Set[ORMHealth]] = None,
    ) -> List[ORMRevision]:

        # fmt: off
        query, variables = """
            FOR revision in @@collection
                <filter-options>
                SORT revision.created DESC
                LIMIT @offset, @limit
                RETURN MERGE(revision, {
                    "id": revision._key,
                })
        """, {
            "@collection": self._col_revisions.name,
            "offset": paginator.offset,
            "limit": paginator.limit,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query,
            variables,
            fuzzer_id,
            removal_state,
            statuses,
            health,
        )

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMRevision(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def list_internal(self, fuzzer_id: str):

        filters = {"fuzzer_id": fuzzer_id}
        cursor: Cursor = await self._col_revisions.find(filters)

        async def async_iter():
            async for doc in cursor:
                yield ORMRevision(**dbkey_to_id(doc))

        return async_iter()

    @maybe_unknown_error
    async def count(
        self,
        fuzzer_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
        statuses: Optional[Set[ORMRevisionStatus]] = None,
        health: Optional[Set[ORMHealth]] = None,
    ) -> int:

        # fmt: off
        query, variables = """
            FOR revision IN @@collection
                <filter-options>
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._col_revisions.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query,
            variables,
            fuzzer_id,
            removal_state,
            statuses,
            health,
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    @maybe_unknown_error
    async def create(
        self,
        name: str,
        description: str,
        binaries: ORMUploadStatus,
        seeds: ORMUploadStatus,
        config: ORMUploadStatus,
        status: ORMRevisionStatus,
        health: ORMHealth,
        fuzzer_id: str,
        image_id: str,
        is_verified: bool,
        created: str,
        cpu_usage: int,
        ram_usage: int,
        tmpfs_size: int,
        feedback: Optional[ORMFeedback] = None,
        last_start_date: Optional[str] = None,
        last_stop_date: Optional[str] = None,
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMRevision:

        revision = ORMRevision(
            id="",  # filled from meta
            name=name,
            description=description,
            binaries=binaries,
            seeds=seeds,
            config=config,
            status=status,
            health=health,
            fuzzer_id=fuzzer_id,
            image_id=image_id,
            is_verified=is_verified,
            created=created,
            cpu_usage=cpu_usage,
            ram_usage=ram_usage,
            tmpfs_size=tmpfs_size,
            feedback=feedback,
            last_start_date=last_start_date,
            last_stop_date=last_stop_date,
            erasure_date=erasure_date,
            no_backup=no_backup,
        )

        meta = await self._col_revisions.insert(revision.dict(exclude={"id"}))
        revision.id = meta["_key"]

        return revision

    @maybe_unknown_error
    async def update(self, revision: ORMRevision):
        await self._col_revisions.replace(id_to_dbkey(revision.dict()), silent=True)

    @maybe_unknown_error
    async def delete(self, revision: ORMRevision):

        # no childs :(
        # TODO: statistics?
        await self._col_revisions.delete(revision.id)

    @testing_only
    @maybe_unknown_error
    async def create_default(self, fuzzer_id: str, image_id: str) -> ORMRevision:
        return await self.create(
            name="default",
            description="Default revision",
            image_id=image_id,
            fuzzer_id=fuzzer_id,
            status=ORMRevisionStatus.unverified,
            health=ORMHealth.err,
            binaries=ORMUploadStatus(uploaded=False),
            config=ORMUploadStatus(uploaded=False),
            seeds=ORMUploadStatus(uploaded=False),
            cpu_usage=1000,
            ram_usage=1000,
            tmpfs_size=1000,
            created=rfc3339_now(),
            is_verified=False,
        )

    @testing_only
    @maybe_unknown_error
    async def create_custom(
        self,
        name: str,
        fuzzer_id: str,
        image_id: str,
        status=ORMRevisionStatus.unverified,
        health=ORMHealth.err,
        binaries=ORMUploadStatus(uploaded=False),
        seeds=ORMUploadStatus(uploaded=False),
        config=ORMUploadStatus(uploaded=False),
        is_verified=False,
    ) -> ORMRevision:
        return await self.create(
            ORMRevision(
                name=name,
                description="Custom revision",
                image_id=image_id,
                fuzzer_id=fuzzer_id,
                status=status,
                health=health,
                binaries=binaries,
                config=config,
                seeds=seeds,
                cpu_usage=1000,
                ram_usage=1000,
                tmpfs_size=1000,
                created=rfc3339_now(),
                is_verified=is_verified,
            )
        )

    @maybe_unknown_error
    async def stop_all(self, project_id: str):

        # fmt: off
        query, variables = """
            FOR fuzzer in @@col_fuzzers
                FILTER fuzzer.project_id == @project_id
                FILTER fuzzer.active_revision != null

                FOR rev IN @@col_revisions
                    FILTER fuzzer.active_revision == rev._key
                    FILTER rev.status IN [@st_running, @st_verifying]

                    LET new_status = (rev.status == @st_verifying)
                        ? @st_unverified
                        : @st_stopped

                    UPDATE rev WITH {
                        status: new_status,
                        last_stop_date: DATE_ISO8601(DATE_NOW()),
                    } IN @@col_revisions
        """, {
            "@col_fuzzers": self._collections.fuzzers,
            "@col_revisions": self._collections.revisions,
            "st_running": ORMRevisionStatus.running.value,
            "st_verifying": ORMRevisionStatus.verifying.value,
            "st_unverified": ORMRevisionStatus.unverified.value,
            "st_stopped": ORMRevisionStatus.stopped.value,
            "project_id": project_id,
        }
        # fmt: on

        await self._db.aql.execute(query, bind_vars=variables)

    @testing_only
    @maybe_unknown_error
    async def generate_test_set(self, n: int) -> List[ORMRevision]:

        not_uploaded = {
            "uploaded": False,
            "last_error": None,
        }

        # fmt: off
        query, variables = """

            // Copy fuzzer id from default revision
            LET fuzzer_id = FIRST(@@col_revisions).fuzzer_id

            // Copy image id from default image
            LET image_id = FIRST(@@col_images)._key

            FOR i in 1..@count
                INSERT {
                    name: CONCAT("revision", i),
                    description: CONCAT("Description ", i),
                    created: DATE_ISO8601(DATE_NOW()),
                    image_id: image_id,
                    fuzzer_id: fuzzer_id,
                    status: @status_unverified,
                    health: @health_err,
                    binaries: @not_uploaded,
                    config: @not_uploaded,
                    seeds: @not_uploaded,
                    cpu_usage: 1000,
                    ram_usage: 1000,
                    tmpfs_size: 1000,
                    is_verified: False,
                } INTO @@col_revisions

                RETURN MERGE(NEW, {
                    "id": NEW._key
                })
        """, {
            "@col_revisions": self._collections.revisions,
            "@col_images": self._collections.images,
            "status_unverified": ORMRevisionStatus.unverified,
            "health_err": ORMHealth.err,
            "not_uploaded": not_uploaded,
            "count": n,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMRevision(**doc) async for doc in cursor]
