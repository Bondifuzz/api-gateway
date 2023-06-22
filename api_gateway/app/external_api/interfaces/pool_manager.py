from typing import List, Optional, Union

from api_gateway.app.api.base import ItemCountResponseModel
from api_gateway.app.api.models.pools import (
    AdminUpdatePoolInfoRequestModel,
    CloudNodeGroupModel,
    CreatePoolRequestModel,
    LocalNodeGroupModel,
    PoolResponseModel,
)
from api_gateway.app.settings import AppSettings
from api_gateway.app.utils import PrefixedLogger

from ..utils import wrap_aiohttp_errors
from .base import ExternalAPIBase


class PoolManagerAPI(ExternalAPIBase):

    """Communication with Pool manager"""

    def __init__(self, settings: AppSettings):
        super().__init__(settings.api.endpoints.pool_manager)
        extra = {"prefix": f"[{self.__class__.__name__}]"}
        self._logger = PrefixedLogger(self._logger, extra)
        self._base_path = "/api/v1/pools"

    @wrap_aiohttp_errors
    async def create_pool(
        self,
        body: CreatePoolRequestModel,
    ):
        response = await self._session.post(
            url=self._base_path,
            json=body.dict(),
        )
        return await self.parse_response(response, PoolResponseModel)

    @wrap_aiohttp_errors
    async def get_pool_by_id(
        self,
        id: str,
        user_id: Optional[str] = None,
    ):
        params = dict()
        if user_id is not None:
            params["user_id"] = user_id

        url = f"{self._base_path}/{id}"
        response = await self._session.get(url, params=params)
        return await self.parse_response(response, PoolResponseModel)

    @wrap_aiohttp_errors
    async def get_pool_by_name(
        self,
        name: str,
        user_id: Optional[str],
    ):
        params = {
            "name": name,
        }
        if user_id is not None:
            params["user_id"] = user_id

        url = f"{self._base_path}/lookup"
        response = await self._session.get(url, params=params)
        return await self.parse_response(response, PoolResponseModel)

    @wrap_aiohttp_errors
    async def update_pool_info(
        self,
        id: str,
        body: AdminUpdatePoolInfoRequestModel,
        user_id: Optional[str] = None,
    ):
        params = dict()
        if user_id is not None:
            params["user_id"] = user_id

        response = await self._session.patch(
            url=f"{self._base_path}/{id}",
            params=params,
            json=body.dict(exclude_unset=True),
        )
        await self.parse_response_no_model(response)

    @wrap_aiohttp_errors
    async def update_pool_node_group(
        self,
        id: str,
        node_group: Union[LocalNodeGroupModel, CloudNodeGroupModel],
        user_id: Optional[str] = None,
    ):
        params = dict()
        if user_id is not None:
            params["user_id"] = user_id

        response = await self._session.put(
            url=f"{self._base_path}/{id}/node_group",
            params=params,
            json=node_group.dict(),
        )
        await self.parse_response_no_model(response)

    @wrap_aiohttp_errors
    async def delete_pool(
        self,
        id: str,
        user_id: Optional[str] = None,
    ):
        params = dict()
        if user_id is not None:
            params["user_id"] = user_id

        response = await self._session.delete(f"{self._base_path}/{id}", params=params)
        await self.parse_response_no_model(response)

    @wrap_aiohttp_errors
    async def count_pools(
        self,
        pg_size: int,
        user_id: Optional[str],
    ):
        params = {
            "pg_size": pg_size,
        }

        if user_id is not None:
            params["user_id"] = user_id

        url = f"{self._base_path}/count"
        response = await self._session.get(url, params=params)
        return await self.parse_response(response, ItemCountResponseModel)

    @wrap_aiohttp_errors
    async def list_pools(
        self,
        pg_num: int,
        pg_size: int,
        user_id: Optional[str],
    ):
        params = {
            "pg_num": pg_num,
            "pg_size": pg_size,
        }

        if user_id is not None:
            params["user_id"] = user_id

        # TODO: yield?
        pools: List[PoolResponseModel] = list()
        async for pool in self.paginate(
            self._base_path, PoolResponseModel, params=params
        ):
            pools.append(pool)

        return pools

    @wrap_aiohttp_errors
    async def count_available_pools(
        self,
        pg_size: int,
        user_id: str,
    ):
        params = {
            "pg_size": pg_size,
            "user_id": user_id,
        }

        url = f"{self._base_path}/available/count"
        response = await self._session.get(url, params=params)
        return await self.parse_response(response, ItemCountResponseModel)

    @wrap_aiohttp_errors
    async def list_available_pools(
        self,
        pg_num: int,
        pg_size: int,
        user_id: str,
    ):
        params = {
            "pg_num": pg_num,
            "pg_size": pg_size,
            "user_id": user_id,
        }

        # TODO: yield?
        url = f"{self._base_path}/available"
        pools: List[PoolResponseModel] = list()
        async for pool in self.paginate(url, PoolResponseModel, params=params):
            pools.append(pool)

        return pools
