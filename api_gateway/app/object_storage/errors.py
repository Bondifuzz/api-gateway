import functools

from aiohttp.client_exceptions import ClientConnectionError
from botocore.exceptions import ClientError


class ObjectStorageError(Exception):
    pass


class ObjectNotFoundError(ObjectStorageError):
    pass


class UploadLimitError(ObjectStorageError):
    pass


def maybe_unknown_error(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            res = await func(*args, **kwargs)
        except (ClientError, ClientConnectionError) as e:
            raise ObjectStorageError(str(e)) from e

        return res

    return wrapper


def maybe_not_found(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            res = await func(*args, **kwargs)
        except ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                raise ObjectNotFoundError() from e
            raise

        return res

    return wrapper
