"""Тесты пер-студийного кеша настроек."""
import pytest

from src.models.studio import Studio
from src.models.setting import Setting, SettingType
from src.services.settings_service import SettingsService


async def _two_studios(db_session):
    s1, s2 = Studio(slug="s1", name="S1"), Studio(slug="s2", name="S2")
    db_session.add_all([s1, s2])
    await db_session.commit()
    db_session.add(Setting(studio_id=s1.id, key="min_photos", value="10",
                           value_type=SettingType.INTEGER))
    db_session.add(Setting(studio_id=s2.id, key="min_photos", value="3",
                           value_type=SettingType.INTEGER))
    await db_session.commit()
    return s1, s2


@pytest.mark.asyncio
async def test_cache_is_per_studio(db_session):
    SettingsService.invalidate_cache()
    s1, s2 = await _two_studios(db_session)
    svc = SettingsService(db_session)
    await svc.load_cache(s1.id)
    await svc.load_cache(s2.id)

    assert SettingsService.get_int(s1.id, "min_photos", 0) == 10
    assert SettingsService.get_int(s2.id, "min_photos", 0) == 3


@pytest.mark.asyncio
async def test_set_value_updates_only_one_studio(db_session):
    SettingsService.invalidate_cache()
    s1, s2 = await _two_studios(db_session)
    svc = SettingsService(db_session)
    await svc.load_cache(s1.id)
    await svc.load_cache(s2.id)

    await svc.set_value(s1.id, "min_photos", "99")
    assert SettingsService.get_int(s1.id, "min_photos", 0) == 99
    assert SettingsService.get_int(s2.id, "min_photos", 0) == 3
