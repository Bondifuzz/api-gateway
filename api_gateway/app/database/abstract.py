from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator, Dict, Set, Tuple

from api_gateway.app.database.orm import (
    ORMCrash,
    ORMDeviceCookie,
    ORMEngine,
    ORMEngineID,
    ORMFeedback,
    ORMHealth,
    ORMImageStatus,
    ORMImageType,
    ORMIntegration,
    ORMIntegrationStatus,
    ORMIntegrationType,
    ORMIntegrationTypeID,
    ORMLang,
    ORMLangID,
    ORMRevisionStatus,
    ORMStatisticsAFL,
    ORMStatisticsCrashes,
    ORMStatisticsGroupBy,
    ORMStatisticsLibFuzzer,
    ORMUploadStatus,
)
from api_gateway.app.utils import ObjectRemovalState, testing_only

if TYPE_CHECKING:
    from typing import List, Optional

    from api_gateway.app.database.orm import (
        ORMCookie,
        ORMFuzzer,
        ORMImage,
        ORMProject,
        ORMRevision,
        ORMUser,
        Paginator,
    )
    from api_gateway.app.settings import (
        AppSettings,
        DefaultUserSettings,
        SystemAdminSettings,
    )


class IUnsentMessages(metaclass=ABCMeta):

    """
    Used for saving/loading MQ unsent messages from database.
    """

    @abstractmethod
    async def save_unsent_messages(self, messages: Dict[str, list]):
        pass

    @abstractmethod
    async def load_unsent_messages(self) -> Dict[str, list]:
        pass


class ICookies(metaclass=ABCMeta):

    """Used for managing user cookies"""

    @abstractmethod
    async def create(
        self,
        user_id: str,
        metadata: str,
        expiration_seconds: int,
    ) -> ORMCookie:
        pass

    @abstractmethod
    async def get(self, cookie_id: str, user_id: Optional[str] = None) -> ORMCookie:
        pass

    @abstractmethod
    async def delete(self, cookie: ORMCookie):
        pass

    @abstractmethod
    async def list(self, paginator: Paginator, user_id=None) -> List[ORMCookie]:
        pass


class IUsers(metaclass=ABCMeta):

    """Used for managing user accounts"""

    @abstractmethod
    async def create(
        self,
        name: str,
        display_name: str,
        password_hash: str,
        is_confirmed: bool,
        is_disabled: bool,
        is_admin: bool,
        is_system: bool,
        email: str,
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMUser:
        pass

    @abstractmethod
    async def delete(self, user: ORMUser) -> None:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        user_id: str,
    ) -> ORMUser:
        pass

    @abstractmethod
    async def get_by_name(
        self,
        user_name: str,
    ) -> ORMUser:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> List[ORMUser]:
        pass

    @abstractmethod
    async def count(
        self,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> int:
        pass

    @abstractmethod
    async def update(self, user: ORMUser):
        pass

    @abstractmethod
    async def create_system_admin(self, settings: SystemAdminSettings) -> ORMUser:
        pass

    @abstractmethod
    async def create_default_user(self, settings: DefaultUserSettings) -> ORMUser:
        pass

    @abstractmethod
    @testing_only
    async def generate_test_set(self, n: int, prefix: str) -> List[ORMUser]:
        pass


class IUserLockout(metaclass=ABCMeta):
    @abstractmethod
    async def add(self, device_cookie: ORMDeviceCookie, exp_seconds: str):
        pass

    @abstractmethod
    async def has(self, device_cookie: ORMDeviceCookie) -> bool:
        pass

    @abstractmethod
    async def remove_expired(self):
        pass


class ILangs(metaclass=ABCMeta):
    @abstractmethod
    async def get_by_id(self, lang_id: ORMLangID) -> ORMLang:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Optional[Paginator] = None,
    ) -> List[ORMLang]:
        pass

    @abstractmethod
    async def count(self) -> int:
        pass

    @abstractmethod
    async def create(
        self,
        id: ORMLangID,
        display_name: str,
    ) -> ORMLang:
        pass

    @abstractmethod
    async def update(self, lang: ORMLang):
        pass

    @abstractmethod
    async def delete(self, lang: ORMLang):
        pass


