"""Тесты AdminUser и хеширования паролей."""
import pytest
from sqlalchemy import select

from src.models.admin_user import AdminUser, AdminRole
from src.models.studio import Studio
from src.services.auth import hash_password, verify_password


def test_password_hashing():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


@pytest.mark.asyncio
async def test_super_admin_has_no_studio(db_session):
    admin = AdminUser(
        username="ivan",
        password_hash=hash_password("pw"),
        role=AdminRole.SUPER_ADMIN,
        studio_id=None,
    )
    db_session.add(admin)
    await db_session.commit()
    loaded = (await db_session.execute(select(AdminUser))).scalar_one()
    assert loaded.role == AdminRole.SUPER_ADMIN
    assert loaded.studio_id is None


@pytest.mark.asyncio
async def test_studio_admin_linked_to_studio(db_session):
    studio = Studio(slug="s1", name="S1")
    db_session.add(studio)
    await db_session.commit()
    admin = AdminUser(
        username="owner1",
        password_hash=hash_password("pw"),
        role=AdminRole.STUDIO_ADMIN,
        studio_id=studio.id,
    )
    db_session.add(admin)
    await db_session.commit()
    loaded = (await db_session.execute(
        select(AdminUser).where(AdminUser.username == "owner1")
    )).scalar_one()
    assert loaded.studio_id == studio.id
