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
    
    # Кадрирование
    CROP_ENABLED = "crop_enabled"  # Включить функцию кадрирования
    SMART_CROP_ENABLED = "smart_crop_enabled"  # Использовать умный авто-кроп
    CROP_FACE_PRIORITY = "crop_face_priority"  # Приоритет лиц при кропе (0-100)
    CROP_CONFIDENCE_THRESHOLD = "crop_confidence_threshold"  # Порог уверенности для авто-подтверждения
    CROP_SHOW_EDITOR = "crop_show_editor"  # Всегда показывать редактор или только проблемные
    
    # Доставка — ОЗОН
    DELIVERY_OZON_ENABLED = "delivery_ozon_enabled"
    DELIVERY_OZON_PRICE = "delivery_ozon_price"
    DELIVERY_OZON_NAME = "delivery_ozon_name"
    DELIVERY_OZON_DESCRIPTION = "delivery_ozon_description"
    # Доставка — Курьер
    DELIVERY_COURIER_ENABLED = "delivery_courier_enabled"
    DELIVERY_COURIER_PRICE = "delivery_courier_price"
    DELIVERY_COURIER_NAME = "delivery_courier_name"
    DELIVERY_COURIER_DESCRIPTION = "delivery_courier_description"
    # Доставка — Самовывоз
    DELIVERY_PICKUP_ENABLED = "delivery_pickup_enabled"
    DELIVERY_PICKUP_NAME = "delivery_pickup_name"
    DELIVERY_PICKUP_ADDRESS = "delivery_pickup_address"
    DELIVERY_PICKUP_DESCRIPTION = "delivery_pickup_description"
    # Общее
    FREE_DELIVERY_THRESHOLD = "free_delivery_threshold"
    
    # Контакты
    MANAGER_USERNAME = "manager_username"
    PAYMENT_PHONE = "payment_phone"
    PAYMENT_CARD = "payment_card"
    PAYMENT_RECEIVER = "payment_receiver"
    
    # Бот
    WELCOME_MESSAGE = "welcome_message"  # Приветственное сообщение (шаблон)
    
    # Подписка
    SUBSCRIPTION_CHANNEL = "subscription_channel"  # @username или ID канала для проверки подписки
    
    # Уведомления
    MANAGER_CHAT_ID = "manager_chat_id"  # ID группы менеджеров для уведомлений
    NOTIFY_CLIENT_STATUS = "notify_client_status"  # Уведомлять клиента о смене статуса
    
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
        "description": "thumbnail — показывать как фото, document — показывать как документ",
        "group": "general",
        "sort_order": 2,
    },
    # Кадрирование
    {
        "key": SettingKeys.CROP_ENABLED,
        "value": "true",
        "value_type": SettingType.BOOLEAN,
        "display_name": "Включить кадрирование",
        "description": "Предлагать клиентам настроить кадрирование фото перед печатью",
        "group": "crop",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.SMART_CROP_ENABLED,
        "value": "true",
        "value_type": SettingType.BOOLEAN,
        "display_name": "Умный авто-кроп",
        "description": "Автоматически определять лица и важные области для кадрирования",
        "group": "crop",
        "sort_order": 2,
    },
    {
        "key": SettingKeys.CROP_FACE_PRIORITY,
        "value": "80",
        "value_type": SettingType.INTEGER,
        "display_name": "Приоритет лиц (0-100)",
        "description": "Насколько важно центрировать кроп на лицах. 100 = всегда по лицу, 0 = игнорировать лица",
        "group": "crop",
        "sort_order": 3,
    },
    {
        "key": SettingKeys.CROP_CONFIDENCE_THRESHOLD,
        "value": "85",
        "value_type": SettingType.INTEGER,
        "display_name": "Порог авто-подтверждения (%)",
        "description": "Если уверенность кропа выше этого порога — не спрашивать подтверждение у клиента",
        "group": "crop",
        "sort_order": 4,
    },
    {
        "key": SettingKeys.CROP_SHOW_EDITOR,
        "value": "problems_only",
        "value_type": SettingType.STRING,
        "display_name": "Показывать редактор кропа",
        "description": "always — всегда, problems_only — только для проблемных фото, never — никогда",
        "group": "crop",
        "sort_order": 5,
    },
    # Доставка — ОЗОН
    {
        "key": SettingKeys.DELIVERY_OZON_ENABLED,
        "value": "true",
        "value_type": SettingType.BOOLEAN,
        "display_name": "ОЗОН доставка",
        "description": "Включить/выключить доставку через ОЗОН",
        "group": "delivery_ozon",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.DELIVERY_OZON_PRICE,
        "value": "100",
        "value_type": SettingType.INTEGER,
        "display_name": "Стоимость",
        "description": "Стоимость доставки ОЗОН в рублях",
        "group": "delivery_ozon",
        "sort_order": 2,
    },
    {
        "key": SettingKeys.DELIVERY_OZON_NAME,
        "value": "ОЗОН доставка",
        "value_type": SettingType.STRING,
        "display_name": "Название",
        "description": "Название для кнопки в боте",
        "group": "delivery_ozon",
        "sort_order": 3,
    },
    {
        "key": SettingKeys.DELIVERY_OZON_DESCRIPTION,
        "value": "Доставка в пункт выдачи ОЗОН\n• Срок: от 4 дней\n• Необходимо приложение ОЗОН",
        "value_type": SettingType.TEXT,
        "display_name": "Описание",
        "description": "Описание способа доставки (показывается клиенту)",
        "group": "delivery_ozon",
        "sort_order": 4,
    },
    # Доставка — Курьер
    {
        "key": SettingKeys.DELIVERY_COURIER_ENABLED,
        "value": "true",
        "value_type": SettingType.BOOLEAN,
        "display_name": "Курьерская доставка",
        "description": "Включить/выключить курьерскую доставку",
        "group": "delivery_courier",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.DELIVERY_COURIER_PRICE,
        "value": "0",
        "value_type": SettingType.INTEGER,
        "display_name": "Стоимость",
        "description": "Стоимость доставки курьером в рублях (0 = по согласованию)",
        "group": "delivery_courier",
        "sort_order": 2,
    },
    {
        "key": SettingKeys.DELIVERY_COURIER_NAME,
        "value": "Курьером по Москве",
        "value_type": SettingType.STRING,
        "display_name": "Название",
        "description": "Название для кнопки в боте",
        "group": "delivery_courier",
        "sort_order": 3,
    },
    {
        "key": SettingKeys.DELIVERY_COURIER_DESCRIPTION,
        "value": "Служба Достависта\n• Время и стоимость по согласованию",
        "value_type": SettingType.TEXT,
        "display_name": "Описание",
        "description": "Описание способа доставки (показывается клиенту)",
        "group": "delivery_courier",
        "sort_order": 4,
    },
    # Доставка — Самовывоз
    {
        "key": SettingKeys.DELIVERY_PICKUP_ENABLED,
        "value": "true",
        "value_type": SettingType.BOOLEAN,
        "display_name": "Самовывоз",
        "description": "Включить/выключить самовывоз",
        "group": "delivery_pickup",
        "sort_order": 1,
    },
    {
        "key": SettingKeys.DELIVERY_PICKUP_NAME,
        "value": "Самовывоз",
        "value_type": SettingType.STRING,
        "display_name": "Название",
        "description": "Название для кнопки в боте",
        "group": "delivery_pickup",
        "sort_order": 2,
    },
    {
        "key": SettingKeys.DELIVERY_PICKUP_ADDRESS,
        "value": "г. Москва, м. Чертановская\nБалаклавский пр-т 12к3, подъезд 1",
        "value_type": SettingType.TEXT,
        "display_name": "Адрес самовывоза",
        "description": "Адрес пункта самовывоза (показывается клиенту)",
        "group": "delivery_pickup",
        "sort_order": 3,
    },
    {
        "key": SettingKeys.DELIVERY_PICKUP_DESCRIPTION,
        "value": "Время по согласованию с менеджером",
        "value_type": SettingType.TEXT,
        "display_name": "Описание",
        "description": "Дополнительная информация о самовывозе",
        "group": "delivery_pickup",
        "sort_order": 4,
    },
    # Общие настройки доставки
    {
        "key": SettingKeys.FREE_DELIVERY_THRESHOLD,
        "value": "0",
        "value_type": SettingType.INTEGER,
        "display_name": "Бесплатная доставка от суммы",
        "description": "Сумма заказа для бесплатной доставки (0 = отключено)",
        "group": "delivery_general",
        "sort_order": 1,
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
    # Бот
    {
        "key": SettingKeys.WELCOME_MESSAGE,
        "value": "Здравствуйте! 👋\n\nЯ бот приёма заказов <b>Photo28</b>!\n\nКакой формат фотографий вы хотите напечатать?\n\n📷 <b>Форматы:</b>\n{formats}\n\nДля связи с менеджером: @{manager}",
        "value_type": SettingType.TEXT,
        "display_name": "Приветственное сообщение",
        "description": "Шаблон приветствия. Переменные: {formats} — список форматов, {manager} — username менеджера",
        "group": "bot",
        "sort_order": 1,
    },
    # Подписка
    {
        "key": SettingKeys.SUBSCRIPTION_CHANNEL,
        "value": "",
        "value_type": SettingType.STRING,
        "display_name": "Канал для проверки подписки",
        "description": "Username канала (напр. @photo28studio) или его ID. Бот должен быть администратором канала. Оставьте пустым если не используете.",
        "group": "subscription",
        "sort_order": 1,
    },
    # Уведомления
    {
        "key": SettingKeys.MANAGER_CHAT_ID,
        "value": "",
        "value_type": SettingType.STRING,
        "display_name": "ID чата менеджеров",
        "description": "ID группы/чата для уведомлений о заказах. Используйте /chatid в группе чтобы узнать ID.",
        "group": "notifications",
        "sort_order": 1,
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