class IEngines(metaclass=ABCMeta):
    @abstractmethod
    async def get_by_id(self, engine_id: ORMEngineID) -> ORMEngine:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Optional[Paginator] = None,
        lang_id: Optional[ORMLangID] = None,
    ) -> List[ORMEngine]:
        pass

    @abstractmethod
    async def count(
        self,
        lang_id: Optional[ORMLangID] = None,
    ) -> int:
        pass

    @abstractmethod
    async def create(
        self,
        id: ORMEngineID,
        display_name: str,
        lang_ids: Optional[List[ORMLangID]] = None,
    ) -> ORMEngine:
        pass

    @abstractmethod
    async def update(self, engine: ORMEngine):
        pass

    @abstractmethod
    async def delete(self, engine: ORMEngine):
        pass

    @abstractmethod
    async def enable_lang(self, engine: ORMEngine, lang_id: ORMLangID):
        pass

    @abstractmethod
    async def disable_lang(self, engine: ORMEngine, lang_id: ORMLangID):
        pass

    @abstractmethod
    async def set_langs(self, engine: ORMEngine, lang_ids: List[ORMLangID]):
        pass


class IImages(metaclass=ABCMeta):

    """Used for managing fuzzer docker images in admin space"""

    @abstractmethod
    async def get_by_id(
        self,
        image_id: str,
        project_id: Optional[str] = None,
    ) -> ORMImage:
        pass

    @abstractmethod
    async def get_by_name(
        self,
        image_name: str,
        project_id: Optional[str],
    ) -> ORMImage:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        project_id: Optional[str] = None,
        image_type: Optional[ORMImageType] = None,
        statuses: Optional[Set[ORMImageStatus]] = None,
        engines: Optional[Set[ORMEngineID]] = None,
    ) -> List[ORMImage]:
        pass

    @abstractmethod
    async def count(
        self,
        project_id: Optional[str] = None,
        image_type: Optional[ORMImageType] = None,
        statuses: Optional[Set[ORMImageStatus]] = None,
        engines: Optional[Set[ORMEngineID]] = None,
    ) -> int:
        pass

    @abstractmethod
    async def create(
        self,
        name: str,
        description: str,
        project_id: Optional[str],
        engines: List[ORMEngineID],
        status: ORMImageStatus,
    ) -> ORMImage:
        pass

    @abstractmethod
    async def update(self, image: ORMImage):
        pass

    @abstractmethod
    async def delete(self, image: ORMImage):
        pass

    @abstractmethod
    async def enable_engine(self, image: ORMImage, engine_id: ORMEngineID):
        pass

    @abstractmethod
    async def disable_engine(self, image: ORMImage, engine_id: ORMEngineID):
        pass

    @abstractmethod
    async def set_engines(self, image: ORMImage, engine_ids: List[ORMEngineID]):
        pass

    @abstractmethod
    @testing_only
    async def generate_builtin_test_set(self, n: int) -> List[ORMImage]:
        pass

    # @abstractmethod
    # @testing_only
    # async def generate_custom_test_set(self, n: int) -> List[ORMImage]:
    #     pass

    @abstractmethod
    @testing_only
    async def create_default(self) -> ORMImage:
        pass


