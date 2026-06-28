"""Студия-скоупленные опции доставки (заменяют свойства enum DeliveryType)."""
from src.models.order import DeliveryType
from src.services.settings_service import SettingKeys

_NAME_KEYS = {
    DeliveryType.OZON: SettingKeys.DELIVERY_OZON_NAME,
    DeliveryType.COURIER: SettingKeys.DELIVERY_COURIER_NAME,
    DeliveryType.PICKUP: SettingKeys.DELIVERY_PICKUP_NAME,
}
_DEFAULT_NAMES = {
    DeliveryType.OZON: "ОЗОН доставка",
    DeliveryType.COURIER: "Курьер",
    DeliveryType.PICKUP: "Самовывоз",
}
_PRICE_KEYS = {
    DeliveryType.OZON: SettingKeys.DELIVERY_OZON_PRICE,
    DeliveryType.COURIER: SettingKeys.DELIVERY_COURIER_PRICE,
}
_ENABLED_KEYS = {
    DeliveryType.OZON: SettingKeys.DELIVERY_OZON_ENABLED,
    DeliveryType.COURIER: SettingKeys.DELIVERY_COURIER_ENABLED,
    DeliveryType.PICKUP: SettingKeys.DELIVERY_PICKUP_ENABLED,
}


def delivery_display_name(settings, dt: DeliveryType) -> str:
    return settings.get(_NAME_KEYS[dt], _DEFAULT_NAMES[dt])


def delivery_cost(settings, dt: DeliveryType) -> int:
    if dt == DeliveryType.PICKUP:
        return 0
    return settings.get_int(_PRICE_KEYS[dt], 0)


def delivery_is_enabled(settings, dt: DeliveryType) -> bool:
    return settings.get_bool(_ENABLED_KEYS[dt], True)
