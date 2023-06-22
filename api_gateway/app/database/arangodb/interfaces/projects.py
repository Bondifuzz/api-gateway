from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IProjects
from api_gateway.app.database.errors import (
    DBProjectAlreadyExistsError,
    DBProjectNotFoundError,
)
from api_gateway.app.database.orm import ORMProject, ORMRevisionStatus
from api_gateway.app.utils import (
    ObjectRemovalState,
    rfc3339_expired,
    rfc3339_now,
    testing_only,
)

from .base import DBBase
from .utils import dbkey_to_id, id_to_dbkey, maybe_already_exists, maybe_unknown_error

if TYPE_CHECKING:
    from typing import List, Optional

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBProjects(DBBase, IProjects):

    _col_projects: StandardCollection

    """Used for managing project projects"""

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_projects = db[collections.projects]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def get_by_id(
        self,
        project_id: str,
        owner_id: Optional[str] = None,
        include_erasing: bool = False,
    ) -> ORMProject:

        project_dict = await self._col_projects.get(project_id)

        if not project_dict:
            raise DBProjectNotFoundError()

        project = ORMProject(**dbkey_to_id(project_dict))

        if owner_id is not None:
            if owner_id != project.owner_id:
                raise DBProjectNotFoundError()

        if not include_erasing and project.erasure_date:
            if rfc3339_expired(project.erasure_date):
                raise DBProjectNotFoundError()

        return project

    @maybe_unknown_error
    async def get_by_name(
        self,
        project_name: str,
        owner_id: str,
    ) -> ORMProject:

        filters = {
            "name": project_name,
            "owner_id": owner_id,
            "erasure_date": None,  # filter out trashbin objects
        }

        cursor: Cursor = await self._col_projects.find(filters, limit=1)

        if cursor.empty():
            raise DBProjectNotFoundError()

        return ORMProject(**dbkey_to_id(cursor.pop()))

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        owner_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        if owner_id:
            filters.append("FILTER project.owner_id == @owner_id")
            variables.update({"owner_id": owner_id})

        if removal_state is None:
            removal_state = ObjectRemovalState.present

        if removal_state == ObjectRemovalState.present:
            filters.append("FILTER project.erasure_date == null")
        elif removal_state == ObjectRemovalState.trash_bin:
            filters.append("FILTER project.erasure_date != null")
            filters.append("FILTER project.erasure_date > @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.erasing:
            filters.append("FILTER project.erasure_date != null")
            filters.append("FILTER project.erasure_date <= @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.visible:
            filters.append(
                "FILTER project.erasure_date == null OR project.erasure_date > @date_now"
            )
            variables["date_now"] = rfc3339_now()

        if filters:
            query = query.replace("<filter-options>", "\n\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    @maybe_unknown_error
    async def list(
        self,
        paginator: Paginator,
        owner_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> List[ORMProject]:

        # fmt: off
        query, variables = """
            FOR project in @@collection
                <filter-options>
                SORT DATE_TIMESTAMP(project.created) DESC
                LIMIT @offset, @limit
                RETURN MERGE(project, {
                    "id": project._key,
                })
        """, {
            "@collection": self._collections.projects,
            "offset": paginator.offset,
            "limit": paginator.limit,
        }
        # fmt: on

        # TODO: filter projects/fuzzers/revisions
        # created from <date-begin> to <date-end>

        query, variables = self._apply_filter_options(
            query, variables, owner_id, removal_state
        )

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMProject(**doc) async for doc in cursor]

    # TODO: rewrite
    @maybe_unknown_error
    async def get_pool_load(
        self, paginator: Paginator, pool_id: str
    ) -> List[ORMPoolLoad]:

        # fmt: off
        query, variables = """
            FOR project in @@col_projects
                FILTER project.pool_id == @pool_id
                FILTER project.erasure_date == null

                FOR fuzzer IN @@col_fuzzers
                    FILTER fuzzer.project_id == project._key
                    FILTER fuzzer.active_revision != null

                    FOR revision IN @@col_revisions
                        FILTER revision._key == fuzzer.active_revision
                        FILTER revision.status == @status_running

                        COLLECT AGGREGATE
                            cpu = SUM(revision.cpu_usage),
                            ram = SUM(revision.ram_usage + revision.tmpfs_usage)
                        
                        RETURN {
                            cpu: cpu,
                            ram: ram,
                        }

        """, {
            "@col_projects": self._collections.projects,
            "@col_fuzzers": self._collections.projects,
            "@col_revisions": self._collections.projects,
            "pool_id": pool_id,
            "status_running": ORMRevisionStatus.running,
        }
        # fmt: on

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMPoolLoad(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def list_internal(self, owner_id: str):

        filters = {"owner_id": owner_id}
        cursor: Cursor = await self._col_projects.find(filters)

        async def async_iter():
            async for doc in cursor:
                yield ORMProject(**dbkey_to_id(doc))

        return async_iter()

    @maybe_unknown_error
    async def count(
        self,
        owner_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> int:

        # fmt: off
        query, variables = """
            FOR project IN @@collection
                <filter-options>
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._col_projects.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query, variables, owner_id, removal_state
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    @maybe_unknown_error
    async def create(
        self,
        name: str,
        description: str,
        owner_id: str,
        created: str,
        pool_id: Optional[str],
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMProject:

        project = ORMProject(
            id="",  # filled from meta
            name=name,
            description=description,
            owner_id=owner_id,
            created=created,
            pool_id=pool_id,
            erasure_date=erasure_date,
            no_backup=no_backup,
        )

        meta = await self._col_projects.insert(project.dict(exclude={"id"}))
        project.id = meta["_key"]

        return project

    @maybe_unknown_error
    @maybe_already_exists(DBProjectAlreadyExistsError)
    async def update(self, project: ORMProject):
        await self._col_projects.replace(id_to_dbkey(project.dict()), silent=True)

    @maybe_unknown_error
    async def delete(self, project: ORMProject):

        # fmt: off
        query, variables = """
            FOR fuzzer IN @@collection
                FILTER fuzzer.project_id == @project_id
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._collections.fuzzers,
            "project_id": project.id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        fuzzers_in_db: int = cursor.pop()
        if fuzzers_in_db != 0:
            raise Exception("fuzzers_in_db != 0")

        await self._col_projects.delete(project.id)

    @maybe_unknown_error
    async def create_default_project(self, owner_id: str, pool_id: str) -> ORMProject:
        return await self.create(
            name="default",
            description="Default project",
            created=rfc3339_now(),
            owner_id=owner_id,
            pool_id=pool_id,
        )

    @testing_only
    @maybe_unknown_error
    async def generate_test_set(self, n: int) -> List[ORMProject]:

        # fmt: off
        query, variables = """

            // Copy owner id from default project
            LET project_id = FIRST(@@collection)._key

            FOR i in 1..@count
                INSERT {
                    name: CONCAT("image", i),
                    description: CONCAT("Description ", i),
                    created: DATE_ISO8601(DATE_NOW()),
                    project_id: project_id,
                } INTO @@collection

                RETURN MERGE(NEW, {
                    "id": NEW._key
                })
        """, {
            "@collection": self._collections.projects,
            "count": n,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMProject(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def trashbin_empty(self, user_id: str) -> int:

        # fmt: off
        query, variables = """
            FOR project in @@collection_projects
                FILTER project.owner_id == @user_id
                FILTER project.erasure_date != null
                FILTER project.erasure_date > @date_now
                UPDATE project WITH {
                    erasure_date: @date_now
                } IN @@collection_projects
                COLLECT WITH COUNT INTO erased_projects_cnt
                RETURN erased_projects_cnt
        """, {
            "@collection_projects": self._collections.projects,
            "date_now": rfc3339_now(),
            "user_id": user_id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()
