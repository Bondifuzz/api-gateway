from __future__ import annotations

from typing import TYPE_CHECKING

from api_gateway.app.database.abstract import IImages
from api_gateway.app.database.errors import (
    DBEngineAlreadyEnabledError,
    DBEngineNotEnabledError,
    DBEngineNotFoundError,
    DBEnginesNotFoundError,
    DBImageNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMEngineID,
    ORMLangID,
    ORMImage,
    ORMImageStatus,
    ORMImageType,
)
from api_gateway.app.utils import testing_only

from .base import DBBase
from .utils import dbkey_to_id, id_to_dbkey, maybe_already_exists, maybe_unknown_error, maybe_not_found

if TYPE_CHECKING:
    from typing import List, Optional, Set

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBImages(DBBase, IImages):

    _col_images: StandardCollection
    _col_engines: StandardCollection

    """Used for managing fuzzer docker images in admin space"""

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
    ):
        self._col_images = db[collections.images]
        self._col_engines = db[collections.engines]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def get_by_id(
        self,
        image_id: str,
        project_id: Optional[str] = None,
    ) -> ORMImage:

        img_doc = await self._col_images.get(image_id)
        if img_doc is None:
            raise DBImageNotFoundError()

        image = ORMImage(**dbkey_to_id(img_doc))

        if project_id and image.project_id != project_id:
            raise DBImageNotFoundError()

        return image

    @maybe_unknown_error
    async def get_by_name(
        self,
        image_name: str,
        project_id: Optional[str],
    ) -> ORMImage:

        # TODO: check null filter
        filters = {"name": image_name, "project_id": project_id}
        cursor: Cursor = await self._col_images.find(filters, limit=1)

        if cursor.empty():
            raise DBImageNotFoundError()

        return ORMImage(**dbkey_to_id(cursor.pop()))

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        image_id: Optional[str] = None,
        image_name: Optional[str] = None,
        project_id: Optional[str] = None,
        image_type: Optional[ORMImageType] = None,
        statuses: Optional[Set[ORMImageStatus]] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        if image_id is not None:
            filters.append("FILTER image._key == @image_id")
            variables["image_id"] = image_id

        if image_name is not None:
            filters.append("FILTER image.name == @image_name")
            variables["image_name"] = image_name

        if project_id is not None:
            filters.append("FILTER image.project_id == @project_id")
            variables["project_id"] = project_id

        elif image_type:
            if image_type == ORMImageType.builtin:
                filters.append("FILTER image.project_id == null")
            else: # elif image_type == ORMImageType.custom:
                filters.append("FILTER image.project_id != null")

        if statuses:
            filters.append("FILTER image.status IN @statuses")
            variables["statuses"] = list(statuses)

        if filters:
            query = query.replace("<filter-options>", "\n\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    @maybe_unknown_error
    async def list(
        self,
        paginator: Paginator,
        project_id: Optional[str] = None,
        image_type: Optional[ORMImageType] = None,
        statuses: Optional[Set[ORMImageStatus]] = None,
        engines: Optional[Set[ORMEngineID]] = None,
    ) -> List[ORMImage]:

        # fmt: off
        query, variables = """
            FOR image in @@col_images
                <filter-options>

                // no filter or if any engine present for image
                FILTER LENGTH(@engines) == 0 OR LENGTH(INTERSECTION(image.engines, @engines)) > 0

                SORT !IS_NULL(image.project_id), image.name
                LIMIT @offset, @limit
                RETURN MERGE(image, {
                    "id": image._key,
                })
        """, {
            "@col_images": self._collections.images,
            "engines": list(engines) if engines else list(),
            "offset": paginator.offset,
            "limit": paginator.limit,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query=query,
            variables=variables,
            project_id=project_id,
            image_type=image_type,
            statuses=statuses,
        )

        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMImage(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def count(
        self,
        project_id: Optional[str] = None,
        image_type: Optional[ORMImageType] = None,
        statuses: Optional[Set[ORMImageStatus]] = None,
        engines: Optional[Set[ORMEngineID]] = None,
    ) -> int:

        # fmt: off
        query, variables = """
            FOR image IN @@col_images
                <filter-options>

                // no filter or if any engine present for image
                FILTER LENGTH(@engines) == 0 OR LENGTH(INTERSECTION(image.engines, @engines)) > 0

                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@col_images": self._collections.images,
            "engines": list(engines) if engines else list(),
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query=query,
            variables=variables,
            project_id=project_id,
            image_type=image_type,
            statuses=statuses,
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    async def _get_unknown_engines(self, engine_ids: List[ORMEngineID]) -> List[ORMEngineID]:
        # fmt: off
        query, variables = """
            FOR engine IN @@col_engines
                FILTER engine._key IN @engine_ids
                RETURN engine._key
        """, {
            "@col_engines": self._collections.engines,
            "engine_ids": engine_ids,
        }
        # fmt: on
        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        known_engine_ids = [ORMEngineID(doc) async for doc in cursor]
        unknown_engine_ids = set(engine_ids) - set(known_engine_ids)
        return list(unknown_engine_ids)

    @maybe_unknown_error
    async def create(
        self,
        name: str,
        description: str,
        project_id: Optional[str],
        engines: List[ORMEngineID],
        status: ORMImageStatus,
    ) -> ORMImage:
        image = ORMImage(
            id="", # Filled from meta
            name=name,
            description=description,
            engines=engines,
            project_id=project_id,
            status=status,
        )

        unknown_engines = await self._get_unknown_engines(engines)
        if len(unknown_engines) > 0:
            raise DBEnginesNotFoundError(engines=unknown_engines)

        image_meta: dict = await self._col_images.insert(
            image.dict(exclude={"id"}),
        )

        image.id = image_meta["_key"]
        return image

    @maybe_unknown_error
    async def update(self, image: ORMImage):
        image_dict = id_to_dbkey(image.dict())
        await self._col_images.replace(image_dict, silent=True)

    @maybe_unknown_error
    async def delete(self, image: ORMImage):
        await self._col_images.delete(image.id, silent=True, ignore_missing=True)

    @maybe_unknown_error
    @maybe_not_found(DBImageNotFoundError) # current image deleted
    async def enable_engine(self, image: ORMImage, engine_id: ORMEngineID):

        if engine_id in image.engines:
            raise DBEngineAlreadyEnabledError()

        # fmt: off
        query, variables = """
            FOR engine IN @@col_engines
                FILTER engine._key == @engine_id

                UPDATE @image_id WITH {
                    engines: PUSH(@current_engine_ids, @engine_id, true)
                } IN @@col_images
                RETURN true
        """, {
            "@col_images": self._collections.images,
            "@col_engines": self._collections.engines,
            "engine_id": engine_id,
            "current_engine_ids": image.engines,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        if cursor.empty():
            raise DBEngineNotFoundError()

    @maybe_unknown_error
    async def disable_engine(self, image: ORMImage, engine_id: ORMEngineID):
        if engine_id not in image.engines:
            raise DBEngineNotEnabledError()

        new_engines = list(image.engines)
        new_engines.remove(engine_id)

        await self._col_images.update({
            "_key": image.id,
            "engines": new_engines,
        })

        image.engines = new_engines

    @maybe_unknown_error
    async def set_engines(self, image: ORMImage, engine_ids: List[ORMEngineID]):
        unknown_engines = await self._get_unknown_engines(engine_ids)
        if len(unknown_engines) > 0:
            raise DBEnginesNotFoundError(langs=unknown_engines)
        
        await self._col_images.update({
            "_key": image.id,
            "engines": engine_ids,
        })

        image.engines = engine_ids

    @testing_only
    @maybe_unknown_error
    async def generate_builtin_test_set(self, n: int) -> List[ORMImage]:
        # fmt: off
        query, variables = """
            FOR i in 1..@count
                INSERT {
                    name: CONCAT("image", i),
                    description: CONCAT("Description ", i),
                    project_id: null,
                    engines: [@engine],
                    status: @image_status,
                } INTO @@collection

                RETURN MERGE(NEW, {
                    "id": NEW._key
                })
        """, {
            "@collection": self._collections.images,
            "engine": ORMEngineID.libfuzzer,
            "image_status": ORMImageStatus.ready,
            "count": n,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMImage(**doc) async for doc in cursor]

    @testing_only
    @maybe_unknown_error
    async def create_default(self) -> ORMImage:
        return await self.create(
            name="default",
            description="Default image",
            project_id=None,
            engines=[ORMEngineID.libfuzzer],
            status=ORMImageStatus.ready,
        )
