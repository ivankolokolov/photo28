"""Смоук: админка импортируется, lifespan не делает сломанных вызовов."""
import os
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


def test_admin_app_imports():
    import src.admin.app as app_module
    assert app_module.app is not None


@pytest.mark.asyncio
async def test_lifespan_is_noop():
    """Lifespan не зовёт глобальный load_cache (тот требует studio_id)."""
    import src.admin.app as app_module
    async with app_module._lifespan(app_module.app):
        pass  # не должно бросить
