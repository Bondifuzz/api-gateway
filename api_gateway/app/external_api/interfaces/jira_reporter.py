from pydantic import BaseModel

from api_gateway.app.external_api.models import JiraIntegrationModel
from api_gateway.app.settings import AppSettings
from api_gateway.app.utils import PrefixedLogger

from ..utils import wrap_aiohttp_errors
from .base import ExternalAPIBase


class CreateIntegrationResponseModel(BaseModel):
    id: str


class GetIntegrationResponseModel(JiraIntegrationModel):
    id: str


class JiraReporterAPI(ExternalAPIBase):

    """Communication with Jira reporter"""

    def __init__(self, settings: AppSettings):
        super().__init__(settings.api.endpoints.jira_reporter)
        extra = {"prefix": f"[{self.__class__.__name__}]"}
        self._logger = PrefixedLogger(self._logger, extra)
        self._base_path = "/api/v1/integrations"

    @wrap_aiohttp_errors
    async def create_integration(self, integration: JiraIntegrationModel):
        json_data = integration.dict(exclude={"id"})
        response = await self._session.post(self._base_path, json=json_data)
        data = await self.parse_response(response, CreateIntegrationResponseModel)
        return data.id

    @wrap_aiohttp_errors
    async def update_integration(self, integration: JiraIntegrationModel):
        url = f"{self._base_path}/{integration.id}"
        json_data = integration.dict(exclude={"id"})
        response = await self._session.put(url, json=json_data)
        await self.parse_response_no_model(response)

    @wrap_aiohttp_errors
    async def delete_integration(self, integration_id: str):
        response = await self._session.delete(f"{self._base_path}/{integration_id}")
        await self.parse_response_no_model(response)

    @wrap_aiohttp_errors
    async def get_integration(self, integration_id: str):
        response = await self._session.get(f"{self._base_path}/{integration_id}")
        return await self.parse_response(response, JiraIntegrationModel)
