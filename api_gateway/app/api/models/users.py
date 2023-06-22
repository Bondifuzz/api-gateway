from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from api_gateway.app.api.utils import max_length
from api_gateway.app.utils import BaseModelPartial


class CreateUserRequestModel(BaseModel):
    name: str = Field(**max_length(C_MAX_USERNAME_LENGTH))
    password: str = Field(**max_length(C_MAX_PASSWORD_LENGTH))
    display_name: str = Field(**max_length(C_MAX_USERNAME_LENGTH))
    email: EmailStr
    is_admin: bool


class UserResponseModel(BaseModel):
    id: str
    name: str
    display_name: str
    is_confirmed: bool
    is_disabled: bool
    erasure_date: Optional[str]
    is_admin: bool
    is_system: bool
    email: str


class ListUsersResponseModel(BasePaginatorResponseModel):
    items: List[UserResponseModel]


class AdminUpdateUserRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_USERNAME_LENGTH))
    display_name: Optional[str] = Field(**max_length(C_MAX_USERNAME_LENGTH))
    password: Optional[str] = Field(**max_length(C_MAX_PASSWORD_LENGTH))
    email: Optional[EmailStr]
    is_confirmed: Optional[bool]
    is_disabled: Optional[bool]


class UpdateUserRequestModel(BaseModelPartial):
    name: Optional[str] = Field(**max_length(C_MAX_USERNAME_LENGTH))
    display_name: Optional[str] = Field(**max_length(C_MAX_USERNAME_LENGTH))
    email: Optional[EmailStr]

    current_password: Optional[str] = Field(**max_length(C_MAX_PASSWORD_LENGTH))
    new_password: Optional[str] = Field(**max_length(C_MAX_PASSWORD_LENGTH))
