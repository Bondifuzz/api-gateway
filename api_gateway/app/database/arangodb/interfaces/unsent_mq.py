from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from api_gateway.app.database.abstract import IUnsentMessages

from .base import DBBase
from .utils import maybe_unknown_error

if TYPE_CHECKING:
    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.settings import CollectionSettings


class DBUnsentMessages(DBBase, IUnsentMessages):

    _col_messages: StandardCollection

    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        self._col_messages = db[collections.unsent_messages]
        super().__init__(db, collections)

    @maybe_unknown_error
    async def save_unsent_messages(self, unsent_messages: Dict[str, list]):

        await self._col_messages.truncate()
        for queue_name, messages in unsent_messages.items():

            docs = []
            for i, message in enumerate(messages):
                assert "name" in message
                assert "body" in message
                docs.append(
                    {
                        "name": message["name"],
                        "body": message["body"],
                        "queue": queue_name,
                        "order": i,
                    }
                )

            if docs:
                await self._col_messages.insert_many(docs)

    @maybe_unknown_error
    async def load_unsent_messages(self) -> Dict[str, list]:

        # fmt: off
        query, variables = """
            FOR msg in @@collection
                SORT msg.order
                COLLECT queue = msg.queue INTO groupedByQueue
                RETURN groupedByQueue[*].msg
        """, {
            "@collection": self._col_messages.name,
        }
        # fmt: on

        unsent_messages: Dict[str, list] = {}
        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        grouped_by_queue = [doc async for doc in cursor]

        for grouped_messages in grouped_by_queue:
            for message in grouped_messages:

                mq_message = {
                    "name": message["name"],
                    "body": message["body"],
                }

                queue = message["queue"]

                try:
                    messages = unsent_messages[queue]
                    messages.append(mq_message)

                except KeyError:
                    messages = list()
                    messages.append(mq_message)
                    unsent_messages[queue] = messages

        return unsent_messages
