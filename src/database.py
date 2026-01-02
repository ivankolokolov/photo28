"""Настройка подключения к базе данных."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.config import settings
from src.models.base import Base


# Создаём асинхронный движок
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Включить для отладки SQL-запросов
)

# Фабрика сессий
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Инициализация базы данных (создание таблиц)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получить сессию базы данных."""
    async with async_session() as session:
        yield session

