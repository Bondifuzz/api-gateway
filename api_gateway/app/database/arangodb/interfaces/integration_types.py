from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IIntegrationTypes
from api_gateway.app.database.errors import (
    DBIntegrationTypeAlreadyExistsError,
    DBIntegrationTypeNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMIntegrationTypeID,
    ORMIntegrationType,
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


class DBIntegrationTypes(DBBase, IIntegrationTypes):

    _col_integrations: StandardCollection
    _col_integration_types: StandardCollection


    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_integrations = db[collections.integrations]
        self._col_integration_types = db[collections.integration_types]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def get_by_id(
        self,
        integration_type_id: ORMIntegrationTypeID,
    ) -> ORMIntegrationType:

        doc: Optional[dict] = await self._col_integration_types.get(integration_type_id)
        if doc is None:
            raise DBIntegrationTypeNotFoundError()
        
        return ORMIntegrationType(**dbkey_to_id(doc))

    @maybe_unknown_error
    async def list(
        self,
        paginator: Optional[Paginator] = None,
    ) -> List[ORMIntegrationType]:

        cursor: Cursor = await self._col_integration_types.all(
            skip=paginator.offset if paginator else None,
            limit=paginator.limit if paginator else None,
        )

        return [ORMIntegrationType(**dbkey_to_id(doc)) async for doc in cursor]

    @maybe_unknown_error
    async def count(self) -> int:
        return await self._col_integration_types.count()

    @maybe_unknown_error
    @maybe_already_exists(DBIntegrationTypeAlreadyExistsError)
    async def create(
        self,
        id: ORMIntegrationTypeID,
        display_name: str,
        twoway: bool,
    ) -> ORMIntegrationType:

        integration_type = ORMIntegrationType(
            id=id,
            display_name=display_name,
            twoway=twoway,
        )

        await self._col_integration_types.insert(
            id_to_dbkey(integration_type.dict()),
            silent=True,
        )

        return integration_type

    @maybe_unknown_error
    @maybe_not_found(DBIntegrationTypeNotFoundError)
    async def update(self, integration_type: ORMIntegrationType):
        doc = id_to_dbkey(integration_type.dict())
        await self._col_integration_types.replace(doc, silent=True)

    @maybe_unknown_error
    async def delete(self, integration_type: ORMIntegrationType):
        await self._col_integration_types.delete(
            integration_type.id,
            silent=True,
            ignore_missing=True,
        )
        filters = { "type": integration_type.id }
        await self._col_integrations.delete_match(filters)

