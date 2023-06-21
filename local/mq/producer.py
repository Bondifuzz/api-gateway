from __future__ import annotations
from base64 import b64encode
from typing import Optional
from datetime import date, datetime, timezone
import logging
import asyncio

from pydantic import BaseModel
from mqtransport import MQApp, SQSApp
from mqtransport.participants import Producer
from settings import AppSettings, load_app_settings

USER_ID = "46709"
PROJECT_ID = "62131"
FUZZER_ID = "62170"
REVISION_ID = "81029"
IMAGE_ID = "80312"
CONFIG_ID = "89221"
UPDATE_REV = "1646497096-dead"


class MP_JiraReportUndelivered(Producer):

    """
    Handle notification from jira reporter about undelivered reports
    """

    name = "jira-reporter.reports.undelivered"

    class Model(BaseModel):

        config_id: str
        """ Unique config id used to find integration """

        error: str
        """ Last error caused integration to fail """


class MP_JiraIntegrationStatus(Producer):

    """
    Handle notification from jira reporter about integration status
    """

    name = "jira-reporter.integrations.result"

    class Model(BaseModel):

        config_id: str
        """ Unique config id used to find integration """

        error: Optional[str]
        """ Last error caused integration to fail """

        update_rev: str
        """ Update revision. Used to filter outdated messages """


class MP_JiraUniqueCrashFound(Producer):

    name = "crash-analyzer.crashes.unique"

    class Model(BaseModel):

        created: str
        """ Date when crash was retrieved """

        fuzzer_id: str
        """ Id of fuzzer which statistics belongs to """

        fuzzer_rev: str
        """ Id of revision which statistics belongs to """

        preview: str
        """ Chunk of crash input to preview (base64-encoded) """

        brief: str
        """ Short descriptions for crash """

        input_id: Optional[str]
        """ Identifies crash info in object storage """

        input_hash: str
        """ Unique hash of crash input """

        output: str
        """ Crash output (long multiline text) """

        type: str
        """ Type of crash """


class MP_JiraDuplicateCrashFound(Producer):

    name = "crash-analyzer.crashes.duplicate"

    class Model(BaseModel):

        fuzzer_id: str
        """ Id of fuzzer which statistics belongs to """

        fuzzer_rev: str
        """ Id of revision which statistics belongs to """

        sample_hash: str
        """ Unique hash of crash input """


class StatisticsBase(BaseModel):

    start_time: str
    """ Fuzzer session start time """

    finish_time: str
    """ Fuzzer session finish time """


class StatisticsLibFuzzer(StatisticsBase):

    """Get LibFuzzer statistics from scheduler"""

    execs_per_sec: int
    """ Average count of executions per second """

    edge_cov: int
    """ Edge coverage """

    feature_cov: int
    """ Feature coverage """

    peak_rss: int
    """ Max RAM usage in bytes """

    execs_done: int
    """ Count of fuzzing iterations executed """

    corpus_entries: int
    """ Count of files in merged corpus """

    corpus_size: int
    """ The size of generated corpus in bytes """


class StatisticsAFL(StatisticsBase):

    """Get AFL statistics from scheduler"""

    cycles_done: int
    """queue cycles completed so far"""

    cycles_wo_finds: int
    """number of cycles without any new paths found"""

    execs_done: int
    """number of execve() calls attempted"""

    execs_per_sec: float
    """overall number of execs per second"""

    corpus_count: int
    """total number of entries in the queue"""

    corpus_favored: int
    """number of queue entries that are favored"""

    corpus_found: int
    """number of entries discovered through local fuzzing"""

    corpus_variable: int
    """number of test cases showing variable behavior"""

    stability: float
    """percentage of bitmap bytes that behave consistently"""

    bitmap_cvg: float
    """percentage of edge coverage found in the map so far"""

    slowest_exec_ms: int
    """real time of the slowest execution in ms"""

    peak_rss_mb: int
    """max rss usage reached during fuzzing in MB"""


class MP_FuzzerRunResult(Producer):

    """
    Handle notification from scheduler when fuzzer run finishes successfully.
    """

    name = "scheduler.fuzzer.result"

    class Model(BaseModel):
        fuzzer_id: str
        fuzzer_rev: str
        fuzzer_engine: str
        fuzzer_lang: str
        statistics: dict
        crash_found: bool


class MQAppState:
    mp_run_result: MP_FuzzerRunResult
    mp_uniq_crash: MP_JiraUniqueCrashFound
    mp_dup_crash: MP_JiraDuplicateCrashFound
    mp_jira_status: MP_JiraIntegrationStatus
    mp_jira_error: MP_JiraReportUndelivered


