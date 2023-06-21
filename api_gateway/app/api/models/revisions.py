from pydantic import BaseModel, Field
from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.api.utils import max_length
from api_gateway.app.utils import (
    BaseModelPartial,
)
from typing import Optional, List


class CreateRevisionRequestModel(BaseModel):
    name: Optional[str] = Field(**max_length(C_MAX_REVISION_NAME_LENGTH))
    description: str = Field(max_length=C_MAX_DESCRIPTION_LENGTH)
    image_id: str = Field(**max_length(C_MAX_DATABASE_KEY_LENGTH))
    cpu_usage: int = Field(gt=0)
    ram_usage: int = Field(gt=0)
    tmpfs_size: int = Field(gt=0)


class RevisionResponseModel(BaseModel):
    id: str
    name: str
    description: str
    binaries: dict
    seeds: dict
    config: dict
    status: str
    health: str
    feedback: Optional[dict] = None
    cpu_usage: int
    ram_usage: int
    tmpfs_size: int
    last_start_date: Optional[str]
    last_stop_date: Optional[str]
    image_id: str
    created: str
    erasure_date: Optional[str] = Field(None)


class CopyCorpusRequestModel(BaseModel):
    src_rev_id: str


class SetActiveRevisionRequestModel(BaseModel):
    revision_id: str


class UpdateRevisionInfoRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_REVISION_NAME_LENGTH))
    description: Optional[str] = Field(max_length=C_MAX_DESCRIPTION_LENGTH)


class UpdateRevisionResourcesRequestModel(BaseModelPartial):
    cpu_usage: Optional[int] = Field(gt=0)
    ram_usage: Optional[int] = Field(gt=0)
    tmpfs_size: Optional[int] = Field(gt=0)


class ListRevisionsResponseModel(BasePaginatorResponseModel):
    items: List[RevisionResponseModel]

