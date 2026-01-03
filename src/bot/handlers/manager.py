"""Обработчики для менеджеров (в группе уведомлений)."""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from src.database import async_session
from src.services.order_service import OrderService
from src.models.order import OrderStatus

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("mgr_confirm:"))
async def manager_confirm_payment(callback: CallbackQuery, bot: Bot):
    """Менеджер подтверждает оплату заказа."""
    order_id = int(callback.data.split(":")[1])
    manager_name = callback.from_user.full_name or callback.from_user.username or "Менеджер"
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("❌ Заказ не найден", show_alert=True)
            return
        
        if order.status != OrderStatus.PAID:
            await callback.answer(
                f"⚠️ Заказ уже в статусе: {order.status.display_name}",
                show_alert=True
            )
            return
        
        # Меняем статус на "Подтверждён"
        await service.update_order_status(order, OrderStatus.CONFIRMED)
        
        # Уведомляем клиента
        try:
            await bot.send_message(
                chat_id=order.user.telegram_id,
                text=(
                    f"✅ <b>Оплата подтверждена!</b>\n\n"
                    f"Ваш заказ #{order.order_number} принят в работу.\n"
                    f"Мы сообщим, когда фотографии будут готовы к отправке."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить клиента: {e}")
    
    # Обновляем сообщение в группе менеджеров
    try:
        # Меняем caption и убираем кнопки
        await callback.message.edit_caption(
            caption=(
                f"{callback.message.caption}\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"✅ <b>Оплата подтверждена</b>\n"
                f"👤 {manager_name}"
            ),
            parse_mode="HTML",
            reply_markup=None,  # Убираем кнопки
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение: {e}")
    
    await callback.answer("✅ Оплата подтверждена, клиент уведомлён!")

