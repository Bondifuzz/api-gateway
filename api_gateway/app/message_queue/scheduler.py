from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from mqtransport.errors import ConsumeMessageError
from pydantic import BaseModel, Field

from api_gateway.app.database.errors import DBRevisionNotFoundError
from api_gateway.app.database.orm import (
    ORMEngineID,
    ORMEvent,
    ORMFeedback,
    ORMHealth,
    ORMLangID,
    ORMRevisionStatus,
    ORMStatisticsAFL,
    ORMStatisticsLibFuzzer,
)
from api_gateway.app.utils import rfc3339_now

from .utils import Consumer, Producer

if TYPE_CHECKING:
    from mqtransport import MQApp

    from .instance import MQAppState


########################################
# Producers
########################################


class MP_StartFuzzer(Producer):

    """Send task to scheduler to start fuzzer"""

    name = "api-gateway.fuzzer.start"

    class Model(BaseModel):
        user_id: str
        project_id: str
        pool_id: str
        fuzzer_id: str
        fuzzer_rev: str
        fuzzer_engine: str
        fuzzer_lang: str
        cpu_usage: int = Field(gt=0)
        ram_usage: int = Field(gt=0)
        tmpfs_size: int = Field(gt=0)
        reset_state: bool
        is_verified: bool
        image_id: str


class MP_UpdateFuzzer(Producer):

    """Send task to scheduler to update running fuzzer"""

    name = "api-gateway.fuzzer.update"

    class Model(BaseModel):
        pool_id: str
        fuzzer_id: str
        fuzzer_rev: str
        cpu_usage: int = Field(gt=0)
        ram_usage: int = Field(gt=0)
        tmpfs_size: int = Field(gt=0)


class MP_StopFuzzer(Producer):

    """Send task to scheduler to stop fuzzer"""

    name = "api-gateway.fuzzer.stop"

    class Model(BaseModel):
        pool_id: str
        fuzzer_id: str
        fuzzer_rev: str


class MP_StopFuzzersInPool(Producer):

    """Send task to scheduler to stop fuzzers in pool"""

    name = "api-gateway.pool.stop_all_fuzzers"

    class Model(BaseModel):
        pool_id: str


########################################
# Consumers
########################################


class Status(BaseModel):
    code: str
    message: str
    details: Optional[str]


class MC_FuzzerVerified(Consumer):

    """Handle event from scheduler when fuzzer is verified"""

    name = "scheduler.fuzzer.verified"

    class Model(BaseModel):
        fuzzer_id: str
        fuzzer_rev: str

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state

        try:
            revision = await state.db.revisions.get_by_id(msg.fuzzer_rev)

            if revision.status != ORMRevisionStatus.verifying:
                raise ValueError("Revision is not in verifying state")

        except DBRevisionNotFoundError as e:
            self.logger.error("Revision '%s' not found", msg.fuzzer_rev)
            raise ConsumeMessageError() from e

        except ValueError as e:
            text = "Got logical error for revision '%s' - %s"
            self.logger.error(text, msg.fuzzer_rev, e)
            raise ConsumeMessageError() from e

        revision.is_verified = True
        revision.status = ORMRevisionStatus.running
        await state.db.revisions.update(revision)

        text = "Revision '%s' was successfully verified"
        self.logger.info(text, msg.fuzzer_rev)


class MC_FuzzerStopped(Consumer):

    """Handle task from scheduler when fuzzer is stopped"""

    name = "scheduler.fuzzer.stopped"

    class Model(BaseModel):
        fuzzer_id: str
        fuzzer_rev: str
        fuzzer_status: Status
        fuzzer_health: ORMHealth  # warn, err
        agent_status: Optional[Status]

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state

        try:
            revision = await state.db.revisions.get_by_id(msg.fuzzer_rev)

            if revision.status not in [
                ORMRevisionStatus.running,
                ORMRevisionStatus.verifying,
            ]:
                raise ValueError("Revision is not running")

        except DBRevisionNotFoundError as e:
            self.logger.error("Revision '%s' not found", msg.fuzzer_rev)
            raise ConsumeMessageError() from e

        except ValueError as e:
            text = "Got logical error for revision '%s' - %s"
            self.logger.error(text, msg.fuzzer_rev, e)
            raise ConsumeMessageError() from e

        status_code = msg.fuzzer_status.code
        status_message = msg.fuzzer_status.message
        text = "Revision '%s' was stopped. Reason: [%d] %s"
        self.logger.info(text, msg.fuzzer_rev, status_code, status_message)

        #
        # Stop fuzzer and update health, status
        #

        revision.health = msg.fuzzer_health
        if revision.status == ORMRevisionStatus.verifying:
            revision.status = ORMRevisionStatus.unverified
        else:
            revision.status = ORMRevisionStatus.stopped

        #
        # Record the reason of fuzzer stop and update database
        #

        status = msg.agent_status
        agent_status = ORMEvent.construct(**status.dict()) if status else None
        fuzzer_status = ORMEvent.construct(**msg.fuzzer_status.dict())

        revision.feedback = ORMFeedback.construct(
            scheduler=fuzzer_status, agent=agent_status
        )

        revision.last_stop_date = rfc3339_now()
        await state.db.revisions.update(revision)


