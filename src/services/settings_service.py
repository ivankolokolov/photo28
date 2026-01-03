"""Сервис настроек с кешированием."""
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.setting import Setting, SettingType


class SettingsService:
    """Сервис для работы с настройками."""
    
    # Кеш настроек (в памяти)
    _cache: Dict[str, Any] = {}
    _cache_loaded: bool = False
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def load_cache(self) -> None:
        """Загружает все настройки в кеш."""
        query = select(Setting)
        result = await self.session.execute(query)
        settings = result.scalars().all()
        
        SettingsService._cache = {
            s.key: s.get_typed_value() for s in settings
        }
        SettingsService._cache_loaded = True
    
    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Получает значение из кеша."""
        return cls._cache.get(key, default)
    
    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Получает целочисленное значение."""
        value = cls._cache.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    @classmethod
    def get_float(cls, key: str, default: float = 0.0) -> float:
        """Получает вещественное значение."""
        value = cls._cache.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Получает булево значение."""
        value = cls._cache.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "да")
        return bool(value)
    
    @classmethod
    def invalidate_cache(cls) -> None:
        """Сбрасывает кеш (вызывать после изменения настроек)."""
        cls._cache = {}
        cls._cache_loaded = False
    
    async def get_all(self) -> list[Setting]:
        """Получает все настройки из БД."""
        query = select(Setting).order_by(Setting.group, Setting.sort_order)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_key(self, key: str) -> Optional[Setting]:
        """Получает настройку по ключу."""
        query = select(Setting).where(Setting.key == key)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def set_value(self, key: str, value: Any) -> Setting:
        """Устанавливает значение настройки."""
        setting = await self.get_by_key(key)
        if setting:
            setting.value = str(value)
            await self.session.commit()
            # Обновляем кеш
            SettingsService._cache[key] = setting.get_typed_value()
            return setting
        else:
            raise ValueError(f"Настройка {key} не найдена")
    
    async def create_setting(
        self,
        key: str,
        value: str,
        value_type: SettingType = SettingType.STRING,
        display_name: str = "",
        description: str = "",
        group: str = "general",
        sort_order: int = 0,
    ) -> Setting:
        """Создаёт новую настройку."""
        setting = Setting(
            key=key,
            value=value,
            value_type=value_type,
            display_name=display_name or key,
            description=description,
            group=group,
            sort_order=sort_order,
        )
        self.session.add(setting)
        await self.session.commit()
        # Обновляем кеш
        SettingsService._cache[key] = setting.get_typed_value()
        return setting


# Константы ключей настроек
class SettingKeys:
    """Ключи настроек."""
    # Основные
    MIN_PHOTOS = "min_photos"
    PREVIEW_MODE = "preview_mode"  # "thumbnail" или "document"
    
    # Доставка
    DELIVERY_PRICE_CDEK = "delivery_price_cdek"
    DELIVERY_PRICE_POST = "delivery_price_post"
    FREE_DELIVERY_THRESHOLD = "free_delivery_threshold"
    
    # Контакты
    MANAGER_USERNAME = "manager_username"
    PAYMENT_PHONE = "payment_phone"
    PAYMENT_CARD = "payment_card"
    PAYMENT_RECEIVER = "payment_receiver"
    
    # Системные (не отображаются в UI настроек)
    RESTART_REQUESTED = "restart_requested"  # "true" / "false"
    RESTART_SCHEDULED_TIME = "restart_scheduled_time"  # ISO datetime или пустая строка


# Значения по умолчанию
DEFAULT_SETTINGS = [
    # Основные
    {
        "key": SettingKeys.MIN_PHOTOS,
        "value": "10",
        "value_type": SettingType.INTEGER,
        "display_name": "Минимальное количество фото",
        "description": "Минимальное количество фотографий для оформления заказа",
        "group": "general",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.PREVIEW_MODE,
        "value": "thumbnail",
        "value_type": SettingType.STRING,
        "display_name": "Режим превью документов",
        "description": "thumbnail — показывать как фото (медленнее), document — показывать как документ",
        "group": "general",
        "sort_order": 2,
    },
    # Доставка
    {
        "key": SettingKeys.DELIVERY_PRICE_CDEK,
        "value": "350",
        "value_type": SettingType.INTEGER,
        "display_name": "Стоимость доставки СДЭК",
        "description": "Стоимость доставки через СДЭК в рублях",
        "group": "delivery",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.DELIVERY_PRICE_POST,
        "value": "250",
        "value_type": SettingType.INTEGER,
        "display_name": "Стоимость доставки Почтой России",
        "description": "Стоимость доставки Почтой России в рублях",
        "group": "delivery",
        "sort_order": 2,
    },
    {
        "key": SettingKeys.FREE_DELIVERY_THRESHOLD,
        "value": "0",
        "value_type": SettingType.INTEGER,
        "display_name": "Бесплатная доставка от суммы",
        "description": "Сумма заказа для бесплатной доставки (0 = отключено)",
        "group": "delivery",
        "sort_order": 3,
    },
    # Контакты
    {
        "key": SettingKeys.MANAGER_USERNAME,
        "value": "@manager",
        "value_type": SettingType.STRING,
        "display_name": "Username менеджера",
        "description": "Telegram username менеджера для связи",
        "group": "contacts",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.PAYMENT_PHONE,
        "value": "+7 (999) 123-45-67",
        "value_type": SettingType.STRING,
        "display_name": "Телефон для оплаты",
        "description": "Номер телефона для перевода по СБП",
        "group": "contacts",
        "sort_order": 2,
    },
    {
        "key": SettingKeys.PAYMENT_CARD,
        "value": "1234 5678 9012 3456",
        "value_type": SettingType.STRING,
        "display_name": "Номер карты",
        "description": "Номер карты для оплаты переводом",
        "group": "contacts",
        "sort_order": 3,
    },
    {
        "key": SettingKeys.PAYMENT_RECEIVER,
        "value": "Имя Фамилия",
        "value_type": SettingType.STRING,
        "display_name": "Получатель платежа",
        "description": "ФИО получателя для подтверждения перевода",
        "group": "contacts",
        "sort_order": 4,
    },
    # Системные
    {
        "key": SettingKeys.RESTART_REQUESTED,
        "value": "false",
        "value_type": SettingType.BOOLEAN,
        "display_name": "Перезапуск запрошен",
        "description": "",
        "group": "system",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.RESTART_SCHEDULED_TIME,
        "value": "",
        "value_type": SettingType.STRING,
        "display_name": "Запланированное время перезапуска",
        "description": "",
        "group": "system",
        "sort_order": 2,
    },
]

