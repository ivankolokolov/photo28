"""Конфигурация приложения."""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Telegram Bot
    bot_token: str = Field(..., env="BOT_TOKEN")
    
    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./storage/bot.db",
        env="DATABASE_URL"
    )
    
    # Yandex Disk
    yandex_disk_token: str = Field(default="", env="YANDEX_DISK_TOKEN")
    
    # Admin Panel
    admin_secret_key: str = Field(default="change_me_in_production", env="ADMIN_SECRET_KEY")
    admin_username: str = Field(default="admin", env="ADMIN_USERNAME")
    admin_password: str = Field(default="admin", env="ADMIN_PASSWORD")
    admin_url: str = Field(default="", env="ADMIN_URL")  # Например: http://localhost:8080
    
    # Storage paths
    photos_dir: Path = Field(default=Path("./storage/photos"), env="PHOTOS_DIR")
    temp_dir: Path = Field(default=Path("./storage/temp"), env="TEMP_DIR")
    
    # Manager contact
    manager_username: str = Field(default="print28photo_zakaz", env="MANAGER_USERNAME")
    
    # Payment details
    payment_phone: str = Field(default="+79999821473", env="PAYMENT_PHONE")
    payment_card: str = Field(default="4377723740716133", env="PAYMENT_CARD")
    payment_receiver: str = Field(default="Дарья Р.", env="PAYMENT_RECEIVER")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def ensure_dirs(self) -> None:
        """Создаёт необходимые директории."""
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


# Глобальный экземпляр настроек
settings = Settings()

