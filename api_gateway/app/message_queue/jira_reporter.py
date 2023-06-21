from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from mqtransport.errors import ConsumeMessageError
from pydantic import AnyHttpUrl, BaseModel

from api_gateway.app.database.errors import DBIntegrationNotFoundError
from api_gateway.app.database.orm import ORMIntegrationStatus

from .utils import Consumer, Producer

if TYPE_CHECKING:
    from mqtransport import MQApp

    from .instance import MQAppState

########################################
# Producers
########################################


class MP_JiraUniqueCrashFound(Producer):

    """Send notification to jira that unique crash is found"""

    name = "jira-reporter.crashes.unique"

    class Model(BaseModel):

        crash_id: str
        """ Unique id of crash"""

        config_id: str
        """ Unique config id used to find integration """

        crash_info: str
        """ Short description for crash """

        crash_type: str
        """ Type of crash: crash, oom, timeout, leak, etc.. """

        crash_output: str
        """ Crash output (long multiline text) """

        crash_url: AnyHttpUrl
        """ URL can be opened to read crash information """

        project_name: str
        """ Name of project. Used for grouping JIRA issues """

        fuzzer_name: str
        """ Name of fuzzer. Used for grouping JIRA issues """

        revision_name: str
        """ Name of fuzzer revision. Used for grouping JIRA issues """


class MP_JiraDuplicateCrashFound(Producer):

    """Send notification to jira that duplicate of crash is found"""

    name = "jira-reporter.crashes.duplicate"

    class Model(BaseModel):

        crash_id: str
        """ Unique id of crash to get issue id for jira reporter """

        config_id: str
        """ Unique config id used to find integration """

        duplicate_count: int
        """ Count of similar crashes found (at least) """


########################################
# Consumers
########################################


class MC_JiraReportUndelivered(Consumer):

    """
    Handle notification from jira reporter about undelivered reports
    """

    name = "jira-reporter.reports.undelivered"

    class Model(BaseModel):

        config_id: str
        """ Unique config id used to find integration """

        error: str
        """ Last error caused integration to fail """

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state
        integrations = state.db.integrations

        try:
            integration = await integrations.get_by_config_id(msg.config_id)
        except DBIntegrationNotFoundError as e:
            err = "Integration with config id '%s' not found"
            self.logger.error(err, msg.config_id)
            raise ConsumeMessageError() from e

        text = "Failed to deliver report of integration (id='%s', name='%s')"
        self.logger.warning(text, integration.id, integration.name)

        integration.num_undelivered += 1
        integration.last_error = msg.error
        await integrations.update(integration)


class MC_JiraIntegrationResult(Consumer):

    """
    Handle notification from jira reporter about integration result
    """

    name = "jira-reporter.integrations.result"

    class Model(BaseModel):

        config_id: str
        """ Unique config id used to find integration """

        error: Optional[str]
        """ Last error caused integration to fail """

        update_rev: str
        """ Update revision. Used to filter outdated messages """

    async def consume(self, msg: Model, app: MQApp):

        state: MQAppState = app.state
        integrations = state.db.integrations

        try:
            integration = await integrations.get_by_config_id(msg.config_id)
        except DBIntegrationNotFoundError as e:
            err = "Integration with config id '%s' not found"
            self.logger.error(err, msg.config_id)
            raise ConsumeMessageError() from e

        text = "Got integration result for (id='%s', name='%s')"
        self.logger.info(text, integration.id, integration.name)

        if integration.update_rev != msg.update_rev:
            self.logger.warning("Integration status is outdated. Skipping...")
            return

        if msg.error is None:
            text = "Integration succeeded for (id='%s', name='%s')"
            self.logger.info(text, integration.id, integration.name)
            integration.status = ORMIntegrationStatus.succeeded
        else:
            text = "Integration failed for (id='%s', name='%s'). Reason - %s"
            self.logger.warning(text, integration.id, integration.name, msg.error)
            integration.status = ORMIntegrationStatus.failed

        integration.last_error = msg.error
        await integrations.update(integration)
