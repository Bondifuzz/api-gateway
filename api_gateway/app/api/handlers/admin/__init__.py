from fastapi import APIRouter

from . import engines, images, integration_types, langs, metrics, pools, users

router = APIRouter(prefix="/admin")
router.include_router(metrics.router)
router.include_router(images.router)
router.include_router(users.router)
router.include_router(engines.router)
router.include_router(langs.router)
router.include_router(integration_types.router)
router.include_router(pools.router)
