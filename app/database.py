from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

# check_same_thread=False — БД дёргается из фонового asyncio-цикла и из обработчиков
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI-зависимость: сессия БД на запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
