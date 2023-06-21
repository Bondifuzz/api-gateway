from pydantic import BaseModel, Field
from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.api.utils import max_length
from api_gateway.app.utils import (
    BaseModelPartial,
)
from typing import Optional, List


class CreateProjectRequestModel(BaseModel):
    name: str = Field(**max_length(C_MAX_PROJECT_NAME_LENGTH))
    description: str = Field(max_length=C_MAX_DESCRIPTION_LENGTH)
    pool_id: str


class ProjectResponseModel(BaseModel):
    id: str
    name: str
    description: str
    erasure_date: Optional[str]
    pool_id: Optional[str]


class UserTrashbinEmptyResponseModel(BaseModel):
    erased_projects: int


class UpdateProjectRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_PROJECT_NAME_LENGTH))
    description: Optional[str] = Field(max_length=C_MAX_DESCRIPTION_LENGTH)
    pool_id: Optional[str]


class ListProjectsResponseModel(BasePaginatorResponseModel):
    items: List[ProjectResponseModel]

