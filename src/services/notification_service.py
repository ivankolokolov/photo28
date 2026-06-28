"""Сервис уведомлений для менеджеров (studio-aware)."""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.models.order import Order, OrderStatus, DeliveryType
from src.models.studio import Studio
from src.services.delivery_options import delivery_display_name
from src.services.settings_service import SettingKeys
from src.config import settings as app_settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Уведомления менеджерам/клиенту в рамках одной студии."""

    def __init__(self, bot: Bot, studio: Studio, settings, products):
        self.bot = bot
        self.studio = studio
        self.settings = settings
        self.products = products

    def _get_order_keyboard(self, order_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✅ Подтвердить оплату",
                                         callback_data=f"mgr_confirm:{order_id}"))
        admin_url = getattr(app_settings, "admin_url", None)
        if admin_url:
            builder.row(InlineKeyboardButton(text="📋 Открыть в админке",
                                             url=f"{admin_url}/orders/{order_id}"))
        return builder.as_markup()

    def _get_manager_chat_id(self) -> Optional[int]:
        chat_id_str = self.studio.manager_chat_id
        if not chat_id_str:
            return None
        try:
            return int(chat_id_str)
        except (ValueError, TypeError):
            logger.error("Неверный manager_chat_id студии %s: %r", self.studio.id, chat_id_str)
            return None

    async def notify_new_order(self, order: Order) -> bool:
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            logger.warning("manager_chat_id не настроен для студии %s", self.studio.id)
            return False
        photos_lines = []
        for product_id, count in order.photos_by_product().items():
            product = self.products.get(product_id)
            name = product.short_name if product else f"Товар #{product_id}"
            photos_lines.append(f"  • {name}: {count} шт.")
        client = f"@{order.user.username}" if order.user.username else (order.user.first_name or "Клиент")
        delivery_info = ""
        if order.delivery_type:
            delivery_info = f"\n\n🚚 <b>Доставка:</b> {delivery_display_name(self.settings, order.delivery_type)}"
            if order.delivery_address:
                delivery_info += f"\n📍 {order.delivery_address}"
        message = (
            f"🆕 <b>Новый заказ #{order.order_number}</b>\n\n"
            f"👤 Клиент: {client}\n📷 Фото:\n" + "\n".join(photos_lines) +
            f"\n\n💰 <b>Сумма: {order.total_cost}₽</b>{delivery_info}"
        )
        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error("Ошибка отправки уведомления: %s", e)
            return False

    async def notify_receipt_uploaded(self, order: Order, receipt_file_id: str) -> bool:
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            return False
        client = f"@{order.user.username}" if order.user.username else (order.user.first_name or "Клиент")
        delivery_info = ""
        if order.delivery_type:
            delivery_info = f"\n🚚 {delivery_display_name(self.settings, order.delivery_type)}"
            if order.delivery_address:
                delivery_info += f"\n📍 {order.delivery_address}"
        caption = (
            f"🧾 <b>Новый заказ #{order.order_number}</b>\n\n"
            f"👤 Клиент: {client}\n📷 Фото: {order.photos_count} шт.\n"
            f"💰 Сумма: {order.total_cost}₽{delivery_info}"
        )
        try:
            await self.bot.send_photo(chat_id=chat_id, photo=receipt_file_id, caption=caption,
                                      parse_mode="HTML", reply_markup=self._get_order_keyboard(order.id))
            return True
        except Exception as e:
            logger.error("Ошибка отправки квитанции: %s", e)
            return False

    async def notify_order_status_changed(self, order: Order, old_status: str, new_status: str) -> bool:
        chat_id = self._get_manager_chat_id()
        if not chat_id:
            return False
        message = (f"🔄 <b>Статус заказа изменён</b>\n\n📦 Заказ: #{order.order_number}\n"
                   f"📊 {old_status} → <b>{new_status}</b>")
        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error("Ошибка отправки уведомления о статусе: %s", e)
            return False

    async def notify_client_status_changed(self, order: Order, new_status: str) -> bool:
        manager = self.studio.manager_username or "manager"
        status_messages = {
            OrderStatus.CONFIRMED.value: (
                f"✅ <b>Заказ #{order.order_number} подтверждён!</b>\n\n"
                "Мы начинаем работу над вашим заказом. "
                "Сообщим, когда фотографии будут готовы к отправке."),
            OrderStatus.PRINTING.value: (
                f"🖨 <b>Заказ #{order.order_number} в печати!</b>\n\n"
                "Ваши фотографии сейчас печатаются. Скоро будут готовы!"),
            OrderStatus.READY.value: (
                f"📦 <b>Заказ #{order.order_number} готов!</b>\n\n"
                "Фотографии распечатаны и готовы к отправке. "
                "Мы сообщим номер отслеживания после отправки."),
            OrderStatus.SHIPPED.value: self._get_shipped_message(order),
            OrderStatus.DELIVERED.value: (
                f"🎉 <b>Заказ #{order.order_number} доставлен!</b>\n\n"
                "Спасибо за заказ! Надеемся, вам понравятся фотографии.\n"
                "Будем рады видеть вас снова! 📸"),
            OrderStatus.CANCELLED.value: (
                f"❌ <b>Заказ #{order.order_number} отменён</b>\n\n"
                f"Если есть вопросы, свяжитесь с менеджером: @{manager}"),
        }
        message = status_messages.get(new_status)
        if not message:
            return False
        try:
            await self.bot.send_message(chat_id=order.user.telegram_id, text=message, parse_mode="HTML")
            return True
        except Exception as e:
            logger.error("Ошибка уведомления клиента: %s", e)
            return False

    def _get_shipped_message(self, order: Order) -> str:
        base = f"🚚 <b>Заказ #{order.order_number} отправлен!</b>\n\n"
        if order.delivery_type == DeliveryType.OZON:
            return base + "Посылка передана в службу ОЗОН. Отслеживайте в приложении ОЗОН."
        if order.delivery_type == DeliveryType.COURIER:
            return base + "Курьер свяжется с вами в указанное время."
        if order.delivery_type == DeliveryType.PICKUP:
            addr = self.settings.get(SettingKeys.DELIVERY_PICKUP_ADDRESS, "")
            if addr:
                return base + f"Заказ готов к самовывозу по адресу:\n{addr}"
            return base + "Заказ готов к самовывозу."
        return base + "Скоро вы получите свой заказ!"
