import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.api import customers, debug, orders
from app.config import Settings, get_settings
from app.db import Base, get_session, make_engine
from app.logging_config import request_id_var, setup_logging
from app.metrics import HTTP_LATENCY, HTTP_REQUESTS

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.app_env)

    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        logger.info("application started", extra={"app_env": settings.app_env})
        yield
        engine.dispose()
        logger.info("application stopped")

    app = FastAPI(title="test.logger", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)

    app.include_router(customers.router)
    app.include_router(orders.router)
    if settings.enable_debug_endpoints:
        app.include_router(debug.router)

    @app.middleware("http")
    async def observe_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        except Exception:
            # Отвечаем 500 сами, чтобы uvicorn не дублировал стектрейс без request_id
            logger.exception("unhandled exception")
            response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get("route")
            route_path = route.path if route else "unmatched"
            if route_path not in ("/metrics", "/health"):
                HTTP_REQUESTS.labels(request.method, route_path, str(status)).inc()
                HTTP_LATENCY.labels(request.method, route_path).observe(duration)
                log = logger.warning if status >= 500 else logger.info
                log(
                    "http request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(duration * 1000, 2),
                    },
                )
            request_id_var.reset(token)

    @app.get("/health", tags=["system"])
    def health(session: Session = Depends(get_session)):
        session.execute(text("SELECT 1"))
        return {"status": "ok", "env": settings.app_env}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
