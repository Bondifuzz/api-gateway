import prometheus_client
from starlette.status import *

from api_gateway.app.database.orm import ORMUser
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from ...depends import Operation, current_admin
from ...error_codes import *
from ...error_model import ErrorModel, error_msg
from ...utils import log_operation_error_to, log_operation_success_to

router = APIRouter(
    tags=["metrics (admin)"],
    responses={
        HTTP_401_UNAUTHORIZED: {
            "model": ErrorModel,
            "description": error_msg(E_AUTHORIZATION_REQUIRED),
        },
        HTTP_403_FORBIDDEN: {
            "model": ErrorModel,
            "description": error_msg(E_ADMIN_REQUIRED),
        },
    },
)


def log_operation_success(operation: str, **kwargs):
    log_operation_success_to("api.metrics", operation, **kwargs)


def log_operation_error(operation: str, reason: str, **kwargs):
    log_operation_error_to("api.metrics", operation, reason, **kwargs)


@router.get("/metrics")
async def metrics(
    operation: str = Depends(Operation("Get metrics")),
    admin: ORMUser = Depends(current_admin),
):
    log_operation_success(operation, caller=admin.name)
    return PlainTextResponse(content=prometheus_client.generate_latest())
