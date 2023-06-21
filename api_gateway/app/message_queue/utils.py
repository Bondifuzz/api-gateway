from __future__ import annotations

from mqtransport.participants import Consumer as BaseConsumer
from mqtransport.participants import Producer as BaseProducer

from api_gateway.app.utils import PrefixedLogger


class Consumer(BaseConsumer):
    def __init__(self):
        super().__init__()
        extra = {"prefix": f"[{self.__class__.__name__}]"}
        self._logger = PrefixedLogger(self._logger, extra)


class Producer(BaseProducer):
    def __init__(self):
        super().__init__()
        extra = {"prefix": f"[{self.__class__.__name__}]"}
        self._logger = PrefixedLogger(self._logger, extra)
