"""Модель студии (тенанта)."""
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Boolean, Numeric, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Studio(Base):
    """Фотостудия — единица мультитенантности."""

    __tablename__ = "studios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # kill-switch

    # Telegram — зашифрованный токен бота (Fernet), см. src/services/crypto.py
    bot_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Секрет для пути webhook (/webhook/{webhook_secret}); не равен токену.
    webhook_secret: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )

    # Группа чеков / менеджер
    manager_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    manager_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Реквизиты P2P
    payment_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_card: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_receiver: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Опциональный собственный платёжный шлюз (зашифр. JSON-креды)
    payment_gateway_creds: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Хранилище
    yandex_disk_token: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Биллинг платформы
    platform_fee_per_photo: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("5.00")
    )
    monthly_minimum: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0")
    )

    def __repr__(self) -> str:
        return f"<Studio {self.slug}: {self.name}>"
