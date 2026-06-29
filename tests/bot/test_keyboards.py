"""Тесты для клавиатур, требующих ctx (studio-скоуп)."""
import pytest
from cryptography.fernet import Fernet
from src.services.studio_provisioning import provision_studio, CATALOG_TEMPLATE
from src.services.settings_service import SettingsService, SettingKeys
from tests.bot.conftest import make_ctx


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_get_format_keyboard_buttons_match_catalog(db_session):
    """get_format_keyboard(ctx) возвращает кнопки по топ-уровневым продуктам студии."""
    from src.bot.keyboards.main import get_format_keyboard

    studio = await provision_studio(
        db_session, slug="kb1", name="KbStudio1", bot_token="t1",
        admin_username="a", admin_password="p",
    )
    ctx = await make_ctx(db_session, studio)

    markup = get_format_keyboard(ctx)

    # Собираем все тексты кнопок
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]

    # Каждый продукт из шаблона должен быть представлен в кнопках
    catalog_names = [p["name"] for p in CATALOG_TEMPLATE]
    for name in catalog_names:
        assert any(name in t for t in button_texts), (
            f"Продукт '{name}' не найден в кнопках: {button_texts}"
        )


@pytest.mark.asyncio
async def test_get_format_keyboard_requires_ctx(db_session):
    """get_format_keyboard() без ctx должен вызывать TypeError."""
    from src.bot.keyboards.main import get_format_keyboard

    with pytest.raises(TypeError):
        get_format_keyboard()


@pytest.mark.asyncio
async def test_get_subcategory_keyboard_requires_ctx(db_session):
    """get_subcategory_keyboard(parent_id) без ctx должен вызывать TypeError."""
    from src.bot.keyboards.main import get_subcategory_keyboard

    with pytest.raises(TypeError):
        get_subcategory_keyboard(1)


@pytest.mark.asyncio
async def test_get_delivery_keyboard_shows_enabled_methods(db_session):
    """get_delivery_keyboard(ctx) показывает только включённые методы доставки."""
    from src.bot.keyboards.main import get_delivery_keyboard

    studio = await provision_studio(
        db_session, slug="kb2", name="KbStudio2", bot_token="t2",
        admin_username="b", admin_password="p",
    )

    # По умолчанию все методы включены — должны быть кнопки OZON, Курьер, Самовывоз
    ctx = await make_ctx(db_session, studio)
    markup = get_delivery_keyboard(ctx)
    button_texts = [btn.text for row in markup.inline_keyboard for btn in row]

    assert any("ОЗОН" in t or "Ozon" in t or "ozon" in t.lower() for t in button_texts), (
        f"ОЗОН не найден в кнопках: {button_texts}"
    )
    assert any("Курьер" in t or "курьер" in t.lower() for t in button_texts), (
        f"Курьер не найден в кнопках: {button_texts}"
    )

    # Отключаем COURIER
    svc = SettingsService(db_session)
    await svc.set_value(studio.id, SettingKeys.DELIVERY_COURIER_ENABLED, "false")
    # Перезагружаем кеш
    await SettingsService(db_session).load_cache(studio.id)
    ctx2 = await make_ctx(db_session, studio)

    markup2 = get_delivery_keyboard(ctx2)
    button_texts2 = [btn.text for row in markup2.inline_keyboard for btn in row]

    assert not any("Курьер" in t or "курьер" in t.lower() for t in button_texts2), (
        f"Курьер должен быть отключён, но найден в кнопках: {button_texts2}"
    )


@pytest.mark.asyncio
async def test_get_delivery_keyboard_requires_ctx(db_session):
    """get_delivery_keyboard() без ctx должен вызывать TypeError."""
    from src.bot.keyboards.main import get_delivery_keyboard

    with pytest.raises(TypeError):
        get_delivery_keyboard()
