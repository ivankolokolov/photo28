"""Конфигурация приложения."""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot
    bot_token: str = Field(default="", alias="BOT_TOKEN")  # legacy; рантайм берёт токены из Studio

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./storage/bot.db",
        alias="DATABASE_URL",
    )

    # Yandex Disk
    yandex_disk_token: str = Field(default="", alias="YANDEX_DISK_TOKEN")

    # Admin Panel
    admin_secret_key: str = Field(default="change_me_in_production", alias="ADMIN_SECRET_KEY")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD")
    admin_url: str = Field(default="", alias="ADMIN_URL")  # Например: http://localhost:8080

    # Storage paths
    photos_dir: Path = Field(default=Path("./storage/photos"), alias="PHOTOS_DIR")
    temp_dir: Path = Field(default=Path("./storage/temp"), alias="TEMP_DIR")

    # Manager contact (значение берётся из .env или записи Studio; дефолт пустой)
    manager_username: str = Field(default="", alias="MANAGER_USERNAME")

    # Payment details (значения берутся из записи Studio; дефолты пустые, в код не хардкодим)
    payment_phone: str = Field(default="", alias="PAYMENT_PHONE")
    payment_card: str = Field(default="", alias="PAYMENT_CARD")
    payment_receiver: str = Field(default="", alias="PAYMENT_RECEIVER")

    # Fernet encryption key for studio secrets
    fernet_key: str = Field(default="", alias="FERNET_KEY")

    # Webhook
    base_webhook_url: str = Field(default="", alias="BASE_WEBHOOK_URL")

    def ensure_dirs(self) -> None:
        """Создаёт необходимые директории."""
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


# Глобальный экземпляр настроек
settings = Settings()
