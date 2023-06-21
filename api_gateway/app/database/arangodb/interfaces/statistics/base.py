from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from api_gateway.app.database.orm import ORMStatisticsGroupBy, Paginator

from ..base import DBBase
from ..utils import maybe_unknown_error

if TYPE_CHECKING:
    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.settings import CollectionSettings


class DBStatisticsBase(DBBase):

    _col_statistics: StandardCollection
    _aggregates: Dict[str, Dict[str, str]]

    def __init__(
        self,
        db: StandardDatabase,
        collections: CollectionSettings,
        aggregates: Dict[str, Dict[str, str]],
        collection_name: str,
    ):
        super().__init__(db, collections)
        self._aggregates = aggregates
        self._col_statistics = db[collection_name]

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        date_begin: Optional[str] = None,
        date_end: Optional[str] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        # revision_id is globally unique
        # Specifying both fuzzer_id and revision_id is redundant
        if fuzzer_id and revision_id:
            fuzzer_id = None

        if fuzzer_id:
            filters.append("FILTER item.fuzzer_id == @fuzzer_id")
            variables.update({"fuzzer_id": fuzzer_id})

        if revision_id:
            filters.append("FILTER item.revision_id == @revision_id")
            variables.update({"revision_id": revision_id})

        if date_begin:
            filters.append("FILTER item.date >= @date_begin")
            variables.update({"date_begin": date_begin})

        if date_end:
            # add one time unit to include date_end
            filters.append("FILTER item.date < DATE_ADD(@date_end, 1, @period)")
            variables.update({"date_end": date_end})

        if filters:
            query = query.replace("<filter-options>", "\n\t\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    @staticmethod
    def _apply_aggregates(query: str, aggregates: Dict[str, Dict[str, str]]):

        assert "<aggregate-functions>" in query
        assert "<aggregate-returns>" in query

        delim = ",\n" + "\t" * 3
        functions = []
        returns = []

        for param, aggregate in aggregates.items():
            functions.append(f"{param} = {aggregate['aggr_func']}(item.{param})")

            if "ret_func" in aggregate:
                returns.append(f"{param}: {aggregate['ret_func']}({param})")
            else:
                returns.append(f"{param}: {param}")

        query = query.replace("<aggregate-functions>", delim.join(functions))
        query = query.replace("<aggregate-returns>", delim.join(returns))

        return query

    @maybe_unknown_error
    async def _execute_list_query(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ):

        assert self._col_statistics is not None
        assert fuzzer_id or revision_id

        # fmt: off
        query, variables = """
            LET start_date = DATE_TRUNC(@date_begin, "day")

            let crash_statistics = (
                FOR item IN @@col_crash_statistics
                    <filter-options>

                    LET current_date = DATE_TRUNC(item.date, "day")
                    COLLECT i = FLOOR(DATE_DIFF(start_date, current_date, @period, true))
                    AGGREGATE
                        total = SUM(item.total),
                        unique = SUM(item.unique)

                    RETURN {
                        date: DATE_ADD(start_date, i, @period),
                        total: total,
                        unique: unique,
                    }
            )

            FOR item IN @@col_statistics
                <filter-options>

                LET current_date = DATE_TRUNC(item.date, "day")
                COLLECT i = FLOOR(DATE_DIFF(start_date, current_date, @period, true))
                AGGREGATE
                    <aggregate-functions>

                // Code bellow will be executed only for current page(limit)
                LIMIT @offset, @limit

                LET date = DATE_ADD(start_date, i, @period)
                LET crash_stats_tmp = FIRST(
                    FOR crash_item IN crash_statistics
                        FILTER crash_item.date == date
                        LIMIT 1 RETURN crash_item
                )

                // Set crashes to zero if no data found in query above
                LET crash_stats = crash_stats_tmp ?: {
                    total: 0,
                    unique: 0, 
                }

                RETURN {
                    date: date,
                    unique_crashes: crash_stats.unique,
                    known_crashes: crash_stats.total - crash_stats.unique,
                    total_crashes: crash_stats.total,
                    <aggregate-returns>,
                }
        """, {
            "@col_crash_statistics": self._collections.statistics.crashes,
            "@col_statistics": self._col_statistics.name,
            "period": group_by,
            "offset": paginator.offset,
            "limit": paginator.limit,
            "date_begin": date_begin,
        }
        # fmt: on

        query = self._apply_aggregates(query, self._aggregates)

        query, variables = self._apply_filter_options(
            query, variables, fuzzer_id, revision_id, date_begin, date_end
        )

        return await self._db.aql.execute(query, bind_vars=variables)

    @maybe_unknown_error
    async def count(
        self,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ) -> int:

        assert self._col_statistics is not None
        assert fuzzer_id or revision_id

        # fmt: off
        query, variables = """

            LET start_date = DATE_TRUNC(@date_begin, "day")

            FOR item IN @@col_statistics

                <filter-options>

                LET current_date = DATE_TRUNC(item.date, "day")
                COLLECT i = FLOOR(DATE_DIFF(start_date, current_date, @period, true))
                COLLECT WITH COUNT INTO stats_count

                RETURN stats_count

        """, {
            "@col_statistics": self._col_statistics.name,
            "period": group_by,
            "date_begin": date_begin,
        }
        # fmt: on

        query, variables = self._apply_filter_options(
            query, variables, fuzzer_id, revision_id, date_begin, date_end
        )

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    async def _find_unaggregated_revisions(self):
        # find revisions with unaggregated statistics

        # fmt: off
        query, variables = """
            LET start_date = DATE_SUBTRACT(DATE_NOW(), 2, "day")
            FOR item in @@col_statistics
                FILTER item.date < start_date

                COLLECT
                    fuzzer_id = item.fuzzer_id,
                    revision_id = item.revision_id,
                    date = DATE_TRUNC(item.date, "day")
                WITH COUNT INTO stats_count

                FILTER stats_count > 1
                RETURN {
                    fuzzer_id: fuzzer_id,
                    revision_id: revision_id,
                    date: date,
                    //stats_count: stats_count,
                }
        """, {
            "@col_statistics": self._col_statistics.name,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)

        async def async_iter():
            async for doc in cursor:
                t_doc: dict = doc
                yield t_doc

        return async_iter()

    async def _get_stat(self, fuzzer_id: str, revision_id: str, date: str) -> dict:
        async for stat in await self._execute_list_query(
            paginator=Paginator(0, 1),
            fuzzer_id=fuzzer_id,
            revision_id=revision_id,
            group_by=ORMStatisticsGroupBy.day,
            date_begin=date,
            date_end=date,
        ):
            return stat

    async def _aggregate_stats(self):
        async for unAggrDate in await self._find_unaggregated_revisions():

            # if unAggrDate["fuzzer_id"] != "8223081" or unAggrDate["revision_id"] != "8803311":
            #    continue

            # get aggregated stats
            stat = await self._get_stat(
                fuzzer_id=unAggrDate["fuzzer_id"],
                revision_id=unAggrDate["revision_id"],
                date=unAggrDate["date"],
            )
            del stat["unique_crashes"]
            del stat["known_crashes"]
            del stat["total_crashes"]

            stat["fuzzer_id"] = unAggrDate["fuzzer_id"]
            stat["revision_id"] = unAggrDate["revision_id"]

            # if unAggrDate["fuzzer_id"] != "8223081" or unAggrDate["revision_id"] != "8803311":
            #    continue

            # insert aggregated stats
            new_stat = await self._col_statistics.insert(stat)

            # removing all unaggregated stats in this date

            # fmt: off
            query, variables = """
                LET start_date = DATE_TRUNC(@date, "day")
                LET end_date = DATE_ADD(start_date, 1, "day")
                FOR item in @@col_statistics
                    FILTER item.fuzzer_id == @fuzzer_id
                    FILTER item.revision_id == @revision_id
                    FILTER item.date >= start_date
                    FILTER item.date < end_date
                    FILTER item._key != @aggregated_key

                    REMOVE item IN @@col_statistics
            """, {
                "@col_statistics": self._col_statistics.name,
                "fuzzer_id": unAggrDate["fuzzer_id"],
                "revision_id": unAggrDate["revision_id"],
                "aggregated_key": new_stat["_key"],
                "date": unAggrDate["date"],
            }
            # fmt: on

            await self._db.aql.execute(query, bind_vars=variables)
