# ping-exporter — мониторинг доступности устройств

Сервис проверяет, в сети ли устройство (по ICMP ping), показывает статус на
дашборде, позволяет администратору заводить устройства и группировать их по
разделам (например «Камеры офис 1», «Контроллеры отеля») и шлёт уведомления в
Telegram при падении/восстановлении.

## Стек

- **FastAPI** (Python) — веб и API
- **SQLite** (SQLAlchemy) — хранилище, данные в `./data`
- **icmplib** — асинхронный ICMP ping
- **Jinja2 + Tailwind (CDN)** — дашборд и админка (тёмная тема)
- **Docker Compose** — запуск

## Возможности

- Дашборд по разделам: индикатор онлайн/офлайн, latency, uptime % за 24ч,
  авто-обновление без перезагрузки
- Админка: CRUD разделов и устройств, глобальные настройки, смена пароля
- Анти-флаппинг: падение фиксируется после N неудачных пингов подряд
- Уведомления в Telegram (🔴 упало / 🟢 восстановилось) + кнопка теста
- История пингов с авто-очисткой по сроку хранения

## Запуск (Docker Compose)

```bash
cp .env.example .env
# отредактируйте .env: ADMIN_USER, ADMIN_PASSWORD, SECRET_KEY (openssl rand -hex 32)
docker compose up --build -d
```

Откройте http://<host>:8080 — дашборд. Вход в админку: `/login` (логин/пароль из `.env`).

### Настройка Telegram

1. Создайте бота у [@BotFather](https://t.me/BotFather), получите **bot token**.
2. Узнайте **chat id** (например через @userinfobot или добавив бота в группу).
3. Админка → Настройки → впишите token и chat id → «Сохранить» → «Отправить тест».

## Локальный запуск (без Docker)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# для unprivileged ICMP на Linux:
#   sudo sysctl -w net.ipv4.ping_group_range="0 2147483647"
# либо в .env: PING_PRIVILEGED=true и запуск через sudo
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Переменные окружения (`.env`)

| Переменная | Назначение |
|---|---|
| `ADMIN_USER` / `ADMIN_PASSWORD` | админ, создаётся при первом запуске |
| `SECRET_KEY` | подпись сессионных cookie |
| `APP_TITLE` | заголовок сервиса |
| `DEFAULT_INTERVAL` | интервал опроса по умолчанию (сек) |
| `PING_PRIVILEGED` | `true` — raw ICMP (нужен NET_RAW), `false` — unprivileged |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | начальные настройки Telegram (можно задать в админке) |

## API

- `GET /api/status` — JSON со статусами всех устройств/разделов (для интеграций).

## ICMP в контейнере

`docker-compose.yml` уже добавляет `cap_add: NET_RAW` и `sysctl
net.ipv4.ping_group_range`, чего достаточно для пинга. Если ваша среда
запрещает менять sysctl, оставьте только `NET_RAW` и `PING_PRIVILEGED=true`.
