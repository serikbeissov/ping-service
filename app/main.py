import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from . import crud
from .auth import hash_password
from .config import settings
from .database import Base, SessionLocal, engine
from .models import User
from .monitor import monitor_loop
from .routers import admin, api, auth_routes, dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")

BASE_DIR = Path(__file__).resolve().parent


# лёгкая «миграция» для SQLite: добавляем недостающие колонки в существующую БД
# (create_all не меняет уже созданные таблицы)
_MIGRATIONS = {
    "devices": [
        ("latency_threshold", "INTEGER"),
        ("is_slow", "BOOLEAN NOT NULL DEFAULT 0"),
        ("slow_streak", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "app_settings": [
        ("latency_threshold_ms", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


def _ensure_columns() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _MIGRATIONS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    log.info("Миграция: добавлена колонка %s.%s", table, name)


def init_db() -> None:
    """Создаёт таблицы, сид админа и строку настроек при первом запуске."""
    # гарантируем каталог для sqlite
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username=settings.admin_user,
                    password_hash=hash_password(settings.admin_password),
                )
            )
            db.commit()
            log.info("Создан админ: %s", settings.admin_user)
        app_settings = crud.get_settings(db)
        # подтягиваем дефолты из env, если в БД пусто
        if not app_settings.telegram_bot_token and settings.telegram_bot_token:
            app_settings.telegram_bot_token = settings.telegram_bot_token
        if not app_settings.telegram_chat_id and settings.telegram_chat_id:
            app_settings.telegram_chat_id = settings.telegram_chat_id
        if app_settings.default_interval is None:
            app_settings.default_interval = settings.default_interval
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop = asyncio.Event()
    task = asyncio.create_task(monitor_loop(stop))
    log.info("%s запущен", settings.app_title)
    try:
        yield
    finally:
        stop.set()
        await task


app = FastAPI(title=settings.app_title, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(dashboard.router)
app.include_router(auth_routes.router)
app.include_router(admin.router)
app.include_router(api.router)
