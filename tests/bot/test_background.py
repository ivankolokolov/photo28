"""Тест разовой очистки черновиков по студиям."""
import os
import pytest
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

from src.services.studio_provisioning import provision_studio
from src.services.order_service import OrderService
from src.models.order import Order, OrderStatus
from src.bot.background import cleanup_old_drafts_once


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_cleanup_only_old_drafts_per_studio(db_session):
    s1 = await provision_studio(db_session, slug="s1", name="S1", bot_token="t", admin_username="a", admin_password="p")
    svc = OrderService(db_session, s1.id)
    user = await svc.get_or_create_user(telegram_id=1)
    old = await svc.create_order(user)
    # делаем черновик старым
    old.created_at = datetime.now() - timedelta(days=10)
    await db_session.commit()

    deleted = await cleanup_old_drafts_once(db_session, [s1.id], days=7)
    assert deleted == 1
