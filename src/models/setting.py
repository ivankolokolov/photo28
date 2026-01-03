"""Модель настроек."""
from enum import Enum
from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SettingType(str, Enum):
    """Типы настроек."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    TEXT = "text"


class Setting(Base):
    """Настройка системы."""
    
    __tablename__ = "settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Ключ настройки (уникальный)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    
    # Значение (хранится как строка)
    value: Mapped[str] = mapped_column(Text, default="")
    
    # Тип значения для корректного преобразования
    value_type: Mapped[SettingType] = mapped_column(default=SettingType.STRING)
    
    # Название для отображения в админке
    display_name: Mapped[str] = mapped_column(String(200), default="")
    
    # Описание настройки
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Группа настроек для организации в админке
    group: Mapped[str] = mapped_column(String(50), default="general")
    
    # Порядок сортировки
    sort_order: Mapped[int] = mapped_column(default=0)
    
    def get_typed_value(self):
        """Возвращает значение с правильным типом."""
        if self.value_type == SettingType.INTEGER:
            return int(self.value) if self.value else 0
        elif self.value_type == SettingType.FLOAT:
            return float(self.value) if self.value else 0.0
        elif self.value_type == SettingType.BOOLEAN:
            return self.value.lower() in ("true", "1", "yes", "да")
        else:
            return self.value
    
    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value}>"

