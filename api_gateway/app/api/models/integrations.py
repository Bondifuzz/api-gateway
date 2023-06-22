from typing import List, Optional, Union

from pydantic import AnyHttpUrl, BaseModel, Field, validator

from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.api.utils import max_length
from api_gateway.app.database.orm import ORMIntegrationStatus, ORMIntegrationTypeID
from api_gateway.app.utils import BaseModelPartial


class JiraIntegrationConfigRequestModel(BaseModel):
    url: AnyHttpUrl
    project: str = Field(..., **max_length(C_MAX_PROJECT_NAME_LENGTH))
    username: str = Field(..., **max_length(C_MAX_USERNAME_LENGTH))
    password: str = Field(..., **max_length(C_MAX_PASSWORD_LENGTH))
    issue_type: str
    priority: Optional[str]


class JiraIntegrationConfigResponseModel(BaseModel):
    id: str
    url: str
    project: str
    username: str
    password: str
    issue_type: str
    priority: Optional[str]


class YoutrackIntegrationConfigRequestModel(BaseModel):
    url: AnyHttpUrl
    token: str = Field(..., **max_length(C_MAX_PASSWORD_LENGTH))
    project: str = Field(..., **max_length(C_MAX_PROJECT_NAME_LENGTH))


class YoutrackIntegrationConfigResponseModel(BaseModel):
    id: str
    url: str
    token: str
    project: str


class AnotherIntegrationConfigRequestModel(BaseModel):
    pass


class AnotherIntegrationConfigResponseModel(BaseModel):
    pass


IntegrationConfig = Union[
    JiraIntegrationConfigRequestModel,
    YoutrackIntegrationConfigRequestModel,
    AnotherIntegrationConfigRequestModel,
]


def check_integration_config(
    integration_type: Optional[ORMIntegrationTypeID],
    integration_config: dict,
):

    if not integration_type:
        raise ValueError("Failed to get integration type")

    if integration_type == ORMIntegrationTypeID.jira:
        return JiraIntegrationConfigRequestModel.parse_obj(integration_config)
    elif integration_type == ORMIntegrationTypeID.youtrack:
        return YoutrackIntegrationConfigRequestModel.parse_obj(integration_config)
    else:
        # TODO: remove this when more integrations will be supported
        raise ValueError("Invalid config")
    # else:
    #     return EmailIntegration.parse_obj(value)


class CreateIntegrationRequestModel(BaseModel):

    name: str
    """ Name of integration. Must be created by user """

    type: ORMIntegrationTypeID
    """ Type of bug tracker to integrate with """

    config: IntegrationConfig
    """ Bug tracker integration essentials """

    @validator("config", pre=True)
    def check_config(cls, value, values: dict):
        return check_integration_config(values.get("type"), value)


class IntegrationResponseModel(BaseModel):

    id: str
    """ Unique identifier of integration """

    name: str
    """ Name of integration. Must be created by user """

    type: ORMIntegrationTypeID
    """ Type of integration: jira, youtrack, mail, etc... """

    status: ORMIntegrationStatus
    """ Integration status: whether works or not """

    enabled: bool
    """ When set, integration with bug tracker is enabled """

    num_undelivered: int
    """ Count of reports which were not delivered to bug tracker """

    last_error: Optional[str]
    """ Last error caused integration to fail """


class UpdateIntegrationRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_INTEGRATION_NAME_LENGTH))
    enabled: Optional[bool]


class UpdateIntegrationConfigRequestModel(BaseModel):

    type: ORMIntegrationTypeID
    """ Type of bug tracker integration """

    config: IntegrationConfig
    """ Bug tracker integration essentials """

    @validator("config", pre=True)
    def check_config(cls, value, values: dict):
        return check_integration_config(values.get("type"), value)


class ListIntegrationsResponseModel(BasePaginatorResponseModel):
    items: List[IntegrationResponseModel]
