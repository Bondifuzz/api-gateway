from abc import ABCMeta, abstractmethod


class IBackgroundTask(metaclass=ABCMeta):
    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass
