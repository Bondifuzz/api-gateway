from pydantic import BaseModel
from api_gateway.app.api.base import BasePaginatorResponseModel
from api_gateway.app.api.constants import *
from typing import List, Union


class GetGrpStatBaseModel(BaseModel):

    """Base class for grouped statistics"""

    date: str
    """ Date period """

    unique_crashes: int
    """ Count of unique crashes found during period """

    known_crashes: int
    """ Count of all crashes found during period """

    work_time: int
    """ Fuzzer work time(seconds) """


class GetGrpStatLibFuzzerResponseModel(GetGrpStatBaseModel):

    """Grouped statistics for libfuzzer engine"""

    execs_per_sec: int
    """ Average count of executions per second """

    edge_cov: int
    """ Edge coverage """

    feature_cov: int
    """ Feature coverage """

    peak_rss: int
    """ Max RAM usage """

    execs_done: int
    """ Count of fuzzing iterations executed """

    corpus_entries: int
    """ Count of files in merged corpus """

    corpus_size: int
    """ The size of generated corpus in bytes """


class GetGrpStatAflResponseModel(GetGrpStatBaseModel):

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


class ListStatisticsResponseModel(BasePaginatorResponseModel):
    LibFuzzer = GetGrpStatLibFuzzerResponseModel
    AFL = GetGrpStatAflResponseModel
    items: List[Union[LibFuzzer, AFL]]
