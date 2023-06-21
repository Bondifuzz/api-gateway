import logging
from typing import Dict

from .abstract import IBackgroundTask


class BackgroundTaskManager:

    _tasks: Dict[str, IBackgroundTask]

    def __init__(self) -> None:
        self._logger = logging.getLogger("bg.taskmgr")
        self._tasks = {}

    def add_task(self, task: IBackgroundTask):
        assert task.name not in self._tasks, "Task already exists"

        self._tasks[task.name] = task
        self._logger.info(f"Added task '{task.name}'")

    def get_task(self, task_name: str):
        return self._tasks[task_name]

    def start_tasks(self):

        for task in self._tasks.values():
            task.start()

        self._logger.info("Background tasks are started'")

    async def stop_tasks(self):

        for task in self._tasks.values():
            await task.stop()

        self._logger.info("Background tasks are stopped'")
