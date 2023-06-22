from typing import List, Optional

from pydantic import BaseModel

from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.database.orm import ORMIntegrationTypeID
from api_gateway.app.utils import BaseModelPartial


class CreateIntegrationTypeRequestModel(BaseModel):
    id: ORMIntegrationTypeID
    display_name: str
    twoway: bool


class IntegrationTypeResponseModel(BaseModel):
    id: ORMIntegrationTypeID
    display_name: str
    twoway: bool


class UpdateIntegrationTypeRequestModel(BaseModelPartial):
    display_name: Optional[str]
    twoway: Optional[bool]


class ListIntegrationTypesResponseModel(BasePaginatorResponseModel):
    items: List[IntegrationTypeResponseModel]
