from __future__ import annotations

import functools

from aiohttp import ClientError

from .errors import EAPIClientError


def wrap_aiohttp_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
        except ClientError as e:
            raise EAPIClientError(e) from e
        return result

    return wrapper
