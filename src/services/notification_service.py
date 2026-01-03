"""Сервис уведомлений для менеджеров."""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.services.settings_service import SettingsService, SettingKeys
from src.models.order import Order
from src.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис для отправки уведомлений менеджерам."""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    def _get_order_keyboard(self, order_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для управления заказом в группе менеджеров."""
        builder = InlineKeyboardBuilder()
        
        # Кнопка подтверждения оплаты
        builder.row(
            InlineKeyboardButton(
                text="✅ Подтвердить оплату",
                callback_data=f"mgr_confirm:{order_id}"
            )
        )
        
        # Ссылка на админку (если настроен URL)
        admin_url = getattr(settings, 'admin_url', None)
        if admin_url:
            builder.row(
                InlineKeyboardButton(
                    text="📋 Открыть в админке",
                    url=f"{admin_url}/orders/{order_id}"
                )
            )
        
        return builder.as_markup()
    
    def _get_manager_chat_id(self) -> Optional[int]:
        """Получает ID чата менеджеров из настроек."""
        chat_id_str = SettingsService.get(SettingKeys.MANAGER_CHAT_ID, "")
        if not chat_id_str:
            return None
        try:
            return int(chat_id_str)
        except ValueError:
            logger.error(f"Неверный MANAGER_CHAT_ID: {chat_id_str}")
            return None
    
    async def notify_new_order(self, order: Order) -> bool:
        """Уведомление о новом оплаченном заказе."""
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            logger.warning("MANAGER_CHAT_ID не настроен, уведомление не отправлено")
            return False
        
        photos_by_format = order.photos_by_format()
        photos_info = "\n".join([
            f"  • {fmt.short_name}: {count} шт."
            for fmt, count in photos_by_format.items()
        ])
        
        # Информация о клиенте
        client_info = f"@{order.user.username}" if order.user.username else order.user.first_name or "Клиент"
        
        # Информация о доставке
        delivery_info = ""
        if order.delivery_type:
            delivery_info = f"\n\n🚚 <b>Доставка:</b> {order.delivery_type.display_name}"
            if order.delivery_address:
                delivery_info += f"\n📍 {order.delivery_address}"
        
        message = (
            f"🆕 <b>Новый заказ #{order.order_number}</b>\n\n"
            f"👤 Клиент: {client_info}\n"
            f"📷 Фото:\n{photos_info}\n\n"
            f"💰 <b>Сумма: {order.total_cost}₽</b>"
            f"{delivery_info}"
        )
        
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
            )
            logger.info(f"Уведомление о заказе #{order.order_number} отправлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
            return False
    
    async def notify_receipt_uploaded(self, order: Order, receipt_file_id: str) -> bool:
        """Уведомление о загрузке квитанции."""
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            return False
        
        client_info = f"@{order.user.username}" if order.user.username else order.user.first_name or "Клиент"
        
        # Информация о доставке
        delivery_info = ""
        if order.delivery_type:
            delivery_info = f"\n🚚 {order.delivery_type.display_name}"
            if order.delivery_address:
                delivery_info += f"\n📍 {order.delivery_address}"
        
        caption = (
            f"🧾 <b>Новый заказ #{order.order_number}</b>\n\n"
            f"👤 Клиент: {client_info}\n"
            f"📷 Фото: {order.photos_count} шт.\n"
            f"💰 Сумма: {order.total_cost}₽"
            f"{delivery_info}"
        )
        
        try:
            await self.bot.send_photo(
                chat_id=chat_id,
                photo=receipt_file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=self._get_order_keyboard(order.id),
            )
            logger.info(f"Квитанция заказа #{order.order_number} отправлена менеджерам")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки квитанции: {e}")
            return False
    
    async def notify_order_status_changed(self, order: Order, old_status: str, new_status: str) -> bool:
        """Уведомление о смене статуса заказа (опционально)."""
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            return False
        
        message = (
            f"🔄 <b>Статус заказа изменён</b>\n\n"
            f"📦 Заказ: #{order.order_number}\n"
            f"📊 {old_status} → <b>{new_status}</b>"
        )
        
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о статусе: {e}")
            return False

