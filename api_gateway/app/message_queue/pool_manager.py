from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from .utils import Consumer

if TYPE_CHECKING:
    from mqtransport import MQApp


########################################
# Consumers
########################################


class MC_PoolDeleted(Consumer):

    """Handle pool status change"""

    name = "pool-manager.pool-deleted"

    class Model(BaseModel):
        id: str

    async def consume(self, pool: Model, app: MQApp):

        # TODO:
        """
        FOR project IN @@col_projects
            FILTER project.pool_id == @pool_id
            UPDATE project WITH {
                pool_id: null
            } IN @@col_projects
        """
        raise NotImplementedError()
