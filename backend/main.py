from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.data import router as data_router
from app.api.health import router as health_router
from app.api.import_data import router as import_router
from app.api.schema import router as schema_router
from app.api.sessions import router as sessions_router
from app.core.config import settings
from app.core.logging import RequestLoggingMiddleware, configure_logging, get_logger
from app.db.database import check_database_connection
from app.services.vector_store import initialize_vector_store
from app.utils.error_handling import register_error_handlers

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup.checks.start")
    check_database_connection()
    initialize_vector_store()
    logger.info("startup.checks.ready")
    yield
    logger.info("shutdown.complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(chat_router, prefix="/api")
    app.include_router(data_router, prefix="/api")
    app.include_router(import_router, prefix="/api")
    app.include_router(schema_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    return app


app = create_app()
