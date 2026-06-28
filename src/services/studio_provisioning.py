"""Провижининг новой студии: тенант + админ + дефолтные настройки + шаблон каталога."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.studio import Studio
from src.models.admin_user import AdminUser, AdminRole
from src.models.setting import Setting
from src.models.product import Product
from src.services.auth import hash_password
from src.services.crypto import encrypt_secret
from src.services.settings_service import DEFAULT_SETTINGS

# Шаблон каталога типовых форматов (владелец потом правит цены в админке).
CATALOG_TEMPLATE = [
    {"slug": "classic_10x15", "name": "Классика 10×15", "short_name": "10×15",
     "emoji": "🖼", "price_per_unit": 25, "price_type": "per_unit",
     "aspect_ratio": 1.5, "sort_order": 1},
    {"slug": "polaroid", "name": "Полароид", "short_name": "Полароид",
     "emoji": "📸", "price_per_unit": 22, "price_type": "tiered",
     "pricing_group": "polaroid", "aspect_ratio": 0.84, "sort_order": 2},
    {"slug": "square_10x10", "name": "Квадрат 10×10", "short_name": "10×10",
     "emoji": "⬜", "price_per_unit": 23, "price_type": "per_unit",
     "aspect_ratio": 1.0, "sort_order": 3},
]


async def provision_studio(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    bot_token: str,
    admin_username: str,
    admin_password: str,
) -> Studio:
    """Создаёт студию и весь её стартовый набор данных."""
    studio = Studio(slug=slug, name=name, bot_token=encrypt_secret(bot_token))
    session.add(studio)
    await session.flush()  # получить studio.id до коммита

    session.add(AdminUser(
        username=admin_username,
        password_hash=hash_password(admin_password),
        role=AdminRole.STUDIO_ADMIN,
        studio_id=studio.id,
    ))

    for s in DEFAULT_SETTINGS:
        session.add(Setting(
            studio_id=studio.id,
            key=s["key"],
            value=s["value"],
            value_type=s["value_type"],
            display_name=s.get("display_name", ""),
            description=s.get("description", ""),
            group=s.get("group", "general"),
            sort_order=s.get("sort_order", 0),
        ))

    for p in CATALOG_TEMPLATE:
        session.add(Product(studio_id=studio.id, **p))

    await session.commit()
    await session.refresh(studio)
    return studio
