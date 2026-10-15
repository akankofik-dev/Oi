"""Remote Android routers."""

from __future__ import annotations

from fastapi import APIRouter

from oi.api.routers.mobile.install import router as install_router
from oi.api.routers.mobile.shell_ws import router as shell_router
from oi.api.routers.mobile.status import router as status_router
from oi.api.routers.mobile.stream import router as stream_router

router = APIRouter()
router.include_router(status_router)
router.include_router(install_router)
router.include_router(stream_router)
router.include_router(shell_router)

__all__ = ["router"]
