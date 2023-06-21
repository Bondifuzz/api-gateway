import secrets

import jwt
from pydantic import BaseModel, Field, ValidationError

from api_gateway.app.settings import AppSettings
from api_gateway.app.utils import future_seconds

BFP_ALGORITHM = "HS256"
BFP_AUDIENCE = "csrf-protection"


class CSRFToken(BaseModel):

    user_id: str = Field(alias="sub")
    """ Subject: username (LOGIN) """

    nonce: str = Field(alias="jti")
    """ Unique identifier for the JWT (NONCE) """

    purpose: str = Field(BFP_AUDIENCE, alias="aud")
    """ Identifies the JWT is intended for CSRF protection"""

    expires: int = Field(alias="exp")
    """ Expiration date for this token """

    class Config:
        allow_population_by_field_name = True


class CSRFTokenInvalid(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid CSRF token")


class CSRFTokenManager:

    _secret_key: str
    _exp_seconds: int

    def __init__(self, settings: AppSettings) -> None:
        self._secret_key = settings.csrf_protection.secret_key
        self._exp_seconds = settings.csrf_protection.token_exp_seconds

    def create_csrf_token(self, user_id: str):

        token = CSRFToken(
            sub=user_id,
            jti=secrets.token_hex(),
            exp=future_seconds(self._exp_seconds),
        )

        return jwt.encode(
            key=self._secret_key,
            algorithm=BFP_ALGORITHM,
            payload=token.dict(by_alias=True),
        )

    def parse_csrf_token(self, csrf_token_jwt: str):

        try:
            data = jwt.decode(
                key=self._secret_key,
                algorithms=[BFP_ALGORITHM],
                audience=BFP_AUDIENCE,
                jwt=csrf_token_jwt,
            )

            token = CSRFToken.parse_obj(data)

        except (jwt.InvalidTokenError, ValidationError) as e:
            raise CSRFTokenInvalid() from e

        return token
