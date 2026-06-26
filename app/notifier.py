import logging

import httpx

log = logging.getLogger("notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram(token: str, chat_id: str, message: str) -> tuple[bool, str]:
    """Отправить сообщение в Telegram. Возвращает (успех, текст ошибки/ответа)."""
    if not token or not chat_id:
        return False, "Не заданы token или chat_id"
    url = TELEGRAM_API.format(token=token)
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "OK"
        return False, f"HTTP {resp.status_code}: {resp.text}"
    except httpx.HTTPError as exc:
        log.warning("Telegram send failed: %s", exc)
        return False, str(exc)


def device_down_message(name: str, host: str) -> str:
    return f"🔴 <b>{name}</b> ({host}) недоступно"


def device_up_message(name: str, host: str, latency_ms: float | None) -> str:
    lat = f" ({latency_ms:.0f} ms)" if latency_ms is not None else ""
    return f"🟢 <b>{name}</b> ({host}) восстановлено{lat}"


def device_slow_message(
    name: str, host: str, latency_ms: float | None, threshold: int
) -> str:
    lat = f"{latency_ms:.0f}" if latency_ms is not None else "?"
    return f"🟡 <b>{name}</b> ({host}) медленный отклик: {lat} ms (порог {threshold} ms)"


def device_normal_message(name: str, host: str, latency_ms: float | None) -> str:
    lat = f" ({latency_ms:.0f} ms)" if latency_ms is not None else ""
    return f"🟢 <b>{name}</b> ({host}) отклик в норме{lat}"
