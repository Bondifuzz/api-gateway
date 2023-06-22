from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from argon2 import PasswordHasher

from api_gateway.app.database.abstract import IUsers
from api_gateway.app.database.errors import (
    DBUserAlreadyExistsError,
    DBUserNotFoundError,
)
from api_gateway.app.database.orm import ORMUser
from api_gateway.app.settings import DefaultUserSettings, SystemAdminSettings
from api_gateway.app.utils import ObjectRemovalState, rfc3339_now, testing_only

from .base import DBBase
from .utils import dbkey_to_id, id_to_dbkey, maybe_already_exists, maybe_unknown_error

if TYPE_CHECKING:
    from typing import List

    from aioarangodb.collection import StandardCollection
    from aioarangodb.cursor import Cursor
    from aioarangodb.database import StandardDatabase

    from api_gateway.app.database.orm import Paginator
    from api_gateway.app.settings import CollectionSettings


class DBUsers(DBBase, IUsers):

    _col_users: StandardCollection

    def __init__(self, db: StandardDatabase, collections: CollectionSettings):
        self._col_users = db[collections.users]
        super().__init__(db, collections)

    @maybe_unknown_error
    @maybe_already_exists(DBUserAlreadyExistsError)
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
        user = ORMUser(
            id="",  # filled from meta
            name=name,
            display_name=display_name,
            password_hash=password_hash,
            is_confirmed=is_confirmed,
            is_disabled=is_disabled,
            is_admin=is_admin,
            is_system=is_system,
            email=email,
            erasure_date=erasure_date,
            no_backup=no_backup,
        )

        meta = await self._col_users.insert(user.dict(exclude={"id"}))
        user.id = meta["_key"]

        return user

    @maybe_unknown_error
    async def get_by_id(
        self,
        user_id: str,
    ) -> ORMUser:

        user_dict = await self._col_users.get(user_id)

        if not user_dict:
            raise DBUserNotFoundError()

        return ORMUser(**dbkey_to_id(user_dict))

    @maybe_unknown_error
    async def get_by_name(
        self,
        user_name: str,
    ) -> ORMUser:

        filters = {"name": user_name}

        cursor: Cursor = await self._col_users.find(filters, limit=1)

        if cursor.empty():
            raise DBUserNotFoundError()

        return ORMUser(**dbkey_to_id(cursor.pop()))

    @maybe_unknown_error
    @maybe_already_exists(DBUserAlreadyExistsError)
    async def update(self, user: ORMUser):
        await self._col_users.replace(id_to_dbkey(user.dict()), silent=True)

    @maybe_unknown_error
    async def delete(self, user: ORMUser):

        # fmt: off
        query, variables = """
            FOR project IN @@collection
                FILTER project.owner_id == @user_id
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._collections.projects,
            "user_id": user.id,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        projects_in_db: int = cursor.pop()
        if projects_in_db != 0:
            raise Exception("TODO: ")

        # TODO: cookies
        await self._col_users.delete(user.id)

    @staticmethod
    def _apply_filter_options(
        query: str,
        variables: dict,
        removal_state: Optional[ObjectRemovalState] = None,
    ):
        assert "<filter-options>" in query
        filters = list()

        if removal_state is None:
            removal_state = ObjectRemovalState.present

        if removal_state == ObjectRemovalState.present:
            filters.append("FILTER user.erasure_date == null")
        elif removal_state == ObjectRemovalState.trash_bin:
            filters.append("FILTER user.erasure_date != null")
            filters.append("FILTER user.erasure_date > @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.erasing:
            filters.append("FILTER user.erasure_date != null")
            filters.append("FILTER user.erasure_date <= @date_now")
            variables["date_now"] = rfc3339_now()
        elif removal_state == ObjectRemovalState.visible:
            filters.append(
                "FILTER user.erasure_date == null OR user.erasure_date > @date_now"
            )
            variables["date_now"] = rfc3339_now()

        if filters:
            query = query.replace("<filter-options>", "\n\t\t".join(filters))
        else:
            query = query.replace("<filter-options>", "")

        return query, variables

    @maybe_unknown_error
    async def list(
        self,
        paginator: Paginator,
        removal_state: Optional[ObjectRemovalState] = None,
    ) -> List[ORMUser]:

        # fmt: off
        query, variables = """
            FOR user in @@collection
                <filter-options>
                SORT user.is_system DESC,
                     user.is_admin DESC,
                     user.name ASC
                LIMIT @offset, @limit
                RETURN MERGE(user, {
                    "id": user._key,
                })
        """, {
            "@collection": self._collections.users,
            "offset": paginator.offset,
            "limit": paginator.limit,
        }
        # fmt: on

        query, variables = self._apply_filter_options(query, variables, removal_state)
        cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMUser(**doc) async for doc in cursor]

    @maybe_unknown_error
    async def count(self, removal_state: Optional[ObjectRemovalState] = None) -> int:

        # fmt: off
        query, variables = """
            FOR user IN @@collection
                <filter-options>
                COLLECT WITH COUNT INTO length
                RETURN length
        """, {
            "@collection": self._col_users.name,
        }
        # fmt: on

        query, variables = self._apply_filter_options(query, variables, removal_state)
        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return cursor.pop()

    @maybe_unknown_error
    async def create_system_admin(self, settings: SystemAdminSettings) -> ORMUser:

        filters = {"name": settings.username}
        cursor: Cursor = await self._col_users.find(filters, limit=1)

        if not cursor.empty():
            raise DBUserAlreadyExistsError()

        ph = PasswordHasher()
        username = settings.username
        password = settings.password
        email = settings.email

        return await self.create(
            name=username,
            display_name=username.capitalize(),
            password_hash=ph.hash(password),
            is_confirmed=True,
            is_disabled=False,
            is_admin=True,
            is_system=True,
            email=email,
        )

    @maybe_unknown_error
    async def create_default_user(self, settings: DefaultUserSettings) -> ORMUser:

        filters = {"name": settings.username}
        cursor: Cursor = await self._col_users.find(filters, limit=1)

        if not cursor.empty():
            raise DBUserAlreadyExistsError()

        ph = PasswordHasher()
        username = settings.username
        password = settings.password
        email = settings.email

        return await self.create(
            name=username,
            display_name=username.capitalize(),
            password_hash=ph.hash(password),
            is_confirmed=True,
            is_disabled=False,
            is_admin=False,
            is_system=False,
            email=email,
        )

    @testing_only
    @maybe_unknown_error
    async def generate_test_set(self, n: int, prefix: str) -> List[ORMUser]:

        # Password for every user (="user")
        password = "argon2id$v=19$m=102400,t=2,p=8$OxoDTuWRrgHo6nLX0Fvk6g$jw6IHL7pEjVkqoHugxoGmg"  # cspell:disable-line

        # fmt: off
        query, variables = """
            FOR i in 1..@count
                INSERT {
                    name: CONCAT(@prefix, "_user", i),
                    display_name: CONCAT(@prefix, "_User", i),
                    password_hash: @password,
                    email: CONCAT("User", i, "@example.com"),
                    is_confirmed: true,
                    is_disabled: false,
                    is_admin: false,
                    is_system: false,
                } INTO @@collection

                RETURN MERGE(NEW, {
                    "id": NEW._key
                })
        """, {
            "@collection": self._collections.users,
            "password": password,
            "count": n,
            "prefix": prefix,
        }
        # fmt: on

        cursor: Cursor = await self._db.aql.execute(query, bind_vars=variables)
        return [ORMUser(**doc) async for doc in cursor]
