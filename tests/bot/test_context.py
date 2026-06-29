"""Тесты StudioContext и фасадов."""
import os
import pytest
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.bot.context import build_studio_context, SettingsFacade, ProductsFacade
from src.services.settings_service import SettingKeys


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_context_facades_are_studio_scoped(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                admin_username="a1", admin_password="p")
    s2 = await provision_studio(db_session, slug="s2", name="S2", bot_token="t2",
                                admin_username="a2", admin_password="p")
    # дефолтные настройки загружены провижинингом; различим их
    from src.services.settings_service import SettingsService
    await SettingsService(db_session).set_value(s1.id, SettingKeys.MIN_PHOTOS, "10")
    await SettingsService(db_session).set_value(s2.id, SettingKeys.MIN_PHOTOS, "3")
    await SettingsService(db_session).load_cache(s1.id)
    await SettingsService(db_session).load_cache(s2.id)

    ctx1 = build_studio_context(db_session, s1)
    ctx2 = build_studio_context(db_session, s2)

    assert ctx1.studio_id == s1.id
    assert ctx1.settings.get_int(SettingKeys.MIN_PHOTOS, 0) == 10
    assert ctx2.settings.get_int(SettingKeys.MIN_PHOTOS, 0) == 3
    assert ctx1.orders.studio_id == s1.id
    assert isinstance(ctx1.products, ProductsFacade)


@pytest.mark.asyncio
async def test_products_facade_top_level(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t1",
                                admin_username="a1", admin_password="p")
    from src.services.product_service import ProductService
    await ProductService(db_session).load_cache(s1.id)
    ctx = build_studio_context(db_session, s1)
    # CATALOG_TEMPLATE из провижининга даёт несколько товаров верхнего уровня
    assert len(ctx.products.top_level()) >= 1
