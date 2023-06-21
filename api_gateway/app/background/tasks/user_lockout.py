import random
from collections import defaultdict
from typing import DefaultDict, Tuple

from api_gateway.app.database import IDatabase
from api_gateway.app.database.orm import ORMDeviceCookie
from api_gateway.app.settings import AppSettings

from ..bg_task import BackgroundTask


class UserLockoutCleaner(BackgroundTask):

    _db: IDatabase

    def __init__(self, settings: AppSettings, db: IDatabase) -> None:
        name = self.__class__.__name__
        wait_interval = settings.bfp.cleanup_interval_sec
        super().__init__(name, wait_interval)
        self._db = db

    async def _task_coro(self):
        await self._db.lockout.remove_expired()
        self._logger.debug("User lockout list cleanup is done")


class FailedLoginCounter(BackgroundTask):

    _TKey = Tuple[str, str]
    _login_attempts: DefaultDict[_TKey, int]
    _max_failed_logins: int

    def __init__(self, settings: AppSettings) -> None:
        name = self.__class__.__name__
        wait_interval = settings.bfp.lockout_period_sec
        super().__init__(name, wait_interval)

        self._max_failed_logins = settings.bfp.max_failed_logins
        self._login_attempts = defaultdict(int)

    @staticmethod
    def _make_key(dc: ORMDeviceCookie):
        return dc.username, dc.nonce

    def _random_cleanup_if_needed(self, capacity: int):

        if len(self._login_attempts) < capacity:
            return

        items = self._login_attempts.items()
        randbool = lambda: bool(random.getrandbits(1))
        self._login_attempts = {k: v for k, v in items if randbool()}

    def add_failed_login(self, device_cookie: ORMDeviceCookie):
        self._random_cleanup_if_needed(10**5)
        key = self._make_key(device_cookie)
        self._login_attempts[key] += 1

    def is_limit_reached(self, device_cookie) -> bool:
        key = self._make_key(device_cookie)
        return self._login_attempts[key] >= self._max_failed_logins

    async def _task_coro(self):
        self._login_attempts.clear()
        self._logger.debug("User failed login attempts are reset")