class MC_FuzzerStatusChanged(Consumer):

    """Handle notification from scheduler when fuzzer status changes"""

    name = "scheduler.fuzzer.status"

    class Model(BaseModel):
        fuzzer_id: str
        fuzzer_rev: str
        fuzzer_status: Status
        fuzzer_health: ORMHealth  # ok, warn

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state

        try:
            revision = await state.db.revisions.get_by_id(msg.fuzzer_rev)

            if revision.status != ORMRevisionStatus.running:
                raise ValueError("Revision is not running")

        except DBRevisionNotFoundError as e:
            self.logger.error("Revision '%s' not found", msg.fuzzer_rev)
            raise ConsumeMessageError() from e

        except ValueError as e:
            text = "Got logical error for revision '%s' - %s"
            self.logger.error(text, msg.fuzzer_rev, e)
            raise ConsumeMessageError() from e

        revision.health = msg.fuzzer_health
        fuzzer_status = ORMEvent.construct(**msg.fuzzer_status.dict())
        revision.feedback = ORMFeedback.construct(scheduler=fuzzer_status, agent=None)
        await state.db.revisions.update(revision)

        status_code = msg.fuzzer_status.code
        status_message = msg.fuzzer_status.message
        text = "Status of revision '%s' was changed. Status: [%d] %s"
        self.logger.info(text, msg.fuzzer_rev, status_code, status_message)

        # reverse lookup to find project, user
        # notification add
        # notification queue push


class StatisticsBase(BaseModel):

    work_time: int
    """ Fuzzer work time """


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


class MC_FuzzerRunResult(Consumer):

    """
    Handle notification from scheduler when fuzzer run finishes successfully.
    """

    name = "scheduler.fuzzer.result"

    class Model(BaseModel):
        user_id: str
        project_id: str
        pool_id: str
        fuzzer_id: str
        fuzzer_rev: str
        fuzzer_engine: ORMEngineID
        fuzzer_lang: ORMLangID

        start_time: str
        finish_time: str

        statistics: Optional[dict]
        crashes_found: int

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state

        try:
            await state.db.revisions.get_by_id(msg.fuzzer_rev)
        except DBRevisionNotFoundError as e:
            self.logger.error("Revision '%s' not found", msg.fuzzer_rev)
            raise ConsumeMessageError() from e

        if msg.crashes_found > 0:
            await state.db.statistics.crashes.inc_crashes(
                date=msg.finish_time,
                fuzzer_id=msg.fuzzer_id,
                revision_id=msg.fuzzer_rev,
                new_total=msg.crashes_found,
            )

        if msg.statistics is not None:
            if ORMEngineID.is_libfuzzer(msg.fuzzer_engine):
                stats = StatisticsLibFuzzer.parse_obj(msg.statistics)
                orm_stats = ORMStatisticsLibFuzzer.construct(
                    date=msg.finish_time,
                    fuzzer_id=msg.fuzzer_id,
                    revision_id=msg.fuzzer_rev,
                    **stats.dict(),
                )
                await state.db.statistics.libfuzzer.create(orm_stats)

            elif ORMEngineID.is_afl(msg.fuzzer_engine):
                stats = StatisticsAFL.parse_obj(msg.statistics)
                orm_stats = ORMStatisticsAFL.construct(
                    date=msg.finish_time,
                    fuzzer_id=msg.fuzzer_id,
                    revision_id=msg.fuzzer_rev,
                    **stats.dict(),
                )
                await state.db.statistics.afl.create(orm_stats)

            else:
                self.logger.error(f"Unknown engine id: {msg.fuzzer_engine}")
                raise ConsumeMessageError()

        self.logger.info("Got statistics for revision '%s'", msg.fuzzer_rev)
