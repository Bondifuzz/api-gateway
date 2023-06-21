from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from api_gateway.app.database.abstract import IStatisticsAFL
from api_gateway.app.database.orm import (
    ORMGroupedStatisticsAFL,
    ORMStatisticsAFL,
    ORMStatisticsGroupBy,
)

from ..utils import dbkey_to_id, maybe_unknown_error
from .base import DBStatisticsBase

ORMStatistics = ORMStatisticsAFL
ORMGroupedStatistics = ORMGroupedStatisticsAFL

if TYPE_CHECKING:
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBStatisticsAFL(DBStatisticsBase, IStatisticsAFL):
    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        aggregates = {
            "work_time": dict(aggr_func="SUM"),
            "cycles_done": dict(aggr_func="SUM"),
            "cycles_wo_finds": dict(aggr_func="SUM"),
            "execs_done": dict(aggr_func="SUM"),
            "execs_per_sec": dict(aggr_func="AVG", ret_func="ROUND"),
            "corpus_count": dict(aggr_func="AVG", ret_func="ROUND"),
            "corpus_favored": dict(aggr_func="AVG", ret_func="ROUND"),
            "corpus_found": dict(aggr_func="SUM"),
            "corpus_variable": dict(aggr_func="AVG", ret_func="ROUND"),
            "stability": dict(aggr_func="AVG"),
            "bitmap_cvg": dict(aggr_func="MAX"),
            "slowest_exec_ms": dict(aggr_func="AVG", ret_func="ROUND"),
            "peak_rss_mb": dict(aggr_func="AVG", ret_func="ROUND"),
        }
        super().__init__(db, collections, aggregates, collections.statistics.afl)

    @maybe_unknown_error
    async def create(self, statistics: ORMStatistics) -> ORMStatistics:
        res = await self._col_statistics.insert(statistics.dict(exclude={"id"}))
        return ORMStatistics(**dbkey_to_id({**res, **statistics.dict()}))

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
