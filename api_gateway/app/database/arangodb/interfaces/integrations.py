from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IIntegrations
from api_gateway.app.database.errors import (
    DBIntegrationAlreadyExistsError,
    DBIntegrationNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMIntegration,
    ORMIntegrationStatus,
    ORMIntegrationTypeID,
)
from api_gateway.app.utils import testing_only

from .base import DBBase
from .utils import dbkey_to_id, id_to_dbkey, maybe_already_exists, maybe_unknown_error

if TYPE_CHECKING:
    from typing import List, Optional, Set

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBIntegrations(DBBase, IIntegrations):

    _col_integrations: StandardCollection

    """Stores integration settings of bug tracking systems """

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_integrations = db[collections.integrations]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def get_by_id(
        self,
        integration_id: str,
        project_id: Optional[str] = None,
    ) -> ORMIntegration:

        integration_dict = await self._col_integrations.get(integration_id)

        if not integration_dict:
            raise DBIntegrationNotFoundError()

        integration = ORMIntegration(**dbkey_to_id(integration_dict))

        if project_id is not None:
            if project_id != integration.project_id:
                raise DBIntegrationNotFoundError()

        return integration

    @maybe_unknown_error
    async def get_by_name(
        self,
        integration_name: str,
        project_id: str,
    ) -> ORMIntegration:

        filters = {"name": integration_name, "project_id": project_id}
        cursor: Cursor = await self._col_integrations.find(filters, limit=1)

        if cursor.empty():
            raise DBIntegrationNotFoundError()

        return ORMIntegration(**dbkey_to_id(cursor.pop()))

    @maybe_unknown_error
    async def get_by_config_id(self, config_id: str) -> ORMIntegration:

        filters = {"config_id": config_id}
        cursor: Cursor = await self._col_integrations.find(filters, limit=1)

        if cursor.empty():
            raise DBIntegrationNotFoundError()

        return ORMIntegration(**dbkey_to_id(cursor.pop()))

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        project_id: Optional[str] = None,
        statuses: Optional[Set[ORMIntegrationStatus]] = None,
        types: Optional[Set[ORMIntegrationTypeID]] = None,
        find_disabled: bool = True,
        find_enabled: bool = True,
    ):
        assert "<filter-options>" in query
        filters = list()

        if project_id:
            filters.append("FILTER integration.project_id == @project_id")
            variables.update({"project_id": project_id})

        if find_enabled != find_disabled:
            if find_enabled:
                filters.append("FILTER integration.enabled == true")
            else:  # find_disabled
                filters.append("FILTER integration.enabled == false")

        if statuses:
            filters.append("FILTER integration.status IN @statuses")
            variables.update({"statuses": list(statuses)})

        if types:
            filters.append("FILTER integration.type IN @types")
            variables.update({"types": list(types)})

        if filters:
            query = query.replace("<filter-options>", "\n\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    @maybe_unknown_error
    async def list(
        self,
        paginator: Optional[Paginator] = None,
        project_id: Optional[str] = None,
        statuses: Optional[Set[ORMIntegrationStatus]] = None,
        types: Optional[Set[ORMIntegrationTypeID]] = None,
        find_disabled: bool = True,
        find_enabled: bool = True,
    ) -> List[ORMIntegration]:

        # fmt: off
        query, variables = """
            FOR integration in @@collection
                <filter-options>
                SORT integration.name
                <limit>
                RETURN MERGE(integration, {
                    "id": integration._key,
                })
        """, {
            "@collection": self._col_integrations.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query, variables, project_id, statuses, types, find_enabled, find_disabled
        )

        if paginator is not None:
            query = query.replace("<limit>", "LIMIT @offset, @limit")
            variables["offset"] = paginator.offset
            variables["limit"] = paginator.limit
        else:
            query = query.replace("<limit>", "")

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMIntegration(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def count(
        self,
        project_id: Optional[str] = None,
        statuses: Optional[Set[ORMIntegrationStatus]] = None,
        types: Optional[Set[ORMIntegrationTypeID]] = None,
        find_disabled: bool = True,
        find_enabled: bool = True,
    ) -> int:

        # fmt: off
        query, variables = """
            FOR integration IN @@collection
                <filter-options>
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._col_integrations.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query, variables, project_id, statuses, types, find_enabled, find_disabled
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    @maybe_unknown_error
    async def list_internal(self, project_id: str):

        filters = {"project_id": project_id}
        cursor: Cursor = await self._col_integrations.find(filters)

        async def async_iter():
            async for doc in cursor:
                yield ORMIntegration(**dbkey_to_id(doc))

        return async_iter()

    @maybe_unknown_error
    async def create(
        self,
        name: str,
        project_id: str,
        config_id: str,
        type: ORMIntegrationTypeID,
        status: ORMIntegrationStatus,
        last_error: Optional[str],
        update_rev: str,
        enabled: bool,
        num_undelivered: int,
    ) -> ORMIntegration:

        integration = ORMIntegration(
            id="",  # filled from meta
            name=name,
            project_id=project_id,
            config_id=config_id,
            type=type,
            status=status,
            last_error=last_error,
            update_rev=update_rev,
            enabled=enabled,
            num_undelivered=num_undelivered,
        )

        meta = await self._col_integrations.insert(integration.dict(exclude={"id"}))
        integration.id = meta["_key"]

        return integration

    @maybe_unknown_error
    @maybe_already_exists(DBIntegrationAlreadyExistsError)
    async def update(self, integration: ORMIntegration):
        await self._col_integrations.replace(
            id_to_dbkey(integration.dict()), silent=True
        )

    @maybe_unknown_error
    async def delete(self, integration: ORMIntegration):
        await self._col_integrations.delete(
            integration.id, silent=True, ignore_missing=True
        )

    @testing_only
    @maybe_unknown_error
    async def generate_builtin_test_set(self, n: int) -> List[ORMIntegration]:

        # fmt: off
        query, variables = """

            // Copy owner id from default project
            LET project_id = FIRST(@@collection).project_id

            FOR i in 1..@count
                INSERT {
                    name: CONCAT("integration", i),
                    project_id: project_id,
                    config_id: "12345",
                    update_rev: "12345",
                    num_undelivered: 0,
                    enabled: true,
                    status: @status,
                    type: @type,
                } INTO @@collection

                RETURN MERGE(NEW, {
                    "id": NEW._key
                })
        """, {
            "@collection": self._collections.integrations,
            "status": ORMIntegrationStatus.succeeded,
            "type": ORMIntegrationTypeID.jira,
            "count": n,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMIntegration(**doc) async for doc in cursor]
