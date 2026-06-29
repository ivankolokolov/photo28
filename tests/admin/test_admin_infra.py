"""Проверка тестовой инфраструктуры админки."""
import os
import pytest
from cryptography.fernet import Fernet
from tests.admin.conftest import seed_super_admin, login


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_login_page_renders(admin_client, db_session):
    resp = admin_client.get("/login")
    assert resp.status_code == 200
