from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from mqtransport.errors import ConsumeMessageError
from pydantic import BaseModel, validator

from api_gateway.app.database.errors import (
    DBCrashNotFoundError,
    DBFuzzerNotFoundError,
    DBProjectNotFoundError,
    DBRevisionNotFoundError,
    DBUserNotFoundError,
)
from api_gateway.app.database.orm import (
    ORMCrash,
    ORMIntegrationStatus,
    ORMIntegrationTypeID,
)
from fastapi import FastAPI

from .utils import Consumer, Producer

if TYPE_CHECKING:
    from mqtransport import MQApp

    from .instance import MQAppState, Producers


class MC_UniqueCrashFound(Consumer):

    """
    Handle notification from crash analyzer when new unique crash found.
    """

    name = "crash-analyzer.crashes.unique"

    class Model(BaseModel):

        created: str
        """ Date when crash was retrieved """

        fuzzer_id: str
        """ Id of fuzzer which crash belongs to """

        fuzzer_rev: str
        """ Id of revision which crash belongs to """

        preview: str
        """ Chunk of crash input to preview (base64-encoded) """

        input_id: Optional[str]
        """ Identifies crash info in object storage """

        input_hash: str
        """ Unique hash of crash input """

        output: str
        """ Crash output (long multiline text) """

        brief: str
        """ Short description for crash """

        reproduced: bool
        """ True if crash was reproduced, else otherwise """

        type: str
        """ Type of crash """

        @validator("created", pre=True)
        def validate_time(cls, value: str):
            if not value.endswith("Z"):
                raise ValueError("Not a valid rfc3339 time")

            # Try to parse without last 'Z'
            datetime.fromisoformat(value[:-1])
            return value

    @staticmethod
    def _find_producer(
        producers: Producers,
        integration_type: ORMIntegrationTypeID,
    ) -> Producer:

        if integration_type == ORMIntegrationTypeID.jira:
            return producers.jr_unique_crash
        elif integration_type == ORMIntegrationTypeID.youtrack:
            return producers.yt_unique_crash

        raise ValueError(f"Invalid integration type: '{integration_type}'")

    async def consume(self, msg: Model, mq_app: MQApp):

        state: MQAppState = mq_app.state
        app: FastAPI = state.fastapi
        producers = state.producers
        settings = state.settings
        db = state.db

        #
        # Check revision exists and get integration settings
        # Get top level objects for constructing notification
        #

        try:
            revision = await db.revisions.get_by_id(msg.fuzzer_rev)
            fuzzer = await db.fuzzers.get_by_id(msg.fuzzer_id)
            project = await db.projects.get_by_id(fuzzer.project_id)
            user = await db.users.get_by_id(project.owner_id)
            integrations = await db.integrations.list_internal(project.id)

        except DBRevisionNotFoundError as e:
            self.logger.error("Revision '%s' not found", msg.fuzzer_rev)
            raise ConsumeMessageError() from e

        except DBFuzzerNotFoundError as e:
            self.logger.error("Fuzzer '%s' not found", msg.fuzzer_id)
            raise ConsumeMessageError() from e

        except DBProjectNotFoundError as e:
            self.logger.error("Project '%s' not found", fuzzer.project_id)
            raise ConsumeMessageError() from e

        except DBUserNotFoundError as e:
            self.logger.error("User '%s' not found", project.owner_id)
            raise ConsumeMessageError() from e

        text = "Got unique crash for revision '%s'"
        self.logger.info(text, msg.fuzzer_rev)

        #
        # Save crash info to database.
        # Send notifications, according to integration settings
        #

        crash = await db.crashes.create(
            created=msg.created,
            fuzzer_id=msg.fuzzer_id,
            revision_id=msg.fuzzer_rev,
            preview=msg.preview,
            input_id=msg.input_id,
            input_hash=msg.input_hash,
            type=msg.type,
            brief=msg.brief,
            output=msg.output,
            reproduced=msg.reproduced,
            archived=False,
            duplicate_count=0,
        )

        await db.statistics.crashes.inc_crashes(
            date=msg.created,
            fuzzer_id=msg.fuzzer_id,
            revision_id=msg.fuzzer_rev,
            new_unique=1,
        )

        crash_path = app.url_path_for(
            "get_fuzzer_crash",
            user_id=user.id,
            project_id=project.id,
            fuzzer_id=msg.fuzzer_id,
            crash_id=crash.id,
        )

        self_url = settings.api.endpoints.public
        crash_url = self_url + crash_path

        #
        # Iterate through all attached integrations
        # Warn if integration is not ready for sending reports
        #

        async for integration in integrations:

            if not integration.enabled:
                continue

            if integration.status != ORMIntegrationStatus.succeeded:

                self.logger.warning(
                    "Unable to deliver report for integration"
                    " (id='%s', name='%s', status='%s')",
                    integration.id,
                    integration.name,
                    integration.status.value,
                )

                integration.num_undelivered += 1
                await db.integrations.update(integration)
                continue

            await self._find_producer(producers, integration.type).produce(
                crash_id=crash.id,
                crash_info=crash.brief,
                crash_type=crash.type,
                crash_output=crash.output,
                crash_url=crash_url,
                project_name=project.name,
                fuzzer_name=fuzzer.name,
                revision_name=revision.name,
                config_id=integration.config_id,
            )


