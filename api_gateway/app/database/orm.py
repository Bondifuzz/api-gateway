from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ORMCookie(BaseModel):
    id: str
    expires: Optional[str] = None
    user_id: str
    metadata: str


class ORMDeviceCookie(BaseModel):
    username: str
    nonce: str


class ORMUser(BaseModel):
    id: str
    name: str
    display_name: str
    password_hash: str
    is_confirmed: bool
    is_disabled: bool
    is_admin: bool
    is_system: bool
    email: str
    erasure_date: Optional[str] = Field(None)
    no_backup: bool = Field(False)


class ORMUserLockout(BaseModel):

    id: str
    """ Use pair <user_id, NONCE> as unique key """

    exp_date: str
    """ Expiration date of account lockout for this device cookie """


class ORMImageStatus(str, Enum):
    not_pushed = "NotPushed"
    verifying = "Verifying"
    verify_error = "VerifyError"
    ready = "Ready"


class ORMImageType(str, Enum):
    custom = "Custom"
    builtin = "Built-in"


class ORMEngineID(str, Enum):
    # afl binding
    afl = "afl"
    afl_rs = "afl.rs"
    sharpfuzz_afl = "sharpfuzz-afl"

    # libfuzzer binding
    libfuzzer = "libfuzzer"
    jazzer = "jazzer"
    atheris = "atheris"
    cargo_fuzz = "cargo-fuzz"
    go_fuzz_libfuzzer = "go-fuzz-libfuzzer"
    sharpfuzz_libfuzzer = "sharpfuzz-libfuzzer"

    @staticmethod
    def is_afl(engine_id: ORMEngineID):
        return engine_id in {
            ORMEngineID.afl,
            ORMEngineID.afl_rs,
            ORMEngineID.sharpfuzz_afl,
        }

    @staticmethod
    def is_libfuzzer(engine_id: ORMEngineID):
        return engine_id in {
            ORMEngineID.libfuzzer,
            ORMEngineID.jazzer,
            ORMEngineID.atheris,
            ORMEngineID.cargo_fuzz,
            ORMEngineID.go_fuzz_libfuzzer,
            ORMEngineID.sharpfuzz_libfuzzer,
        }


class ORMLangID(str, Enum):
    go = "go"  # go-fuzz-libfuzzer
    cpp = "cpp"  # afl, libfuzzer
    rust = "rust"  # afl.rs, cargo-fuzz
    java = "java"  # jqf, jazzer
    swift = "swift"  # libfuzzer
    python = "python"  # atheris
    # javascript = "javascript" # libfuzzer


class ORMLang(BaseModel):
    id: ORMLangID
    display_name: str


class ORMEngine(BaseModel):
    id: ORMEngineID
    display_name: str
    langs: List[ORMLangID]


class ORMImage(BaseModel):
    id: str
    name: str
    description: str
    engines: List[ORMEngineID]
    status: ORMImageStatus
    project_id: Optional[str] = None


class ORMIntegrationType(BaseModel):
    id: ORMIntegrationTypeID
    display_name: str
    twoway: bool


