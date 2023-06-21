from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from api_gateway.app.database.abstract import IStatisticsCrashes
from api_gateway.app.database.orm import (
    ORMGroupedStatisticsLibFuzzer,
    ORMStatisticsGroupBy,
    ORMStatisticsLibFuzzer,
)

from ..utils import maybe_unknown_error
from .base import DBStatisticsBase

ORMStatistics = ORMStatisticsLibFuzzer
ORMGroupedStatistics = ORMGroupedStatisticsLibFuzzer

if TYPE_CHECKING:
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBStatisticsCrashes(DBStatisticsBase, IStatisticsCrashes):
    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        aggregates = {
            "total": dict(aggr_func="SUM"),
            "unique": dict(aggr_func="SUM"),
        }
        super().__init__(db, collections, aggregates, collections.statistics.crashes)

    @maybe_unknown_error
    async def inc_crashes(
        self,
        date: str,
        fuzzer_id: str,
        revision_id: str,
        new_total: int = 0,
        new_unique: int = 0,
    ) -> None:

        assert new_total >= 0 and new_unique >= 0

        # TODO: aggregation interval
        # fmt: off
        query, variables = """
            LET date_now = DATE_TRUNC(@date, "hour")
            UPSERT { date: date_now, fuzzer_id: @fuzzer_id, revision_id: @revision_id }
            INSERT { date: date_now, fuzzer_id: @fuzzer_id, revision_id: @revision_id, total: @n_total, unique: @n_unique }
            UPDATE { total: OLD.total + @n_total, unique: OLD.unique + @n_unique } IN @@col_statistics

        """, {
            "@col_statistics": self._col_statistics.name,
            "date": date,
            "fuzzer_id": fuzzer_id,
            "revision_id": revision_id,
            "n_total": new_total,
            "n_unique": new_unique,
        }
        # fmt: on

        await self._db.aql.execute(query, bind_vars=variables)

    @maybe_unknown_error
    async def list(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ) -> List[ORMGroupedStatistics]:
        return [
            ORMGroupedStatistics(**doc)
            async for doc in await self._execute_list_query(
                paginator,
                fuzzer_id,
                revision_id,
                group_by,
                date_begin,
                date_end,
            )
        ]
