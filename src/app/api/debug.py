"""Эндпоинты для генерации ошибок и задержек. Подключаются только при ENABLE_DEBUG_ENDPOINTS=true."""

import logging
import time

from fastapi import APIRouter

router = APIRouter(prefix="/debug", tags=["debug"])
logger = logging.getLogger(__name__)


@router.get("/error")
def raise_error():
    logger.error("about to raise a simulated error")
    raise RuntimeError("Simulated failure for observability testing")


@router.get("/slow")
def slow(ms: int = 1500):
    ms = min(ms, 10_000)
    logger.info("simulating slow request", extra={"sleep_ms": ms})
    time.sleep(ms / 1000)
    return {"slept_ms": ms}
