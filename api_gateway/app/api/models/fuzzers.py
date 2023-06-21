from pydantic import BaseModel, Field
from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.api.models.revisions import RevisionResponseModel
from api_gateway.app.api.utils import max_length
from api_gateway.app.database.orm import ORMEngineID, ORMLangID
from api_gateway.app.utils import (
    BaseModelPartial,
)
from typing import Optional, List


class CreateFuzzerRequestModel(BaseModel):
    name: str = Field(**max_length(C_MAX_FUZZER_NAME_LENGTH))
    description: str = Field(max_length=C_MAX_DESCRIPTION_LENGTH)
    engine: ORMEngineID
    lang: ORMLangID
    ci_integration: bool


class FuzzerResponseModel(BaseModel):
    id: str
    name: str
    description: str
    engine: ORMEngineID
    lang: ORMLangID
    ci_integration: bool
    erasure_date: Optional[str]
    active_revision: Optional[RevisionResponseModel]


class ListFuzzersResponseModel(BasePaginatorResponseModel):
    items: List[FuzzerResponseModel]


class ProjectTrashbinEmptyResponseModel(BaseModel):
    erased_fuzzers: int
    erased_revisions: int


class UpdateFuzzerRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_FUZZER_NAME_LENGTH))
    description: Optional[str] = Field(max_length=C_MAX_DESCRIPTION_LENGTH)

