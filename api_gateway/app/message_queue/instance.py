from __future__ import annotations

from typing import TYPE_CHECKING

from mqtransport import MQApp, SQSApp

from .crash_analyzer import MC_DuplicateCrashFound, MC_UniqueCrashFound
from .jira_reporter import (
    MC_JiraIntegrationResult,
    MC_JiraReportUndelivered,
    MP_JiraDuplicateCrashFound,
    MP_JiraUniqueCrashFound,
)
from .pool_manager import MC_PoolDeleted
from .scheduler import (
    MC_FuzzerRunResult,
    MC_FuzzerStatusChanged,
    MC_FuzzerStopped,
    MC_FuzzerVerified,
    MP_StartFuzzer,
    MP_StopFuzzer,
    MP_StopFuzzersInPool,
    MP_UpdateFuzzer,
)
from .youtrack_reporter import (
    MC_YoutrackIntegrationResult,
    MC_YoutrackReportUndelivered,
    MP_YoutrackDuplicateCrashFound,
    MP_YoutrackUniqueCrashFound,
)

if TYPE_CHECKING:
    from asyncio import Queue

    from mqtransport.channel import ConsumingChannel, ProducingChannel

    from api_gateway.app.database import IDatabase
    from api_gateway.app.settings import AppSettings
    from fastapi import FastAPI


class Producers:
    sch_start_fuzzer: MP_StartFuzzer
    sch_update_fuzzer: MP_UpdateFuzzer
    sch_stop_fuzzer: MP_StopFuzzer
    sch_stop_pool_fuzzers: MP_StopFuzzersInPool
    jr_unique_crash: MP_JiraUniqueCrashFound
    jr_duplicate_crash: MP_JiraDuplicateCrashFound
    yt_unique_crash: MP_YoutrackUniqueCrashFound
    yt_duplicate_crash: MP_YoutrackDuplicateCrashFound


class MQAppState:
    fastapi: FastAPI
    settings: AppSettings
    producers: Producers
    event_queue: Queue
    db: IDatabase

    def __init__(self):
        self.producers = Producers()


class MQAppInitializer:

    _settings: AppSettings
    _app: MQApp

    _ich_api_gateway: ConsumingChannel
    _och_scheduler: ProducingChannel
    _och_crash_analyzer: ProducingChannel
    _och_jira_reporter: ProducingChannel
    _och_youtrack_reporter: ProducingChannel

    @property
    def app(self):
        return self._app

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._app = None

    async def do_init(self):

        self._app = await self._create_mq_app()
        self._app.state = MQAppState()

        try:
            await self._app.ping()
            await self._configure_channels()

        except:
            await self._app.shutdown()
            raise

    async def _create_mq_app(self):

        mq_broker = self._settings.message_queue.broker.lower()
        mq_settings = self._settings.message_queue

        if mq_broker == "sqs":
            return await SQSApp.create(
                mq_settings.username,
                mq_settings.password,
                mq_settings.region,
                mq_settings.url,
            )

        raise ValueError(f"Unsupported message broker: {mq_broker}")

    async def _create_own_channel(self):
        queues = self._settings.message_queue.queues
        ich = await self._app.create_consuming_channel(queues.api_gateway)
        dlq = await self._app.create_producing_channel(queues.dlq)
        ich.use_dead_letter_queue(dlq)
        self._ich_api_gateway = ich

    async def _create_other_channels(self):
        queues = self._settings.message_queue.queues
        och1 = await self._app.create_producing_channel(queues.scheduler)
        och2 = await self._app.create_producing_channel(queues.jira_reporter)
        och3 = await self._app.create_producing_channel(queues.youtrack_reporter)
        self._och_scheduler = och1
        self._och_jira_reporter = och2
        self._och_youtrack_reporter = och3

    def _setup_jira_reporter_communication(self):

        state: MQAppState = self.app.state
        ich = self._ich_api_gateway
        och = self._och_jira_reporter

        # Incoming messages
        ich.add_consumer(MC_JiraIntegrationResult())
        ich.add_consumer(MC_JiraReportUndelivered())

        # Outcoming messages
        producers = state.producers
        producers.jr_unique_crash = MP_JiraUniqueCrashFound()
        producers.jr_duplicate_crash = MP_JiraDuplicateCrashFound()

        och.add_producer(producers.jr_unique_crash)
        och.add_producer(producers.jr_duplicate_crash)

    def _setup_youtrack_reporter_communication(self):

        state: MQAppState = self.app.state
        ich = self._ich_api_gateway
        och = self._och_youtrack_reporter

        # Incoming messages
        ich.add_consumer(MC_YoutrackIntegrationResult())
        ich.add_consumer(MC_YoutrackReportUndelivered())

        # Outcoming messages
        producers = state.producers
        producers.yt_unique_crash = MP_YoutrackUniqueCrashFound()
        producers.yt_duplicate_crash = MP_YoutrackDuplicateCrashFound()

        och.add_producer(producers.yt_unique_crash)
        och.add_producer(producers.yt_duplicate_crash)

    def _setup_crash_analyzer_communication(self):
        self._ich_api_gateway.add_consumer(MC_UniqueCrashFound())
        self._ich_api_gateway.add_consumer(MC_DuplicateCrashFound())

    def _setup_scheduler_communication(self):

        state: MQAppState = self.app.state
        ich = self._ich_api_gateway
        och = self._och_scheduler

        # Incoming messages
        ich.add_consumer(MC_FuzzerVerified())
        ich.add_consumer(MC_FuzzerStatusChanged())
        ich.add_consumer(MC_FuzzerRunResult())
        ich.add_consumer(MC_FuzzerStopped())

        # Outcoming messages
        producers = state.producers
        producers.sch_start_fuzzer = MP_StartFuzzer()
        producers.sch_update_fuzzer = MP_UpdateFuzzer()
        producers.sch_stop_fuzzer = MP_StopFuzzer()
        producers.sch_stop_pool_fuzzers = MP_StopFuzzersInPool()

        och.add_producer(producers.sch_start_fuzzer)
        och.add_producer(producers.sch_update_fuzzer)
        och.add_producer(producers.sch_stop_fuzzer)
        och.add_producer(producers.sch_stop_pool_fuzzers)

    def _setup_pool_manager_communication(self):
        ich = self._ich_api_gateway
        ich.add_consumer(MC_PoolDeleted())

    async def _configure_channels(self):
        await self._create_own_channel()
        await self._create_other_channels()
        self._setup_crash_analyzer_communication()
        self._setup_jira_reporter_communication()
        self._setup_youtrack_reporter_communication()
        self._setup_pool_manager_communication()
        self._setup_scheduler_communication()


async def mq_init(settings: AppSettings):
    initializer = MQAppInitializer(settings)
    await initializer.do_init()
    return initializer.app