class IProjects(metaclass=ABCMeta):

    """Used for managing projects"""

    @abstractmethod
    async def create(
        self,
        name: str,
        description: str,
        owner_id: str,
        created: str,
        pool_id: Optional[str],
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMProject:
        pass

    @abstractmethod
    async def delete(self, project: ORMProject) -> None:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        project_id: str,
        owner_id: Optional[str] = None,
        include_erasing: bool = False,
    ) -> ORMProject:
        pass

    @abstractmethod
    async def get_by_name(
        self,
        project_name: str,
        owner_id: str,
    ) -> ORMProject:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        owner_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> List[ORMProject]:
        pass

    @abstractmethod
    async def list_internal(self, owner_id: str) -> AsyncIterator[ORMProject]:
        pass

    @abstractmethod
    async def count(
        self,
        owner_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> int:
        pass

    @abstractmethod
    async def update(self, project: ORMProject):
        pass

    @abstractmethod
    async def create_default_project(self, owner_id: str, pool_id: str) -> ORMProject:
        pass

    @abstractmethod
    @testing_only
    async def generate_test_set(self, n: int) -> List[ORMProject]:
        pass

    @abstractmethod
    async def trashbin_empty(self, user_id: str) -> int:
        pass


class IFuzzers(metaclass=ABCMeta):

    """Used for managing fuzzers"""

    @abstractmethod
    async def create(
        self,
        name: str,
        description: str,
        project_id: str,
        engine: ORMEngineID,
        lang: ORMLangID,
        ci_integration: bool,
        created: str,
        active_revision: Optional[ORMRevision],
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMFuzzer:
        pass

    @abstractmethod
    async def delete(self, fuzzer: ORMFuzzer) -> None:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        fuzzer_id: str,
        project_id: Optional[str] = None,
        include_erasing: bool = False,
    ) -> ORMFuzzer:
        pass

    @abstractmethod
    async def get_by_name(
        self,
        fuzzer_name: str,
        project_id: str,
    ) -> ORMFuzzer:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Optional[Paginator] = None,
        project_id: Optional[str] = None,
        engines: Optional[Set[ORMEngineID]] = None,
        langs: Optional[Set[ORMLangID]] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> List[ORMFuzzer]:
        pass

    @abstractmethod
    async def list_internal(self, project_id: str) -> AsyncIterator[ORMFuzzer]:
        pass

    @abstractmethod
    async def count(
        self,
        project_id: Optional[str] = None,
        engines: Optional[Set[ORMEngineID]] = None,
        langs: Optional[Set[ORMLangID]] = None,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> int:
        pass

    @abstractmethod
    async def update(self, fuzzer: ORMFuzzer):
        pass

    @abstractmethod
    @testing_only
    async def create_default_fuzzer(self, project_id: str) -> ORMFuzzer:
        pass

    @abstractmethod
    @testing_only
    async def generate_test_set(self, n: int) -> List[ORMFuzzer]:
        pass

    @abstractmethod
    async def trashbin_list(
        self, paginator: Paginator, project_id: str
    ) -> List[ORMFuzzer]:
        pass

    @abstractmethod
    async def trashbin_count(self, project_id: str) -> int:
        pass

    @abstractmethod
    async def trashbin_empty(
        self, project_id: str, fuzzer_id: Optional[str] = None
    ) -> Tuple[int, int]:
        pass

    @abstractmethod
    async def set_active_revision(
        self,
        fuzzer: ORMFuzzer,
        revision: Optional[ORMRevision],
        start: bool = False,
        restart: bool = False,
    ):
        pass


class IRevisions(metaclass=ABCMeta):

    """Used for managing fuzzer revisions"""

    @abstractmethod
    async def create(
        self,
        name: str,
        description: str,
        binaries: ORMUploadStatus,
        seeds: ORMUploadStatus,
        config: ORMUploadStatus,
        status: ORMRevisionStatus,
        health: ORMHealth,
        fuzzer_id: str,
        image_id: str,
        is_verified: bool,
        created: str,
        cpu_usage: int,
        ram_usage: int,
        tmpfs_size: int,
        feedback: Optional[ORMFeedback] = None,
        last_start_date: Optional[str] = None,
        last_stop_date: Optional[str] = None,
        erasure_date: Optional[str] = None,
        no_backup: bool = False,
    ) -> ORMRevision:
        pass

    @abstractmethod
    async def delete(self, revision: ORMRevision) -> None:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        revision_id: str,
        fuzzer_id: Optional[str] = None,
        include_erasing: bool = False,
    ) -> ORMRevision:
        pass

    @abstractmethod
    async def get_by_name(
        self,
        revision_name: str,
        fuzzer_id: str,
    ) -> ORMRevision:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
        statuses: Optional[List[ORMRevisionStatus]] = None,
        health: Optional[List[ORMHealth]] = None,
    ) -> List[ORMRevision]:
        pass

    # TODO: rewrite all list_internal with filters
    @abstractmethod
    async def list_internal(self, fuzzer_id: str) -> AsyncIterator[ORMRevision]:
        pass

    @abstractmethod
    async def stop_all(self, project_id: str):
        pass

    @abstractmethod
    async def count(
        self,
        fuzzer_id: Optional[str] = None,
        removal_state: Optional[ObjectRemovalState] = None,
        statuses: Optional[List[ORMRevisionStatus]] = None,
        health: Optional[List[ORMHealth]] = None,
    ) -> int:
        pass

    @abstractmethod
    async def update(self, revision: ORMRevision):
        pass

    @abstractmethod
    @testing_only
    async def create_default(
        self,
        fuzzer_id: str,
        image_id: str,
    ) -> ORMRevision:
        pass

    @abstractmethod
    @testing_only
    async def generate_test_set(self, n: int) -> List[ORMRevision]:
        pass


