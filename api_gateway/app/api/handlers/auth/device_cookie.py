import secrets
from typing import Optional

import jwt
from pydantic import BaseModel, Field, ValidationError

from api_gateway.app.settings import AppSettings

BFP_ALGORITHM = "HS256"
BFP_AUDIENCE = "brute-force-protection"


class DeviceCookie(BaseModel):

    username: str = Field(alias="sub")
    """ Subject: username (LOGIN) """

    nonce: str = Field(alias="jti")
    """ Unique identifier for the JWT (NONCE) """

    purpose: str = Field(BFP_AUDIENCE, alias="aud")
    """ Identifies the JWT is intended for bruteforce protection"""

    class Config:
        allow_population_by_field_name = True


class InvalidDeviceCookie(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid device cookie")


UNTRUSTED_AUTH = "untrusted"


class DeviceCookieManager:

    _secret_key: str

    def __init__(self, settings: AppSettings) -> None:
        self._secret_key = settings.bfp.secret_key

    def create_device_cookie(self, username: str):

        nonce = secrets.token_hex()
        dc = DeviceCookie(sub=username, jti=nonce)

        return jwt.encode(
            key=self._secret_key,
            algorithm=BFP_ALGORITHM,
            payload=dc.dict(by_alias=True),
        )

    def parse_device_cookie(self, device_cookie_jwt: str):

        try:
            data = jwt.decode(
                key=self._secret_key,
                algorithms=[BFP_ALGORITHM],
                audience=BFP_AUDIENCE,
                jwt=device_cookie_jwt,
            )

            dc = DeviceCookie.parse_obj(data)

        except (jwt.DecodeError, ValidationError) as e:
            raise InvalidDeviceCookie() from e

        return dc

    def ensure_device_cookie(self, username: str, jwt: Optional[str] = None):

        if jwt is None:
            return DeviceCookie(
                username=username,
                nonce=UNTRUSTED_AUTH,
            )

        return self.parse_device_cookie(jwt)

    def is_trusted_cookie(self, device_cookie: DeviceCookie):
        return device_cookie.nonce != UNTRUSTED_AUTH
