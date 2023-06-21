import functools
import logging
import random
import string
from datetime import datetime, timedelta, timezone
from enum import Enum
from logging import LoggerAdapter
from typing import Any, Dict, Set, TypeVar

from pydantic import BaseModel, ValidationError, root_validator

from .settings import AppSettings, load_app_settings


class BaseModelPartial(BaseModel):
    _nullable_values: Set[str] = set()

    @root_validator(pre=True)
    def nullable_values_validator(cls, data: Dict[str, Any]):
        for k, v in data.items():
            if v is None and k not in cls._nullable_values:
                raise ValueError(f"{k} can't be null")
        
        if len(data) == 0:
            raise ValueError("At least one field must be set")
        
        return data
    

TBaseModelPartial = TypeVar("TBaseModelPartial", bound=BaseModelPartial)
def nullable_values(*values: str):
    def decorator(cls: TBaseModelPartial):
        cls._nullable_values.update(list(values))
        return cls
    return decorator


class ObjectRemovalState(str, Enum):

    all = "All"
    """ All objects (any state) """

    visible = "Visible"
    """ Objects accessible by user(Present+TrashBin) """

    present = "Present"
    """ Objects which are present (not deleted) """

    trash_bin = "TrashBin"
    """ Objects in trashbin (not expired erasure_date) """

    erasing = "Erasing"
    """ Object with expired erasure_date """


def testing_only(func):

    """Provides decorator, which forbids
    calling dangerous functions in production"""

    try:
        settings = load_app_settings()
        is_danger = settings.environment.name == "prod"

    except ValidationError:
        logging.warning("Settings missing or invalid. Using environment 'prod'")
        is_danger = True

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):

        if is_danger:
            err = f"Function '{func.__name__}' is allowed to call only in testing mode"
            help = "Please, check 'ENVIRONMENT' variable is not set to 'prod'"
            raise RuntimeError(f"{err}. {help}")

        return await func(*args, **kwargs)

    return wrapper


def datetime_utcnow() -> datetime:
    # XXX: Do not use utcnow(). It's confusing and potentially dangerous
    # https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow
    # https://blog.ganssle.io/articles/2019/11/utcnow.html
    return datetime.now(tz=timezone.utc)


def rfc3339_now() -> str:
    return datetime_utcnow().replace(microsecond=0).isoformat() + "Z"


def rfc3339_add(date: datetime, seconds: int) -> str:
    return (date.replace(microsecond=0) + timedelta(seconds=seconds)).isoformat() + "Z"


def future_seconds(seconds: int) -> int:
    utcnow = datetime_utcnow().replace(microsecond=0)
    return int((utcnow + timedelta(seconds=seconds)).timestamp())


def rfc3339_fut(seconds: int) -> str:
    utcnow = datetime_utcnow().replace(microsecond=0)
    return (utcnow + timedelta(seconds=seconds)).isoformat() + "Z"


# returns True if date in past or now else - False
def rfc3339_expired(date: str) -> bool:
    assert date.endswith("Z")
    tmp = datetime.fromisoformat(date[:-1])
    return tmp <= datetime_utcnow()


def gen_unique_identifier(n=6) -> str:
    timestamp = str(int(datetime_utcnow().replace(microsecond=0).timestamp()))
    rand = "".join(random.choice(string.ascii_lowercase) for _ in range(n))
    return f"{timestamp}-{rand}"


class PrefixedLogger(LoggerAdapter):
    def process(self, msg, kwargs):
        return f"{self.extra['prefix']} {msg}", kwargs


from pydantic import BaseModel


def _default(obj):
    if isinstance(obj, BaseModel):
        return obj.dict()
    raise TypeError()


try:
    import orjson  # type: ignore

    from fastapi.responses import ORJSONResponse as JSONResponse  # noqa

    json_dumps = lambda x: orjson.dumps(x, _default).decode()
    json_loads = lambda x: orjson.loads(x)

except ModuleNotFoundError:

    import json  # isort: skip
    from fastapi.responses import JSONResponse  # noqa

    json_dumps = lambda x: json.dumps(x, default=_default)
    json_loads = lambda x: json.loads(x)
