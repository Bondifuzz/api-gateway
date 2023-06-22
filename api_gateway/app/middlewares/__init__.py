from typing import Callable

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from api_gateway.app.settings import AppSettings

from .csrf import csrf_protection_middleware
from .react import react_middleware


def add_middleware(app: FastAPI, func: Callable):
    app.add_middleware(BaseHTTPMiddleware, dispatch=func)


def register_middlewares(app: FastAPI, settings: AppSettings):
    add_middleware(app, react_middleware)
    if settings.csrf_protection.enabled:
        add_middleware(app, csrf_protection_middleware)


__all__ = ["register_middlewares"]
