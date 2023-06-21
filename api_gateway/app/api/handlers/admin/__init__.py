from fastapi import APIRouter

from . import images, metrics, users, engines, langs, integration_types, pools

router = APIRouter(prefix="/admin")
router.include_router(metrics.router)
router.include_router(images.router)
router.include_router(users.router)
router.include_router(engines.router)
router.include_router(langs.router)
router.include_router(integration_types.router)
router.include_router(pools.router)
