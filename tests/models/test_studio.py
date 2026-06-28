"""Тесты модели Studio."""
from decimal import Decimal
import pytest
from sqlalchemy import select

from src.models.studio import Studio


@pytest.mark.asyncio
async def test_create_studio_defaults(db_session):
    studio = Studio(slug="photo28", name="Photo28")
    db_session.add(studio)
    await db_session.commit()

    loaded = (await db_session.execute(select(Studio))).scalar_one()
    assert loaded.slug == "photo28"
    assert loaded.is_active is True
    assert loaded.platform_fee_per_photo == Decimal("5.00")
    assert loaded.monthly_minimum == Decimal("0")


@pytest.mark.asyncio
async def test_studio_slug_unique(db_session):
    db_session.add(Studio(slug="dup", name="A"))
    await db_session.commit()
    db_session.add(Studio(slug="dup", name="B"))
    with pytest.raises(Exception):
        await db_session.commit()
