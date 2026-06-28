"""Тенантность каталога/промокодов/настроек."""
import pytest
from sqlalchemy import select

from src.models.studio import Studio
from src.models.product import Product
from src.models.promocode import Promocode
from src.models.setting import Setting


@pytest.mark.asyncio
async def test_same_slug_code_key_across_studios(db_session):
    s1 = Studio(slug="s1", name="S1")
    s2 = Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()

    db_session.add(Product(studio_id=s1.id, slug="10x15", name="A", short_name="A"))
    db_session.add(Product(studio_id=s2.id, slug="10x15", name="A", short_name="A"))
    db_session.add(Promocode(studio_id=s1.id, code="SALE"))
    db_session.add(Promocode(studio_id=s2.id, code="SALE"))
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="10"))
    db_session.add(Setting(studio_id=s2.id, key="min_photos", value="5"))
    await db_session.commit()  # дубликаты в РАЗНЫХ студиях разрешены

    assert len((await db_session.execute(select(Product))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_same_key_same_studio_rejected(db_session):
    s1 = Studio(slug="s1", name="S1")
    db_session.add(s1)
    await db_session.commit()
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="10"))
    await db_session.commit()
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="20"))
    with pytest.raises(Exception):
        await db_session.commit()
