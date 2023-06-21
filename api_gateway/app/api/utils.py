from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from devtools import debug
from starlette.status import *

from .error_codes import *

if TYPE_CHECKING:
    from api_gateway.app.database.orm import ORMUser
    from .error_model import ErrorModel



def filter_sensitive_data(output: str):

    #
    # Filter output of devtools
    # Inspect [key='value'] entries
    #

    pattern = (
        r"(password|token)"  # possible keys
        r"([\s=]+)"  # delimeters (space and '=')
        r"'(.+)'"  # any value
    )

    # Final result: [key='<REDACTED>']
    output = re.sub(pattern, r"\1\2'<REDACTED>'", output)

    #
    # Filter dictionaries
    # Inspect {'key': 'value'} entries
    #

    pattern = (
        r"('password|token')"  # possible keys
        r"([\s:]+)"  # delimeters (space and ':')
        r"'(.+)'"  # any value
    )

    # Final result: {'key': '<REDACTED>'}
    output = re.sub(pattern, r"\1\2'<REDACTED>'", output)

    return output


def log_operation_debug_info_to(
    logger_name: str,
    operation: str,
    info: Any,
):
    logger = logging.getLogger(logger_name)
    if not logger.isEnabledFor(logging.DEBUG):
        return

    text = "Debug info for operation '%s':\n%s"
    output = debug.format(info).str(highlight=True)
    redacted_output = filter_sensitive_data(output)
    logger.debug(text, operation, redacted_output)


def log_operation_success_to(
    logger_name: str,
    operation: str,
    **kwargs,
):
    logger = logging.getLogger(logger_name)
    kw_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info("[OK] Operation='%s', %s", operation, kw_str)


def log_operation_error_to(
    logger_name: str,
    operation: str,
    reason: ErrorModel,
    **kwargs,
):
    logger = logging.getLogger(logger_name)
    kw_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info("[FAILED] Operation='%s', reason=%s, %s", operation, reason, kw_str)


def check_user_status(user: ORMUser):

    # Do not return 404
    # to avoid username bruteforcing
    if user.erasure_date:
        return (HTTP_401_UNAUTHORIZED, E_LOGIN_FAILED)

    if not user.is_confirmed:
        return (HTTP_403_FORBIDDEN, E_ACCOUNT_NOT_CONFIRMED)

    if user.is_disabled:
        return (HTTP_403_FORBIDDEN, E_ACCOUNT_DISABLED)

    return (HTTP_200_OK, E_NO_ERROR)


def pg_size_settings():
    return {
        "ge": 10,  # Minimal count of records in one page
        "le": 200,  # Maximum count of records in one page
        "default": 100,  # Default count of records in one page
    }


def pg_num_settings():
    return {
        "ge": 0,  # Minimal number of page
        "default": 0,  # Default number of page
    }


def max_length(value: int):
    return {
        "min_length": 1,  # Minimal data length
        "max_length": value,  # Maximum data length
    }


def normalize_date(value: Optional[str]) -> Optional[str]:

    """
    Convert input dates to one format(acceptable by arango)

    0000-00-00T00:00:00Z
    0000-00-00T00:00:00+00:00
    0000-00-00T00:00:00-00:00
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Date must be string")

    if value.endswith("Z"):
        value = value[:-1]

    date = datetime.fromisoformat(value)
    value = date.replace(microsecond=0).isoformat()

    # python never add "Z" at end
    if date.tzinfo is None:
        value += "Z"
    elif value.endswith("+00:00"):
        value = value[:-6] + "Z"

    return value
