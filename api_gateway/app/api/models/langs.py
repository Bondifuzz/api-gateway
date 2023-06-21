from pydantic import BaseModel
from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.database.orm import ORMLangID
from api_gateway.app.utils import (
    BaseModelPartial,
)
from typing import Optional, List


class CreateLangRequestModel(BaseModel):
    id: ORMLangID
    display_name: str


class LangResponseModel(BaseModel):
    id: ORMLangID
    display_name: str


class UpdateLangRequestModel(BaseModelPartial):
    display_name: Optional[str]


class ListLangsResponseModel(BasePaginatorResponseModel):
    items: List[LangResponseModel]

