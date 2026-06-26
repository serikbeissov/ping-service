from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    # naive UTC — единый формат и в БД (SQLite DateTime без tz), и в сравнениях,
    # чтобы не смешивать offset-aware и offset-naive datetime
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Group(Base):
    """Раздел устройств, напр. «Камеры офис 1», «Контроллеры отеля»."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)

    # при удалении раздела устройства не удаляются, а становятся «без раздела»
    # (group_id -> NULL); это поведение по умолчанию для one-to-many в SQLAlchemy
    devices: Mapped[list["Device"]] = relationship(
        back_populates="group",
        order_by="Device.name",
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # порог latency (мс) для этого устройства; None -> берётся глобальный
    latency_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # тип проверки: icmp | tcp | http
    check_type: Mapped[str] = mapped_column(String(8), default="icmp")
    # порт для tcp; для http — опционально (иначе 80/443 по схеме)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # текущее состояние
    is_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_change: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # счётчик подряд неуспешных пингов (анти-флаппинг)
    fail_streak: Mapped[int] = mapped_column(Integer, default=0)
    # «медленный отклик»: latency выше порога
    is_slow: Mapped[bool] = mapped_column(Boolean, default=False)
    slow_streak: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped["Group | None"] = relationship(back_populates="devices")


class CheckResult(Base):
    """История пингов для расчёта uptime % и спарклайнов."""

    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    is_up: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class Incident(Base):
    """Инцидент: период недоступности (down) или замедления (slow) устройства."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8), default="down")  # down | slow
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # роль: admin (полный доступ) | viewer (только просмотр)
    role: Mapped[str] = mapped_column(String(16), default="admin")


class AppSettings(Base):
    """Единственная строка с глобальными настройками сервиса."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    default_interval: Mapped[int] = mapped_column(Integer, default=30)
    fail_threshold: Mapped[int] = mapped_column(Integer, default=2)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_bot_token: Mapped[str] = mapped_column(String(255), default="")
    telegram_chat_id: Mapped[str] = mapped_column(String(120), default="")
    # сколько суток хранить историю пингов
    history_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    # глобальный порог latency (мс); 0 = выключено
    latency_threshold_ms: Mapped[int] = mapped_column(Integer, default=0)
