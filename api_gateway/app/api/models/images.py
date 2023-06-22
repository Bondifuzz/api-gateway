from typing import List, Optional

from pydantic import BaseModel, Field

from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.api.utils import max_length
from api_gateway.app.database.orm import ORMEngineID
from api_gateway.app.utils import BaseModelPartial


class CreateImageRequestModel(BaseModel):
    name: str = Field(**max_length(C_MAX_IMAGE_NAME_LENGTH))
    description: str = Field(**max_length(C_MAX_DESCRIPTION_LENGTH))
    engines: List[ORMEngineID] = Field(list())


class ImageResponseModel(BaseModel):
    id: str
    name: str
    description: str
    engines: List[ORMEngineID]
    status: str
    project_id: Optional[str]


class UpdateImageRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_IMAGE_NAME_LENGTH))
    description: Optional[str] = Field(**max_length(C_MAX_DESCRIPTION_LENGTH))


class ListImagesResponseModel(BasePaginatorResponseModel):
    items: List[ImageResponseModel]
