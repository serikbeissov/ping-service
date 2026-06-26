"""Сборка статуса устройств/групп для дашборда и API."""

from sqlalchemy.orm import Session

from . import crud
from .models import Device


def _iso(dt) -> str | None:
    # время хранится как naive UTC — помечаем «Z», чтобы браузер показал локальное
    return (dt.isoformat() + "Z") if dt else None


def device_status(
    device: Device,
    uptime: float | None,
    sparkline: list | None,
    group_name: str | None = None,
    threshold: int | None = None,
) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "host": device.host,
        "enabled": device.enabled,
        "is_up": device.is_up,
        "is_slow": bool(device.is_slow),
        "check_type": device.check_type or "icmp",
        "port": device.port,
        "last_latency_ms": device.last_latency_ms,
        "last_checked": _iso(device.last_checked),
        "last_change": _iso(device.last_change),
        "uptime_24h": uptime,
        "sparkline": sparkline or [],
        "group": group_name,
        "latency_threshold": threshold,
    }


def build_status(db: Session) -> dict:
    groups = crud.list_groups(db)
    all_devices = crud.list_devices(db)

    # батч-запросы вместо N+1 (важно при 100+ устройствах)
    upmap = crud.uptime_map(db, hours=24)
    sparkmap = crud.sparkline_map(db)
    app_settings = crud.get_settings(db)

    group_name_by_id = {g.id: g.name for g in groups}
    statuses = {
        d.id: device_status(
            d,
            upmap.get(d.id),
            sparkmap.get(d.id),
            group_name_by_id.get(d.group_id),
            crud.effective_threshold(d, app_settings),
        )
        for d in all_devices
    }

    def counts(devs: list[dict]) -> tuple[int, int, int]:
        total = len(devs)
        online = sum(1 for d in devs if d["is_up"] is True)
        offline = sum(1 for d in devs if d["is_up"] is False)
        return total, online, offline

    group_blocks = []
    grouped_ids = set()
    for group in groups:
        devs = [statuses[d.id] for d in group.devices]
        grouped_ids.update(d.id for d in group.devices)
        total, online, offline = counts(devs)
        group_blocks.append(
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "devices": devs,
                "total": total,
                "online": online,
                "offline": offline,
            }
        )

    ungrouped = [statuses[d.id] for d in all_devices if d.id not in grouped_ids]
    total, online, offline = counts(list(statuses.values()))

    return {
        "groups": group_blocks,
        "ungrouped": ungrouped,
        "total": total,
        "online": online,
        "offline": offline,
    }
