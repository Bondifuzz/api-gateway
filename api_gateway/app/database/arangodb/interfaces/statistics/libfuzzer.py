from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from api_gateway.app.database.abstract import IStatisticsLibFuzzer
from api_gateway.app.database.orm import (
    ORMGroupedStatisticsLibFuzzer,
    ORMStatisticsGroupBy,
    ORMStatisticsLibFuzzer,
)

from ..utils import dbkey_to_id, maybe_unknown_error
from .base import DBStatisticsBase

ORMStatistics = ORMStatisticsLibFuzzer
ORMGroupedStatistics = ORMGroupedStatisticsLibFuzzer

if TYPE_CHECKING:
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBStatisticsLibFuzzer(DBStatisticsBase, IStatisticsLibFuzzer):
    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        aggregates = {
            "work_time": dict(aggr_func="SUM"),
            "execs_done": dict(aggr_func="SUM"),
            "execs_per_sec": dict(aggr_func="AVG", ret_func="ROUND"),
            "peak_rss": dict(aggr_func="AVG", ret_func="ROUND"),
            "corpus_entries": dict(aggr_func="AVG", ret_func="ROUND"),
            "corpus_size": dict(aggr_func="AVG", ret_func="ROUND"),
            "edge_cov": dict(aggr_func="MAX"),
            "feature_cov": dict(aggr_func="MAX"),
        }
        super().__init__(db, collections, aggregates, collections.statistics.libfuzzer)

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
