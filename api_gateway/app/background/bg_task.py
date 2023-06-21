import asyncio
import logging
from contextlib import suppress
from typing import Optional

from api_gateway.app.utils import PrefixedLogger

from .abstract import IBackgroundTask


class BackgroundTask(IBackgroundTask):

    _logger: logging.Logger
    _task: Optional[asyncio.Task]
    _wait_interval: int
    _cancel_lock: asyncio.Lock
    _wakeup_event: asyncio.Event
    _name: str

    def __init__(self, name: str, wait_interval: int) -> None:

        self._logger = PrefixedLogger(
            logger=logging.getLogger("bg.tasks"),
            extra={"prefix": f"[{name}]"},
        )

        self._name = name
        self._wait_interval = wait_interval

        self._wakeup_event = asyncio.Event()
        self._cancel_lock = asyncio.Lock()

    @property
    def name(self):
        return self._name

    async def _task_coro(self):
        print("<BackgroundTask> replace my body")

    async def _task_coro_safe_call(self):
        try:
            await self._task_coro()
        except:
            logging.exception("Unhandled exception")

    async def _task_loop(self):

        while True:
            async with self._cancel_lock:
                await self._task_coro_safe_call()

            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._wakeup_event.wait(),
                    self._wait_interval,
                )

            if self._wakeup_event.is_set():
                break

    def start(self):
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(
            self._task_loop(),
        )

    async def stop(self):
        async with self._cancel_lock:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