class MC_DuplicateCrashFound(Consumer):

    """
    Handle notification from crash analyzer when duplicate crash found.
    """

    name = "crash-analyzer.crashes.duplicate"

    class Model(BaseModel):

        fuzzer_id: str
        """ Id of fuzzer which crash belongs to """

        fuzzer_rev: str
        """ Id of revision which crash belongs to """

        input_hash: str
        """ Unique hash of crash input """

    @staticmethod
    def _find_producer(
        producers: Producers,
        integration_type: ORMIntegrationTypeID,
    ) -> Producer:

        if integration_type == ORMIntegrationTypeID.jira:
            return producers.jr_duplicate_crash
        elif integration_type == ORMIntegrationTypeID.youtrack:
            return producers.yt_duplicate_crash

        raise ValueError(f"Invalid integration type: '{integration_type}'")

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state
        producers = state.producers
        db = state.db

        #
        # Check revision exists and get integration settings
        # Then update duplicate counter in database
        #

        try:
            await db.revisions.get_by_id(msg.fuzzer_rev)
            fuzzer = await db.fuzzers.get_by_id(msg.fuzzer_id)
            integrations = await db.integrations.list_internal(fuzzer.project_id)

        except DBRevisionNotFoundError as e:
            self.logger.error("Revision '%s' not found", msg.fuzzer_rev)
            raise ConsumeMessageError() from e

        except DBFuzzerNotFoundError as e:
            self.logger.error("Fuzzer '%s' not found", msg.fuzzer_id)
            raise ConsumeMessageError() from e

        text = "Got known crash for revision '%s'"
        self.logger.info(text, msg.fuzzer_rev)

        try:
            crash = await db.crashes.inc_duplicate_count(
                msg.fuzzer_id, msg.fuzzer_rev, msg.input_hash
            )
        except DBCrashNotFoundError:
            text = "Crash record not found for revision '%s'"
            self.logger.error(text, msg.fuzzer_rev)
            raise ConsumeMessageError()

        #
        # Send notifications, according to integration settings
        # Avoid sending messages for each duplicate found
        #

        if crash.duplicate_count % 10 != 0 and crash.duplicate_count != 1:
            return

        #
        # Iterate through all attached integrations
        # Warn if integration is not ready for sending reports
        #

        async for integration in integrations:

            if not integration.enabled:
                continue

            if integration.status != ORMIntegrationStatus.succeeded:

                self.logger.warning(
                    "Unable to deliver report for integration"
                    " (id='%s', name='%s', status='%s')",
                    integration.id,
                    integration.name,
                    integration.status.value,
                )

                integration.num_undelivered += 1
                await db.integrations.update(integration)
                continue

            await self._find_producer(producers, integration.type).produce(
                duplicate_count=crash.duplicate_count,
                config_id=integration.config_id,
                crash_id=crash.id,
            )