class MQAppProduceInitializer:

    _settings: AppSettings
    _app: MQApp

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

        broker = self._settings.message_queue.broker.lower()
        settings = self._settings.message_queue

        if broker == "sqs":
            app = await SQSApp.create(
                settings.username,
                settings.password,
                settings.region,
                settings.url,
            )
        else:
            raise ValueError(f"Unsupported message broker: {broker}")

        return app

    async def _configure_channels(self):

        state: MQAppState = self._app.state
        queues = self._settings.message_queue.queues
        channel = await self._app.create_producing_channel(queues.api_gateway)

        mp_uniq_crash = MP_JiraUniqueCrashFound()
        channel.add_producer(mp_uniq_crash)
        state.mp_uniq_crash = mp_uniq_crash

        mp_dup_crash = MP_JiraDuplicateCrashFound()
        channel.add_producer(mp_dup_crash)
        state.mp_dup_crash = mp_dup_crash

        mp_run_result = MP_FuzzerRunResult()
        channel.add_producer(mp_run_result)
        state.mp_run_result = mp_run_result

        mp_jira_status = MP_JiraIntegrationStatus()
        channel.add_producer(mp_jira_status)
        state.mp_jira_status = mp_jira_status

        mp_jira_error = MP_JiraReportUndelivered()
        channel.add_producer(mp_jira_error)
        state.mp_jira_error = mp_jira_error


async def create_mq_instance():
    settings = load_app_settings()
    initializer = MQAppProduceInitializer(settings)
    await initializer.do_init()
    return initializer.app

def datetime_utcnow():
    return datetime.now(timezone.utc)

def rfc3339_now() -> str:
    return datetime_utcnow().replace(microsecond=0).isoformat() + "Z"


async def produce_unique_crash(mq_app: MQApp):

    state: MQAppState = mq_app.state
    mp_uniq_crash = state.mp_uniq_crash
    crash_preview = b64encode(b"unique crash").decode()

    await mp_uniq_crash.produce(
        created=rfc3339_now(),
        fuzzer_id=FUZZER_ID,
        fuzzer_rev=REVISION_ID,
        brief="Error: AddressSanitizer heap buffer overflow",
        input_id="1234",
        preview=crash_preview,
        input_hash="1234",
        output="output\n" * 20,
        reproduced=True,
        type="crash",
    )


async def produce_libfuzzer_statistics(mq_app: MQApp):

    state: MQAppState = mq_app.state
    mp_run_result = state.mp_run_result

    await mp_run_result.produce(
        fuzzer_id=FUZZER_ID,
        fuzzer_rev=REVISION_ID,
        fuzzer_engine="LibFuzzer",
        fuzzer_lang="Cpp",
        crash_found=True,
        statistics=StatisticsLibFuzzer(
            start_time=rfc3339_now(),
            finish_time=rfc3339_now(),
            execs_per_sec=1000,
            edge_cov=0,
            feature_cov=445,
            peak_rss=50000000,
            execs_done=1111000000,
            corpus_entries=123,
            corpus_size=100000,
        ),
    )


async def produce_afl_statistics(mq_app: MQApp):

    state: MQAppState = mq_app.state
    mp_run_result = state.mp_run_result

    await mp_run_result.produce(
        fuzzer_id=FUZZER_ID,
        fuzzer_rev=REVISION_ID,
        fuzzer_engine="AFL",
        fuzzer_lang="Cpp",
        crash_found=True,
        statistics=StatisticsAFL(
            start_time=rfc3339_now(),
            finish_time=rfc3339_now(),
            cycles_done=111021,
            cycles_wo_finds=12,
            execs_done=21115656434,
            execs_per_sec=11200,
            corpus_count=1110,
            corpus_favored=990,
            corpus_found=110,
            corpus_variable=1,
            stability=0.97,
            bitmap_cvg=0.67,
            slowest_exec_ms=100,
            peak_rss_mb=100,
        ),
    )


async def produce_jira_integration_ok(mq_app: MQApp):

    state: MQAppState = mq_app.state
    mp_jira_status = state.mp_jira_status

    await mp_jira_status.produce(
        config_id=CONFIG_ID,
        update_rev=UPDATE_REV,
        error=None,
    )


async def produce_jira_integration_failed(mq_app: MQApp):

    state: MQAppState = mq_app.state
    mp_jira_status = state.mp_jira_status

    await mp_jira_status.produce(
        config_id=CONFIG_ID,
        update_rev=UPDATE_REV,
        error="Project 'kek' does not exist",
    )


async def produce_jira_report_undelivered(mq_app: MQApp):

    state: MQAppState = mq_app.state
    mp_jira_error = state.mp_jira_error

    await mp_jira_error.produce(
        config_id=CONFIG_ID,
        error="Failed to connect to 192.168.1.1:8080",
    )


async def produce(mq_app: MQApp):
    await produce_unique_crash(mq_app)
    # await produce_libfuzzer_statistics(mq_app)
    # await produce_jira_report_undelivered(mq_app)
    # await produce_jira_integration_ok(mq_app)
    # await produce_jira_integration_ok(mq_app)


if __name__ == "__main__":

    #
    # Setup logging. Make some loggers silent to avoid mess
    #

    FORMAT = "%(asctime)s %(levelname)-8s %(name)-15s %(message)s"
    logging.basicConfig(format=FORMAT, level=logging.DEBUG)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)

    #
    # Start application
    # We need loop to start app coroutine
    #

    loop = asyncio.get_event_loop()
    logging.info("Creating MQApp")
    mq_app = loop.run_until_complete(create_mq_instance())

    try:
        logging.info("Running MQApp. Press Ctrl+C to exit")
        loop.run_until_complete(mq_app.start())
        loop.run_until_complete(produce(mq_app))

    except KeyboardInterrupt as e:
        logging.warning("KeyboardInterrupt received")

    finally:
        logging.info("Shutting MQApp down")
        loop.run_until_complete(mq_app.shutdown())
