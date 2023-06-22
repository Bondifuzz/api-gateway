from typing import List, Optional

from pydantic import BaseModel, Field

from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.database.orm import ORMEngineID, ORMLangID
from api_gateway.app.utils import BaseModelPartial


class CreateEngineRequestModel(BaseModel):
    id: ORMEngineID
    display_name: str
    langs: List[ORMLangID] = Field(list())


class EngineResponseModel(BaseModel):
    id: ORMEngineID
    display_name: str
    langs: List[ORMLangID]


class UpdateEngineRequestModel(BaseModelPartial):
    display_name: Optional[str]


class ListEnginesResponseModel(BasePaginatorResponseModel):
    items: List[EngineResponseModel]
