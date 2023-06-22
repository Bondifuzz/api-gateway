from typing import Optional

from pydantic import BaseModel

from .error_codes import *

API_ERROR_MESSAGES = {
    # general
    E_NO_ERROR: "No error. Operation successful",
    E_INTERNAL_ERROR: "Internal error occurred. Please, try again later or contact support service",
    E_WRONG_REQUEST: "Wrong request parameters",
    # access
    E_AUTHORIZATION_REQUIRED: "Authorization required",
    E_SESSION_NOT_FOUND: "Session not found or expired",
    E_LOGIN_FAILED: "Login failed: Invalid username or password",
    E_ACCESS_DENIED: "Access denied",
    E_ADMIN_REQUIRED: "Administrator rights required",
    E_SYSTEM_ADMIN_REQUIRED: "System administrator rights required",
    E_CLIENT_ACCOUNT_REQUIRED: "Please, use client account to manage data on this route",
    E_DEVICE_COOKIE_LOCKOUT: "Account locked out. Please, try again later",
    E_DEVICE_COOKIE_INVALID: "Provided device cookie is invalid",
    # Security: CSRF
    E_CSRF_TOKEN_MISSING: "CSRF token is missing. Ensure it's present in both cookies and request headers",
    E_CSRF_TOKEN_MISMATCH: "Provided CSRF tokens in cookies and request headers do not match",
    E_CSRF_TOKEN_INVALID: "Provided CSRF token is invalid or expired",
    E_CSRF_TOKEN_USER_MISMATCH: "Provided CSRF token does not match the current user",
    # user
    E_USER_NOT_FOUND: "Requested user does not exist",
    E_USER_EXISTS: "User with this name already exists",
    E_USER_DELETED: "Unable to perform operation, because user is deleted",
    E_USER_NOT_DELETED: "Can't restore user that not deleted",
    E_USER_BEING_ERASED: "Unable to perform operation, because user is being erased",
    E_ACCOUNT_NOT_CONFIRMED: "Account is not activated. Please, check your email/telephone for activation link",
    E_ACCOUNT_DISABLED: "Account is disabled. Please, contact support service to get more information",
    E_WRONG_PASSWORD: "Wrong password",
    # project
    E_PROJECT_NOT_FOUND: "Requested project does not exist",
    E_PROJECT_EXISTS: "Project with this name already exists",
    E_PROJECT_DELETED: "Unable to perform operation, because project is deleted",
    E_PROJECT_NOT_DELETED: "Can't restore project that not deleted",
    E_PROJECT_BEING_ERASED: "Unable to perform operation, because project is being erased",
    E_POOL_NOT_FOUND: "Resource pool not found",
    E_POOL_EXISTS: "Resource pool already exists",
    E_POOL_LOCKED: "Resource pool is being changed now. Please, try again later",
    E_DEFAULT_PROJECT_IMMUTABLE: "Default project can not be modified or deleted",
    E_PROJECT_DELETE_ERROR: "Unable to delete this project",
    E_CPU_RAM_MULTIPLICITY_BROKEN: "The amount of RAM should be a multiple of the number of processor cores",
    E_NODE_CPU_INVALID: "Invalid number of cpu cores to allocate for node",
    E_NODE_RAM_INVALID: "Invalid amount of memory to allocate for node",
    E_INVALID_MEM_PER_CORE: "Invalid ratio of provided cpu and ram",
    # pool
    E_INVALID_NODE_GROUP: "Invalid node group for this platform type",
    # fuzzer
    E_FUZZER_NOT_FOUND: "Requested fuzzer does not exist",
    E_FUZZER_EXISTS: "Fuzzer with this name already exists",
    E_FUZZER_DELETED: "Unable to perform operation, because fuzzer is deleted",
    E_FUZZER_NOT_DELETED: "Can't restore fuzzer that not deleted",
    E_FUZZER_BEING_ERASED: "Unable to perform operation, because fuzzer is being erased",
    E_FUZZER_LANG_MISMATCH: "Selected docker image has a programming language different from specified in request",
    E_FUZZER_ENGINE_MISMATCH: "Selected docker image has a fuzzer engine different from specified in request",
    E_FUZZER_NOT_IN_TRASHBIN: "Fuzzer not in trashbin",
    E_ACTIVE_REVISION_NOT_FOUND: "Active revision not selected",
    # revision
    E_REVISION_NOT_FOUND: "Requested fuzzer revision does not exist",
    E_REVISION_EXISTS: "Fuzzer revision with this name already exists",
    E_REVISION_DELETED: "Unable to perform operation, because revision is deleted",
    E_REVISION_NOT_DELETED: "Can't restore revision that not deleted",
    E_REVISION_BEING_ERASED: "Unable to perform operation, because revision is being erased",
    E_REVISION_CAN_NOT_BE_CHANGED: "Specified type of data can't be changed in current state",
    E_REVISION_IS_NOT_RUNNING: "Revision is not running",
    E_REVISION_CAN_ONLY_RESTART: "Revision in this state can be only restarted",
    E_REVISION_ALREADY_RUNNING: "Revision already running",
    E_MUST_UPLOAD_BINARIES: "You must upload at least binaries to run revision",
    E_NO_POOL_TO_USE: "Current project doesn't have a resource pool. Please, create it to continue",
    E_CPU_USAGE_INVALID: "Invalid CPU usage specified for the revision. Check it does not exceed pool limits",
    E_RAM_USAGE_INVALID: "Invalid RAM usage specified for the revision. Check it does not exceed pool limits",
    E_TMPFS_SIZE_INVALID: "Invalid TmpFS size specified for the revision. Check it does not exceed pool limits",
    E_TOTAL_RAM_USAGE_INVALID: "Sum of TmpFS size and RAM usage exceeds pool limits",
    E_SOURCE_REVISION_NOT_FOUND: "Source revision not found",
    E_TARGET_REVISION_NOT_FOUND: "Destination revision not found",
    E_CORPUS_OVERWRITE_FORBIDDEN: "Corpus files overwrite is forbidden, if target revision has had any runs",
    E_NO_CORPUS_FOUND: "Corpus files were not found",
    E_COPY_SOURCE_TARGET_SAME: "Source and target revision IDs are the same",
    # image
    E_IMAGE_NOT_FOUND: "Requested image does not exist",
    E_IMAGE_EXISTS: "Image with this name already exists",
    E_IMAGE_NOT_READY: "Specified image can't be used to run fuzzer",
    E_ENGINE_LANG_INCOMPATIBLE: "This fuzzer engine is not compatible with programming language specified",
    # engine
    E_ENGINE_NOT_FOUND: "Requested engine does not exist",
    E_ENGINE_EXISTS: "Engine with this id already exists",
    E_ENGINE_LANG_NOT_ENABLED: "Specified lang is not enabled for this engine",
    E_ENGINE_LANG_ALREADY_ENABLED: "Specified lang already enabled for this engine",
    E_ENGINES_INVALID: "Provided invalid engines: %s",
    E_ENGINE_IN_USE_BY: "Engine is in use by: %s",
    # lang
    E_LANG_NOT_FOUND: "Requested language does not exist",
    E_LANG_EXISTS: "Language with this id already exists",
    E_LANGS_INVALID: "Provided invalid langs: %s",
    E_LANG_IN_USE_BY: "Lang is in use by: %s",
    # integration
    E_INTEGRATION_NOT_FOUND: "Requested integration does not exist",
    E_INTEGRATION_EXISTS: "Integration with this name already exists",
    E_INTEGRATION_TYPE_MISMATCH: "Integration type in request body does not match the actual one",
    # integration type
    E_INTEGRATION_TYPE_NOT_FOUND: "Requested integration type does not exists",
    E_INTEGRATION_TYPE_EXISTS: "Integration with this type already exists",
    E_INTEGRATION_TYPE_IN_USE_BY: "Integration type is in use by: %s",
    # crash
    E_CRASH_NOT_FOUND: "Requested crash does not exist",
    # statistics
    E_STATISTICS_NOT_FOUND: "Requested statistics record does not exist",
    # files
    E_UPLOAD_FAILURE: "Failed to upload file. Re-upload required",
    E_FILE_NOT_FOUND: "Requested file does not exist",
    E_FILE_TOO_LARGE: "Provided file is too large. Please, fit into upload limit",
    E_FILE_NOT_ARCHIVE: "Provided file is not recognized as archive. Please, ensure you're uploading '.tar.gz' file",
    E_JSON_FILE_IS_INVALID: "Provided file is not recognized as json. Please, ensure you're uploading valid '.json' file",
}


class ErrorModel(BaseModel):
    message: str
    code: str
    params: Optional[list]

    def __str__(self) -> str:
        if self.params is None:
            return f"ErrorModel[code={self.code}, message={self.message}]"
        else:
            return f"ErrorModel[code={self.code}, message={self.message}, params={self.params}]"  # fmt: skip


class DependencyException(Exception):
    response_code: int
    error_code: str

    def __init__(self, response_code: int, error_code: str):
        self.response_code = response_code
        self.error_code = error_code


def error_msg(*error_codes):
    messages = [API_ERROR_MESSAGES[ec] for ec in error_codes]
    return "<br>".join(messages)


def error_model(error_code: str, params: Optional[list] = None):
    return ErrorModel(
        message=API_ERROR_MESSAGES[error_code],
        code=error_code,
        params=params,
    )


def error_body(error_code: str):
    return {
        "code": error_code,
        "message": API_ERROR_MESSAGES[error_code],
    }
