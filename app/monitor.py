import asyncio
import logging
import time

import httpx
from icmplib import async_ping

from . import crud, notifier
from .config import settings
from .database import SessionLocal
from .models import CheckResult, Device, utcnow

log = logging.getLogger("monitor")

# Как часто просыпается планировщик (сек). Реальная частота опроса устройства
# определяется его interval / глобальным default_interval.
TICK = 5
CLEANUP_EVERY = 3600  # раз в час чистим старую историю


async def _check_icmp(device: Device, privileged: bool) -> tuple[bool, float | None]:
    try:
        host = await async_ping(
            device.host, count=2, interval=0.2, timeout=2, privileged=privileged
        )
        latency = round(host.avg_rtt, 2) if host.is_alive else None
        return host.is_alive, latency
    except Exception as exc:  # резолв/сетевые ошибки → считаем недоступным
        log.debug("ping %s failed: %s", device.host, exc)
        return False, None


async def _check_tcp(device: Device, timeout: float = 3.0) -> tuple[bool, float | None]:
    port = device.port or 80
    start = time.perf_counter()
    writer = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(device.host, port), timeout=timeout
        )
        return True, round((time.perf_counter() - start) * 1000, 2)
    except Exception as exc:
        log.debug("tcp %s:%s failed: %s", device.host, port, exc)
        return False, None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


def _http_url(device: Device) -> str:
    h = device.host
    if h.startswith("http://") or h.startswith("https://"):
        return h
    scheme = "https" if device.port in (443, 8443) else "http"
    if device.port and device.port not in (80, 443):
        return f"{scheme}://{h}:{device.port}"
    return f"{scheme}://{h}"


async def _check_http(device: Device, timeout: float = 5.0) -> tuple[bool, float | None]:
    url = _http_url(device)
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=False, follow_redirects=True
        ) as client:
            resp = await client.get(url)
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        return (200 <= resp.status_code < 400), elapsed
    except Exception as exc:
        log.debug("http %s failed: %s", url, exc)
        return False, None


async def _check_device(device: Device, privileged: bool) -> tuple[bool, float | None]:
    """Проверка устройства согласно его типу. Возвращает (alive, latency_ms)."""
    t = device.check_type or "icmp"
    if t == "tcp":
        return await _check_tcp(device)
    if t == "http":
        return await _check_http(device)
    return await _check_icmp(device, privileged)


def _due(device: Device, default_interval: int) -> bool:
    if not device.enabled:
        return False
    if device.last_checked is None:
        return True
    interval = device.interval or default_interval
    return (utcnow() - device.last_checked).total_seconds() >= interval


async def _run_checks() -> None:
    """Один тик: пинг всех устройств, у которых подошёл интервал."""
    db = SessionLocal()
    try:
        app_settings = crud.get_settings(db)
        default_interval = app_settings.default_interval or settings.default_interval
        devices = [d for d in crud.list_devices(db) if _due(d, default_interval)]
        if not devices:
            return

        results = await asyncio.gather(
            *(_check_device(d, settings.ping_privileged) for d in devices)
        )

        notifications: list[str] = []
        now = utcnow()
        for device, (alive, latency) in zip(devices, results):
            db.add(
                CheckResult(device_id=device.id, is_up=alive, latency_ms=latency)
            )
            device.last_checked = now
            device.last_latency_ms = latency

            prev = device.is_up
            if alive:
                device.fail_streak = 0
                new_state = True
            else:
                device.fail_streak = (device.fail_streak or 0) + 1
                # начальное состояние определяем сразу; иначе падение фиксируем
                # только после порога подряд неудач (анти-флаппинг)
                if prev is None or device.fail_streak >= max(
                    1, app_settings.fail_threshold
                ):
                    new_state = False
                else:
                    new_state = prev

            state_changed = new_state != prev
            if state_changed:
                device.is_up = new_state
                device.last_change = now
                # журнал инцидентов: открываем/закрываем «down»
                if new_state is False:
                    crud.open_incident(db, device.id, "down")
                elif new_state is True:
                    crud.close_incident(db, device.id, "down", now)
                if prev is not None and app_settings.alerts_enabled:
                    if new_state:
                        notifications.append(
                            notifier.device_up_message(
                                device.name, device.host, latency
                            )
                        )
                    else:
                        notifications.append(
                            notifier.device_down_message(device.name, device.host)
                        )
            else:
                device.is_up = new_state

            # ----- порог latency («медленный отклик») -----
            threshold = crud.effective_threshold(device, app_settings)
            over = (
                new_state is True
                and threshold is not None
                and latency is not None
                and latency > threshold
            )
            if over:
                device.slow_streak = (device.slow_streak or 0) + 1
            else:
                device.slow_streak = 0

            prev_slow = device.is_slow
            if new_state is not True or threshold is None:
                new_slow = False
            elif device.slow_streak >= max(1, app_settings.fail_threshold):
                new_slow = True
            elif not over:  # latency вернулась в норму
                new_slow = False
            else:
                new_slow = prev_slow
            device.is_slow = new_slow

            # журнал инцидентов: «slow»
            if new_slow != prev_slow:
                if new_slow:
                    crud.open_incident(db, device.id, "slow")
                else:
                    crud.close_incident(db, device.id, "slow", now)

            # алерт о замедлении/нормализации — только в установившемся up-состоянии,
            # чтобы не дублировать сообщения о падении/восстановлении
            if (
                new_slow != prev_slow
                and not state_changed
                and new_state is True
                and app_settings.alerts_enabled
            ):
                if new_slow:
                    notifications.append(
                        notifier.device_slow_message(
                            device.name, device.host, latency, threshold
                        )
                    )
                else:
                    notifications.append(
                        notifier.device_normal_message(
                            device.name, device.host, latency
                        )
                    )

        db.commit()

        # отправляем уведомления вне транзакции
        token = app_settings.telegram_bot_token
        chat_id = app_settings.telegram_chat_id
        for msg in notifications:
            ok, info = await notifier.send_telegram(token, chat_id, msg)
            if not ok:
                log.warning("Не удалось отправить уведомление: %s", info)
    finally:
        db.close()


async def _cleanup() -> None:
    db = SessionLocal()
    try:
        app_settings = crud.get_settings(db)
        deleted = crud.cleanup_history(db, app_settings.history_retention_days)
        if deleted:
            log.info("Очищено старых записей истории: %d", deleted)
    finally:
        db.close()


async def monitor_loop(stop: asyncio.Event) -> None:
    log.info("Monitor loop запущен (privileged=%s)", settings.ping_privileged)
    elapsed = 0
    while not stop.is_set():
        try:
            await _run_checks()
            elapsed += TICK
            if elapsed >= CLEANUP_EVERY:
                elapsed = 0
                await _cleanup()
        except Exception:  # цикл не должен падать
            log.exception("Ошибка в monitor loop")
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK)
        except asyncio.TimeoutError:
            pass
    log.info("Monitor loop остановлен")
