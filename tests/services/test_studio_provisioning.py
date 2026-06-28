"""Тесты провижининга студии."""
import os
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.admin_user import AdminUser, AdminRole
from src.models.setting import Setting
from src.models.product import Product
from src.services.studio_provisioning import provision_studio
from src.services.crypto import decrypt_secret
from src.services.auth import verify_password


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_provision_creates_full_studio(db_session):
    studio = await provision_studio(
        db_session,
        slug="photo28",
        name="Photo28",
        bot_token="123:ABC",
        admin_username="owner",
        admin_password="pw12345",
    )
    assert studio.id is not None
    # Токен зашифрован
    assert studio.bot_token != "123:ABC"
    assert decrypt_secret(studio.bot_token) == "123:ABC"

    # Создан studio_admin
    admin = (await db_session.execute(
        select(AdminUser).where(AdminUser.studio_id == studio.id)
    )).scalar_one()
    assert admin.role == AdminRole.STUDIO_ADMIN
    assert verify_password("pw12345", admin.password_hash)

    # Дефолтные настройки и каталог привязаны к студии
    settings = (await db_session.execute(
        select(Setting).where(Setting.studio_id == studio.id)
    )).scalars().all()
    assert len(settings) > 0
    products = (await db_session.execute(
        select(Product).where(Product.studio_id == studio.id)
    )).scalars().all()
    assert len(products) > 0