class IStatisticsCrashes(metaclass=ABCMeta):

    ORMStatistics = ORMStatisticsCrashes

    """Crashes statistics"""

    @abstractmethod
    async def inc_crashes(
        self,
        date: str,
        fuzzer_id: str,
        revision_id: str,
        new_total: int = 0,
        new_unique: int = 0,
    ) -> None:
        pass


class IStatisticsLibFuzzer(metaclass=ABCMeta):

    ORMStatistics = ORMStatisticsLibFuzzer

    """Used for managing LibFuzzer statistics"""

    @abstractmethod
    async def create(self, statistics: ORMStatistics) -> ORMStatistics:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ) -> List[ORMStatistics]:
        pass

    @abstractmethod
    async def count(
        self,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ) -> int:
        pass


class IStatisticsAFL(metaclass=ABCMeta):

    """Used for managing AFL statistics"""

    ORMStatistics = ORMStatisticsAFL

    @abstractmethod
    async def create(self, statistics: ORMStatistics) -> ORMStatistics:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ) -> List[ORMStatistics]:
        pass

    @abstractmethod
    async def count(
        self,
        fuzzer_id: Optional[str],
        revision_id: Optional[str],
        group_by: ORMStatisticsGroupBy,
        date_begin: str,
        date_end: Optional[str] = None,
    ) -> int:
        pass


class IStatistics(metaclass=ABCMeta):

    """Used for managing fuzzer statistics"""

    @property
    @abstractmethod
    def crashes(self) -> IStatisticsCrashes:
        pass

    @property
    @abstractmethod
    def libfuzzer(self) -> IStatisticsLibFuzzer:
        pass

    @property
    @abstractmethod
    def afl(self) -> IStatisticsAFL:
        pass


class ICrashes(metaclass=ABCMeta):

    """Used for managing fuzzer crashes"""

    @abstractmethod
    async def create(
        self,
        created: str,
        fuzzer_id: str,
        revision_id: str,
        preview: str,
        input_id: Optional[str],
        input_hash: str,
        type: str,
        brief: str,
        output: str,
        reproduced: bool,
        archived: bool,
        duplicate_count: int,
    ) -> ORMCrash:
        pass

    @abstractmethod
    async def get(
        self,
        crash_id: str,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
    ) -> ORMCrash:
        pass

    @abstractmethod
    async def update_archived(
        self,
        crash_id: str,
        fuzzer_id: str,
        archived: bool,
    ) -> bool:
        pass

    @abstractmethod
    async def inc_duplicate_count(
        self,
        fuzzer_id: str,
        revision_id: str,
        input_hash: str,
    ) -> ORMCrash:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Paginator,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        date_begin: Optional[str] = None,
        date_end: Optional[str] = None,
        archived: Optional[bool] = None,
        reproduced: Optional[bool] = None,
    ) -> List[ORMCrash]:
        pass

    @abstractmethod
    async def count(
        self,
        fuzzer_id: Optional[str] = None,
        revision_id: Optional[str] = None,
        date_begin: Optional[str] = None,
        date_end: Optional[str] = None,
        archived: Optional[bool] = None,
        reproduced: Optional[bool] = None,
    ) -> int:
        pass


