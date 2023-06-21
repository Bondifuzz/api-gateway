from fastapi import APIRouter

from . import (
    config,
    crashes,
    fuzzers,
    images,
    integrations,
    projects,
    revisions,
    statistics,
    users,
    pools,
)

router = APIRouter()
fuzzers.router.include_router(revisions.router)
fuzzers.router.include_router(crashes.router)
fuzzers.router.include_router(statistics.router)
projects.router.include_router(fuzzers.router)
projects.router.include_router(integrations.router)
projects.router.include_router(images.router)
users.router.include_router(projects.router)
users.router.include_router(pools.router)
router.include_router(users.router)
router.include_router(config.router)
