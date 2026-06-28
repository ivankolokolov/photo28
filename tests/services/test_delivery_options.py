"""Тесты studio-скоупленных опций доставки."""
import pytest
from src.models.studio import Studio
from src.models.setting import Setting, SettingType
from src.models.order import DeliveryType
from src.services.settings_service import SettingsService, SettingKeys
from src.bot.context import SettingsFacade
from src.services.delivery_options import (
    delivery_display_name, delivery_cost, delivery_is_enabled,
)


@pytest.mark.asyncio
async def test_delivery_helpers_read_studio_settings(db_session):
    SettingsService.invalidate_cache()
    s = Studio(slug="s1", name="S1"); db_session.add(s); await db_session.commit()
    db_session.add_all([
        Setting(studio_id=s.id, key=SettingKeys.DELIVERY_OZON_NAME, value="ОЗОН X"),
        Setting(studio_id=s.id, key=SettingKeys.DELIVERY_OZON_PRICE, value="150", value_type=SettingType.INTEGER),
        Setting(studio_id=s.id, key=SettingKeys.DELIVERY_OZON_ENABLED, value="true", value_type=SettingType.BOOLEAN),
    ])
    await db_session.commit()
    await SettingsService(db_session).load_cache(s.id)

    facade = SettingsFacade(s.id)
    assert delivery_display_name(facade, DeliveryType.OZON) == "ОЗОН X"
    assert delivery_cost(facade, DeliveryType.OZON) == 150
    assert delivery_is_enabled(facade, DeliveryType.OZON) is True
    assert delivery_cost(facade, DeliveryType.PICKUP) == 0
