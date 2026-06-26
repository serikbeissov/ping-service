from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация из переменных окружения / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admin_user: str = "admin"
    admin_password: str = "changeme"
    secret_key: str = "please-change-me"

    app_title: str = "Мониторинг устройств"
    default_interval: int = 30

    # Путь к файлу БД (внутри тома data/)
    database_url: str = "sqlite:///data/ping.db"

    # ICMP в привилегированном режиме (raw socket). В Docker нужен cap NET_RAW.
    # False — unprivileged ping (требует sysctl net.ipv4.ping_group_range).
    ping_privileged: bool = True

    # Telegram defaults (могут быть переопределены в админке)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


settings = Settings()
