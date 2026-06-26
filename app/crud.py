import re
from datetime import timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .models import AppSettings, CheckResult, Device, Group, User, utcnow


# ---- Settings ----

def get_settings(db: Session) -> AppSettings:
    obj = db.query(AppSettings).first()
    if obj is None:
        obj = AppSettings()
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj


# ---- Groups ----

def list_groups(db: Session) -> list[Group]:
    return db.query(Group).order_by(Group.order, Group.name).all()


def get_group(db: Session, group_id: int) -> Group | None:
    return db.get(Group, group_id)


def create_group(db: Session, name: str, description: str = "", order: int = 0) -> Group:
    group = Group(name=name, description=description, order=order)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def update_group(db: Session, group: Group, **fields) -> Group:
    for key, value in fields.items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return group


def delete_group(db: Session, group: Group) -> None:
    # устройства остаются, просто теряют раздел
    for device in group.devices:
        device.group_id = None
    db.delete(group)
    db.commit()


# ---- Devices ----

def list_devices(db: Session) -> list[Device]:
    return db.query(Device).order_by(Device.name).all()


def get_device(db: Session, device_id: int) -> Device | None:
    return db.get(Device, device_id)


def create_device(db: Session, **fields) -> Device:
    device = Device(**fields)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def update_device(db: Session, device: Device, **fields) -> Device:
    for key, value in fields.items():
        setattr(device, key, value)
    db.commit()
    db.refresh(device)
    return device


def delete_device(db: Session, device: Device) -> None:
    db.delete(device)
    db.commit()


def effective_threshold(device: Device, settings: AppSettings) -> int | None:
    """Порог latency для устройства: персональный, иначе глобальный, иначе None."""
    if device.latency_threshold and device.latency_threshold > 0:
        return device.latency_threshold
    if settings.latency_threshold_ms and settings.latency_threshold_ms > 0:
        return settings.latency_threshold_ms
    return None


# ---- History / uptime ----

def uptime_percent(db: Session, device_id: int, hours: int = 24) -> float | None:
    since = utcnow() - timedelta(hours=hours)
    total = (
        db.query(func.count(CheckResult.id))
        .filter(CheckResult.device_id == device_id, CheckResult.timestamp >= since)
        .scalar()
    )
    if not total:
        return None
    up = (
        db.query(func.count(CheckResult.id))
        .filter(
            CheckResult.device_id == device_id,
            CheckResult.timestamp >= since,
            CheckResult.is_up.is_(True),
        )
        .scalar()
    )
    return round(100.0 * up / total, 2)


def uptime_map(db: Session, hours: int = 24) -> dict[int, float]:
    """Uptime % за период для ВСЕХ устройств одним запросом (для 100+ устройств)."""
    since = utcnow() - timedelta(hours=hours)
    rows = (
        db.query(
            CheckResult.device_id,
            func.count(CheckResult.id),
            func.sum(case((CheckResult.is_up.is_(True), 1), else_=0)),
        )
        .filter(CheckResult.timestamp >= since)
        .group_by(CheckResult.device_id)
        .all()
    )
    out: dict[int, float] = {}
    for device_id, total, up in rows:
        if total:
            out[device_id] = round(100.0 * (up or 0) / total, 2)
    return out


def sparkline_map(
    db: Session, minutes: int = 60, points: int = 40
) -> dict[int, list[float | None]]:
    """Последние значения latency для мини-графиков (sparkline) всех устройств.

    None = устройство было недоступно в этот момент (разрыв линии).
    """
    since = utcnow() - timedelta(minutes=minutes)
    rows = (
        db.query(CheckResult.device_id, CheckResult.latency_ms, CheckResult.is_up)
        .filter(CheckResult.timestamp >= since)
        .order_by(CheckResult.timestamp.asc())
        .all()
    )
    by_dev: dict[int, list[float | None]] = {}
    for device_id, latency, is_up in rows:
        by_dev.setdefault(device_id, []).append(latency if is_up else None)
    return {k: v[-points:] for k, v in by_dev.items()}


def latency_history(
    db: Session, device_id: int, hours: int = 24, max_points: int = 300
) -> list[dict]:
    """Полная история latency устройства для графика (с прореживанием)."""
    since = utcnow() - timedelta(hours=hours)
    rows = (
        db.query(CheckResult.timestamp, CheckResult.latency_ms, CheckResult.is_up)
        .filter(CheckResult.device_id == device_id, CheckResult.timestamp >= since)
        .order_by(CheckResult.timestamp.asc())
        .all()
    )
    step = max(1, len(rows) // max_points)
    return [
        {
            "t": ts.isoformat() + "Z",  # naive UTC -> помечаем для браузера
            "latency": (latency if is_up else None),
            "up": bool(is_up),
        }
        for ts, latency, is_up in rows[::step]
    ]


# ---- Массовый импорт устройств ----

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+$")


def _looks_like_host(token: str) -> bool:
    if _IP_RE.match(token):
        return True
    return bool(_HOST_RE.match(token)) and "." in token


def parse_import(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Разбор списка устройств. Поддерживает форматы:
    «Название, IP», «IP, Название», «IP <таб/пробел> Название», просто «IP».
    Разделители: запятая, точка с запятой, табуляция. Строки с # игнорируются.
    Возвращает (список (name, host), список нераспознанных строк).
    """
    entries: list[tuple[str, str]] = []
    skipped: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[;,\t]", line) if p.strip()]
        if len(parts) < 2:
            parts = [p for p in line.split(None, 1) if p]
        if len(parts) == 1:
            entries.append((parts[0], parts[0]))  # только host -> name=host
            continue
        a, b = parts[0], parts[1]
        # авто-определение, что из двух — адрес (host)
        if _looks_like_host(b) and not _looks_like_host(a):
            name, host = a, b
        elif _looks_like_host(a) and not _looks_like_host(b):
            name, host = b, a
        else:
            name, host = a, b  # по умолчанию «Название, IP»
        if host:
            entries.append((name, host))
        else:
            skipped.append(line)
    return entries, skipped


def bulk_create_devices(
    db: Session,
    entries: list[tuple[str, str]],
    group_id: int | None = None,
    interval: int | None = None,
) -> int:
    for name, host in entries:
        db.add(
            Device(
                name=name,
                host=host,
                group_id=group_id,
                interval=interval,
                enabled=True,
            )
        )
    db.commit()
    return len(entries)


def cleanup_history(db: Session, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    deleted = (
        db.query(CheckResult)
        .filter(CheckResult.timestamp < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


# ---- Users ----

def get_user(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()