class ORMProject(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    created: str
    pool_id: Optional[str]

    erasure_date: Optional[str] = Field(None)
    no_backup: bool = Field(False)


class ORMFuzzer(BaseModel):
    id: str
    name: str
    description: str
    project_id: str
    engine: ORMEngineID
    lang: ORMLangID
    ci_integration: bool
    created: str
    active_revision: Optional[ORMRevision]

    erasure_date: Optional[str] = Field(None)
    no_backup: bool = Field(False)


class ORMEvent(BaseModel):
    code: str
    message: str
    details: Optional[str]


class ORMError(BaseModel):
    code: str
    message: str


class ORMFeedback(BaseModel):
    scheduler: ORMEvent
    agent: Optional[ORMEvent] = None


class ORMUploadStatus(BaseModel):
    uploaded: bool
    last_error: Optional[ORMError] = None


class ORMRevisionStatus(str, Enum):
    unverified = "Unverified"
    verifying = "Verifying"
    running = "Running"
    stopped = "Stopped"


class ORMHealth(str, Enum):
    warn = "Warning"
    err = "Error"
    ok = "Ok"


class ORMRevision(BaseModel):
    id: str
    name: str
    description: str
    binaries: ORMUploadStatus
    seeds: ORMUploadStatus
    config: ORMUploadStatus
    status: ORMRevisionStatus
    health: ORMHealth
    feedback: Optional[ORMFeedback] = None
    fuzzer_id: str
    image_id: str
    is_verified: bool
    created: str
    last_start_date: Optional[str] = None
    last_stop_date: Optional[str] = None
    cpu_usage: int
    ram_usage: int
    tmpfs_size: int

    erasure_date: Optional[str] = Field(None)
    no_backup: bool = Field(False)


class ORMStatisticsGroupBy(str, Enum):
    day = "day"
    week = "week"
    month = "month"


class ORMBaseStatistics(BaseModel):

    id: Optional[str] = None

    fuzzer_id: str
    """ Id of fuzzer which statistics belongs to """

    revision_id: str
    """ Id of revision which statistics belongs to """

    date: str
    """ Date when statistics was retrieved """


class ORMStatisticsCrashesExact(BaseModel):
    total: int
    unique: int


class ORMStatisticsCrashes(
    ORMBaseStatistics,
    ORMStatisticsCrashesExact,
):
    pass


class ORMBaseFuzzerStatistics(ORMBaseStatistics):

    work_time: int
    """ Fuzzer working time """


class ORMStatisticsLibFuzzerExact(BaseModel):

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


class ORMStatisticsLibFuzzer(
    ORMBaseFuzzerStatistics,
    ORMStatisticsLibFuzzerExact,
):
    pass


class ORMStatisticsAFLExact(BaseModel):

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


class ORMStatisticsAFL(
    ORMBaseFuzzerStatistics,
    ORMStatisticsAFLExact,
):
    pass


class ORMBaseGroupedStatistics(BaseModel):

    date: str
    """ Date period """

    unique_crashes: int
    """ Count of unique crashes found during period """

    known_crashes: int
    """ Count of all crashes found during period """

    work_time: int
    """ Fuzzer work time(seconds) """


class ORMGroupedStatisticsLibFuzzer(
    ORMBaseGroupedStatistics,
    ORMStatisticsLibFuzzerExact,
):
    pass


class ORMGroupedStatisticsAFL(
    ORMBaseGroupedStatistics,
    ORMStatisticsAFLExact,
):
    pass


class ORMCrash(BaseModel):

    id: str
    """ Autogenerated unique database key """

    created: str
    """ Date when crash was retrieved """

    fuzzer_id: str
    """ Id of fuzzer which statistics belongs to """

    revision_id: str
    """ Id of revision which statistics belongs to """

    preview: str
    """ Chunk of crash input to preview (base64-encoded) """

    input_id: Optional[str]
    """ Id (key) of uploaded to object storage input which caused program to abort """

    input_hash: str
    """ Unique hash of crash input """

    type: str
    """ Type of crash: crash, oom, timeout, leak, etc.. """

    brief: str
    """ Short description for crash """

    output: str
    """ Crash output (long multiline text) """

    reproduced: bool
    """ True if crash was reproduced, else otherwise """

    archived: bool
    """ True if moved to archive(marked as resolved) """

    duplicate_count: int
    """ Count of similar crashes found """


class ORMIntegrationStatus(str, Enum):

    in_progress = "InProgress"
    """ Verifying bug tracker connection, credentials, etc... """

    succeeded = "Succeeded"
    """ Integration succeeded. Notification delivery works well """

    failed = "Failed"
    """ Integration failed. Notifications will not be delivered """


class ORMIntegrationTypeID(str, Enum):
    jira = "jira"
    youtrack = "youtrack"
    # telegram = "telegram"
    # mail = "mail"


class ORMIntegration(BaseModel):

    id: str
    """ Autogenerated unique database key """

    name: str
    """ Unique name of integration. Must be created by user """

    project_id: str
    """ Unique project id which bug tracker configuration is linked to"""

    config_id: str
    """ Unique id used for working with reporter service """

    type: ORMIntegrationTypeID
    """ Type of integration: jira, youtrack, mail, etc... """

    status: ORMIntegrationStatus
    """ Integration status: whether works or not """

    last_error: Optional[str]
    """ Last error caused integration to fail """

    update_rev: str
    """ Revision of update operation. Always changed on update. Only the last one is valid """

    enabled: bool
    """ When set, integration with bug tracker is enabled """

    num_undelivered: int
    """ Count of reports which were not delivered to bug tracker """


class Paginator:
    def __init__(self, pg_num: int, pg_size: int):
        self.pg_num = pg_num
        self.pg_size = pg_size
        self.offset = pg_num * pg_size
        self.limit = pg_size


########################################

# ORMUser.update_forward_refs()
ORMFuzzer.update_forward_refs()
ORMIntegrationType.update_forward_refs()
