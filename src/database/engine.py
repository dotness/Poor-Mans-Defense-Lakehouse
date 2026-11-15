import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
try:
    from src.config.settings import settings
    from src.database.base import Base
except ImportError:
    from config.settings import settings
    from database.base import Base

logger = logging.getLogger(__name__)

# Format async postgres URL
# Example: postgresql+asyncpg://artemis:artemis_secure_password@localhost:5433/artemis
DATABASE_URL = (
    f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

engine = None
AsyncSessionLocal = None


def get_engine():
    global engine, AsyncSessionLocal
    if engine is None:
        engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return engine


async def init_database():
    """Initializes the database engine and ensures connection."""
    try:
        get_engine()
        logger.info("Initialized async database engine.")
    except Exception as e:
        logger.warning(f"Could not connect to database on startup: {e}")


async def create_tables():
    """Creates tables if not present."""
    eng = get_engine()
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified.")
    except Exception as e:
        logger.warning(f"Could not verify/create tables: {e}")


async def close_database():
    """Closes the async database engine."""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None
        logger.info("Closed async database engine.")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an AsyncSession."""
    get_engine()
    async with AsyncSessionLocal() as session:
        yield session
