import logging
import os
import base64
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends

try:
    from src.config.settings import settings
    from src.database.engine import init_database, create_tables, close_database
    from src.security.middleware import authenticate_user
except ImportError:
    from config.settings import settings
    from database.engine import init_database, create_tables, close_database
    from security.middleware import authenticate_user

logger = logging.getLogger("artemis.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. OpenTelemetry & Pluggable Langfuse Tracing
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            auth = base64.b64encode(
                f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
            ).decode()

            provider = TracerProvider()
            provider.add_span_processor(
                SimpleSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=f"{settings.langfuse_host}/api/public/otel/v1/traces",
                        headers={"Authorization": f"Basic {auth}"},
                    )
                )
            )
            trace.set_tracer_provider(provider)
            logger.info("Langfuse OpenTelemetry distributed tracing initialized.")
        except Exception as e:
            logger.warning(f"Could not initialize Langfuse tracing: {e}")

    # 2. Database Engine & Table Verification
    await init_database()
    await create_tables()

    # 2b. Start Automated Retention TTL Cleanup Scheduler
    try:
        from src.domains.retention.operations.cleanup_workflow import (
            start_background_cleanup_scheduler,
            stop_background_cleanup_scheduler,
        )
        start_background_cleanup_scheduler()
    except Exception as e:
        logger.warning(f"Could not start retention background scheduler: {e}")

    logger.info("Artemis FastAPI Gateway started successfully.")
    yield

    # 3. Teardown
    try:
        from src.domains.retention.operations.cleanup_workflow import stop_background_cleanup_scheduler
        await stop_background_cleanup_scheduler()
    except Exception:
        pass
    await close_database()
    logger.info("Artemis FastAPI Gateway shutdown complete.")


app = FastAPI(
    title="Artemis Unified Domain Gateway",
    version="0.3.0",
    description="Domain-Driven Architecture aligned with uservice-template",
    lifespan=lifespan,
    dependencies=[Depends(authenticate_user)],
)

# Domain Routers
from src.domains.auth.api.router import router as auth_router
from src.domains.analytics.api.router import router as analytics_router
from src.domains.ai.api.router import router as ai_router
from src.domains.ingestion.api.router import router as ingestion_router
from src.domains.graph.api.router import router as graph_router
from src.domains.pipeline.api.router import router as pipeline_router
from src.domains.pipeline.api.routes import router as project_pipeline_router
from src.domains.project.api.routes import router as project_router
from src.domains.discovery.api.router import router as discovery_router
from src.domains.retention.api.router import router as retention_router

app.include_router(auth_router)
app.include_router(analytics_router)
app.include_router(ai_router)
app.include_router(ingestion_router)
app.include_router(graph_router)
app.include_router(pipeline_router)
app.include_router(project_pipeline_router)
app.include_router(project_router)
app.include_router(discovery_router)
app.include_router(retention_router)




@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "HEALTHY", "version": "0.3.0", "service": "artemis-gateway"}