class IIntegrationTypes(metaclass=ABCMeta):
    @abstractmethod
    async def get_by_id(
        self,
        integration_type_id: ORMIntegrationTypeID,
    ) -> ORMIntegrationType:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Optional[Paginator] = None,
    ) -> List[ORMIntegrationType]:
        pass

    @abstractmethod
    async def count(self) -> int:
        pass

    @abstractmethod
    async def create(
        self,
        id: ORMIntegrationTypeID,
        display_name: str,
        twoway: bool,
    ) -> ORMIntegrationType:
        pass

    @abstractmethod
    async def update(self, integration_type: ORMIntegrationType):
        pass

    @abstractmethod
    async def delete(self, integration_type: ORMIntegrationType):
        pass


class IIntegrations(metaclass=ABCMeta):

    """Stores integration settings of bug tracking systems"""

    @abstractmethod
    async def get_by_id(
        self,
        integration_id: str,
        project_id: Optional[str] = None,
    ) -> ORMIntegration:
        pass

    @abstractmethod
    async def get_by_name(
        self,
        integration_name: str,
        project_id: str,
    ) -> ORMIntegration:
        pass

    @abstractmethod
    async def get_by_config_id(self, config_id: str) -> ORMIntegration:
        pass

    @abstractmethod
    async def list(
        self,
        paginator: Optional[Paginator] = None,
        project_id: Optional[str] = None,
        statuses: Optional[Set[ORMIntegrationStatus]] = None,
        types: Optional[Set[ORMIntegrationTypeID]] = None,
    ) -> List[ORMIntegration]:
        pass

    @abstractmethod
    async def list_internal(self, project_id: str) -> AsyncIterator[ORMIntegration]:
        pass

    @abstractmethod
    async def count(
        self,
        project_id: Optional[str] = None,
        statuses: Optional[Set[ORMIntegrationStatus]] = None,
        types: Optional[Set[ORMIntegrationTypeID]] = None,
    ) -> int:
        pass

    @abstractmethod
    async def create(
        self,
        name: str,
        project_id: str,
        config_id: str,
        type: ORMIntegrationTypeID,
        status: ORMIntegrationStatus,
        last_error: Optional[str],
        update_rev: str,
        enabled: bool,
        num_undelivered: int,
    ) -> ORMIntegration:
        pass

    @abstractmethod
    async def update(self, integration: ORMIntegration):
        pass

    @abstractmethod
    async def delete(self, integration: ORMIntegration):
        pass

    @abstractmethod
    @testing_only
    async def generate_builtin_test_set(self, n: int) -> List[ORMIntegration]:
        pass


class IDatabase(metaclass=ABCMeta):

    """Used for managing database"""

    @staticmethod
    @abstractmethod
    async def create(settings: AppSettings):
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @property
    @abstractmethod
    def unsent_mq(self) -> IUnsentMessages:
        pass

    @property
    @abstractmethod
    def cookies(self) -> ICookies:
        pass

    @property
    @abstractmethod
    def users(self) -> IUsers:
        pass

    @property
    @abstractmethod
    def lockout(self) -> IUserLockout:
        pass

    @property
    @abstractmethod
    def projects(self) -> IProjects:
        pass

    @property
    @abstractmethod
    def fuzzers(self) -> IFuzzers:
        pass

    @property
    @abstractmethod
    def revisions(self) -> IRevisions:
        pass

    @property
    @abstractmethod
    def images(self) -> IImages:
        pass

    @property
    @abstractmethod
    def engines(self) -> IEngines:
        pass

    @property
    @abstractmethod
    def langs(self) -> ILangs:
        pass

    @property
    @abstractmethod
    def statistics(self) -> IStatistics:
        pass

    @property
    @abstractmethod
    def crashes(self) -> ICrashes:
        pass

    @property
    @abstractmethod
    def integrations(self) -> IIntegrations:
        pass

    @property
    @abstractmethod
    def integration_types(self) -> IIntegrationTypes:
        pass

    @abstractmethod
    @testing_only
    async def truncate_all_collections(self) -> None:
        pass
