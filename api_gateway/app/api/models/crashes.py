from pydantic import BaseModel
from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from typing import List


class CrashResponseModel(BaseModel):

    id: str
    """ Unique record id """

    created: str
    """ Date when crash was retrieved """

    preview: str
    """ Chunk of crash input to preview (base64-encoded) """

    type: str
    """ Type of crash: crash, oom, timeout, leak, etc.. """

    brief: str
    """ Short description for crash """

    output: str
    """ Crash output (long multiline text) """

    reproduced: bool
    """ True if crash was reproduced, else otherwise """

    archived: bool
    """ True if crash was moved to archive(marked as resolved) """

    duplicate_count: int
    """ Count of similar crashes found """


class ListCrashesResponseModel(BasePaginatorResponseModel):
    items: List[CrashResponseModel]


class PutArchivedCrashRequestModel(BaseModel):
    archived: bool

