from __future__ import annotations

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, validator

from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.utils import normalize_date
from api_gateway.app.utils import BaseModelPartial, nullable_values


class CreatePoolRequestModel(BaseModel):
    name: str
    description: str
    user_id: Optional[str] = Field(...)  # Optional but Required
    node_group: Union[LocalNodeGroupModel, CloudNodeGroupModel]
    exp_date: Optional[str]


class PoolResponseModel(BaseModel):
    id: str
    name: str
    description: str
    user_id: Optional[str]
    exp_date: Optional[str]
    node_group: Union[LocalNodeGroupModel, CloudNodeGroupModel]
    operation: Optional[PoolOperation]
    health: PoolHealth
    created_at: str
    resources: PoolResources


@nullable_values("exp_date")
class AdminUpdatePoolInfoRequestModel(BaseModelPartial):
    name: Optional[str]
    description: Optional[str]
    exp_date: Optional[str]

    @validator("exp_date")
    def validate_date(value: Optional[str]):
        return normalize_date(value)


class UpdatePoolInfoRequestModel(BaseModelPartial):
    name: Optional[str]
    description: Optional[str]


class ListPoolsResponseModel(BasePaginatorResponseModel):
    items: List[PoolResponseModel]


class CloudNodeGroupModel(BaseModel):
    node_cpu: int
    node_ram: int
    node_count: int


class LocalNodeGroupModel(BaseModel):
    node_count: int


class PoolOperationType(str, Enum):
    create = "Create"
    update = "Update"
    delete = "Delete"


class PoolOperation(BaseModel):
    type: PoolOperationType
    scheduled_for: str
    yc_operation_id: Optional[str]
    error_msg: Optional[str]


class PoolHealth(str, Enum):
    ok = "Ok"
    warning = "Warning"
    error = "Error"


class PoolNode(BaseModel):
    name: str
    cpu: int
    ram: int


class PoolResources(BaseModel):
    cpu_total: int
    ram_total: int
    nodes_total: int

    cpu_avail: int
    ram_avail: int
    nodes_avail: int  # TODO:

    fuzzer_max_cpu: int
    fuzzer_max_ram: int

    nodes: List[PoolNode]


CreatePoolRequestModel.update_forward_refs()
PoolResponseModel.update_forward_refs()
