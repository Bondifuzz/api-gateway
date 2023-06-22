from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ListResultModel(BaseModel):
    pg_num: int
    pg_size: int
    items: list


class JiraIntegrationModel(BaseModel):
    id: Optional[str]
    url: str
    project: str
    username: str
    password: str
    issue_type: str
    priority: Optional[str]
    update_rev: str


class YoutrackIntegrationModel(BaseModel):
    id: Optional[str]
    url: str
    token: str
    project: str
    update_rev: str
