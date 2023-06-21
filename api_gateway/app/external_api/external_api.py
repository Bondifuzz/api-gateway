from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from aiohttp import ClientSession

from api_gateway.app.external_api.interfaces.base import ExternalAPIBase

from .interfaces.jira_reporter import JiraReporterAPI
from .interfaces.pool_manager import PoolManagerAPI
from .interfaces.youtrack_reporter import YoutrackReporterAPI

if TYPE_CHECKING:
    from api_gateway.app.settings import AppSettings


class ExternalAPI:

    _pool_mgr: PoolManagerAPI
    _jira_reporter: JiraReporterAPI
    _yt_reporter: YoutrackReporterAPI

    _logger: logging.Logger
    _session: ClientSession
    _is_closed: bool

    @property
    def pool_mgr(self):
        return self._pool_mgr

    @property
    def jira_reporter(self):
        return self._jira_reporter

    @property
    def yt_reporter(self):
        return self._yt_reporter

    async def _init(self, settings: AppSettings):
        self._is_closed = True
        self._logger = logging.getLogger("api.external")
        self._pool_mgr = PoolManagerAPI(settings)
        self._jira_reporter = JiraReporterAPI(settings)
        self._yt_reporter = YoutrackReporterAPI(settings)
        self._is_closed = False

    @staticmethod
    async def create(settings):
        _self = ExternalAPI()
        await _self._init(settings)
        return _self

    async def close(self):

        assert not self._is_closed, "External API sessions have been already closed"

        sessions: List[ExternalAPIBase] = [
            self._pool_mgr,
            self._jira_reporter,
            self._yt_reporter,
        ]

        for session in sessions:
            await session.close()

        self._is_closed = True

    def __del__(self):
        if not self._is_closed:
            self._logger.error("External API sessions have not been closed")
