from enum import Enum
from typing import Any, List

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from api_gateway.app.utils import ObjectRemovalState


class QueryBaseModel(BaseModel):
    """
    Handle ValueError/ValidationError/... raised from
    @validator and @root_validator(FastAPI doesn't handle it by default)
    Solution: Convert pydantic ValidationError to fastapi RequestValidationError
    """

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            raise RequestValidationError(e.raw_errors) from e


class DeleteActions(str, Enum):
    delete = "Delete"
    """ Move object to trashbin with normal expiration time """

    restore = "Restore"
    """ Move object from trashbin """

    erase = "Erase"
    """ Move object to trashbin with zero expiration time """


class UserObjectRemovalState(str, Enum):

    present = "Present"
    """ Objects which are present (not deleted) """

    trash_bin = "TrashBin"
    """ Objects in trashbin (not expired erasure_date) """

    all = "All"
    """ All objects accessible by user """

    def to_internal(self) -> ObjectRemovalState:
        if self == UserObjectRemovalState.present:
            return ObjectRemovalState.present
        elif self == UserObjectRemovalState.trash_bin:
            return ObjectRemovalState.trash_bin
        else:  # self == UserObjectRemovalState.all:
            return ObjectRemovalState.visible


class ItemCountResponseModel(BaseModel):
    pg_size: int
    pg_total: int
    cnt_total: int


class BasePaginatorResponseModel(BaseModel):
    pg_num: int
    pg_size: int
    # TODO: add offset
    items: List[Any]
