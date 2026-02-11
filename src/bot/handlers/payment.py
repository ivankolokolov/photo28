"""Обработчики оплаты."""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.bot.states import OrderStates
from src.bot.keyboards import (
    get_promocode_keyboard,
    get_payment_keyboard,
    get_final_keyboard,
)
from src.database import async_session
from src.services.order_service import OrderService
from src.services.notification_service import NotificationService
from src.services.settings_service import SettingsService, SettingKeys
from src.models.order import OrderStatus

logger = logging.getLogger(__name__)


async def check_channel_subscription(bot: Bot, user_id: int) -> bool:
    """Проверяет подписку пользователя на канал из настроек."""
    channel = SettingsService.get(SettingKeys.SUBSCRIPTION_CHANNEL, "")
    if not channel:
        return True  # Канал не настроен — проверка не нужна
    
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(f"Не удалось проверить подписку на {channel}: {e}")
        return True  # При ошибке пропускаем проверку

router = Router()


def format_payment_summary(order, show_promocode_info: bool = True) -> str:
    """Форматирует сводку для оплаты."""
    lines = [
        "💰 <b>Стоимость заказа:</b>\n",
        f"📷 Фотографии: {order.photos_cost}₽",
        f"🚚 Доставка: {order.delivery_cost}₽",
    ]
    
    if order.discount > 0:
        lines.append(f"🎟 Скидка: -{order.discount}₽")
    
    lines.append(f"\n<b>Итого к оплате: {order.total_cost}₽</b>")
    
    if show_promocode_info and order.discount == 0:
        lines.append("\n💡 У вас есть промокод?")
    
    return "\n".join(lines)


@router.callback_query(F.data == "go_to_payment")
async def go_to_payment(callback: CallbackQuery, state: FSMContext):
    """Переход к оплате."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        # Проверяем, что выбрана доставка
        if not order.delivery_type:
            await callback.answer("Сначала выберите способ доставки", show_alert=True)
            return
    
    await callback.message.edit_text(
        format_payment_summary(order),
        reply_markup=get_promocode_keyboard(),
        parse_mode="HTML",
    )
    
    await callback.answer()


@router.callback_query(F.data == "enter_promocode")
async def enter_promocode(callback: CallbackQuery, state: FSMContext):
    """Ввод промокода."""
    await callback.message.edit_text(
        "🎟 <b>Введите промокод:</b>\n\n"
        "Отправьте промокод в сообщении.",
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.entering_promocode)
    await callback.answer()


@router.message(OrderStates.entering_promocode)
async def process_promocode(message: Message, state: FSMContext, bot: Bot):
    """Обработка промокода."""
    if not message.text:
        await message.answer("Пожалуйста, отправьте промокод текстом.")
        return
    
    data = await state.get_data()
    order_id = data.get("order_id")
    
    code = message.text.strip().upper()
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        # Проверяем промокод
        promocode = await service.get_promocode(code)
        
        if not promocode:
            await message.answer(
                "❌ К сожалению, данный промокод недействителен.\n\n"
                "Попробуйте другой промокод или перейдите к оплате.",
                reply_markup=get_promocode_keyboard(),
            )
            return
        
        # Проверяем валидность (с учётом количества фото)
        is_valid, error_msg = promocode.is_valid(
            order_amount=order.photos_cost,
            photos_count=order.photos_count,
        )
        
        if not is_valid:
            await message.answer(
                f"❌ Промокод не применён: {error_msg}\n\n"
                "Попробуйте другой промокод или перейдите к оплате.",
                reply_markup=get_promocode_keyboard(),
            )
            return
        
        # Проверяем подписку на канал (если требуется)
        if promocode.require_subscription:
            is_subscribed = await check_channel_subscription(bot, message.from_user.id)
            if not is_subscribed:
                channel = SettingsService.get(SettingKeys.SUBSCRIPTION_CHANNEL, "канал")
                await message.answer(
                    f"❌ Для использования этого промокода нужно подписаться на {channel}\n\n"
                    "Подпишитесь и попробуйте ещё раз.",
                    reply_markup=get_promocode_keyboard(),
                )
                return
        
        # Применяем промокод
        order = await service.apply_promocode(order, promocode)
    
    await message.answer(
        f"✅ Промокод <b>{code}</b> применён!\n"
        f"Скидка: {order.discount}₽\n\n"
        + format_payment_summary(order, show_promocode_info=False),
        reply_markup=get_promocode_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)


@router.callback_query(F.data == "skip_promocode")
async def skip_promocode(callback: CallbackQuery, state: FSMContext):
    """Пропуск промокода — переход к оплате."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        # Обновляем статус на "Ожидает оплаты"
        await service.update_order_status(order, OrderStatus.PENDING_PAYMENT)
    
    payment_text = f"""💳 <b>Оплата заказа #{order.order_number}</b>

📷 Стоимость фотографий: {order.photos_cost}₽
🚚 Стоимость доставки: {order.delivery_cost}₽
"""
    
    if order.discount > 0:
        payment_text += f"🎟 Скидка: -{order.discount}₽\n"
    
    # Получаем данные для оплаты из настроек
    payment_phone = SettingsService.get(SettingKeys.PAYMENT_PHONE, "")
    payment_card = SettingsService.get(SettingKeys.PAYMENT_CARD, "")
    payment_receiver = SettingsService.get(SettingKeys.PAYMENT_RECEIVER, "")
    
    payment_text += f"""
<b>💰 Итого: {order.total_cost}₽</b>

━━━━━━━━━━━━━━━

<b>Оплата переводом на Т-банк:</b>

📱 По номеру телефона: <code>{payment_phone}</code>
💳 На карту: <code>{payment_card}</code>
👤 Получатель: {payment_receiver}

━━━━━━━━━━━━━━━

<b>Пришлите, пожалуйста, скриншот квитанции об оплате</b> 📎"""
    
    await callback.message.edit_text(
        payment_text,
        reply_markup=get_payment_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.waiting_payment_receipt)
    await callback.answer()


@router.callback_query(F.data == "back_to_promocode")
async def back_to_promocode(callback: CallbackQuery, state: FSMContext):
    """Возврат к промокоду."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if order:
            await callback.message.edit_text(
                format_payment_summary(order),
                reply_markup=get_promocode_keyboard(),
                parse_mode="HTML",
            )
    
    await state.set_state(OrderStates.selecting_delivery)
    await callback.answer()


@router.message(OrderStates.waiting_payment_receipt, F.photo)
async def process_payment_receipt_photo(message: Message, state: FSMContext, bot: Bot):
    """Обработка квитанции об оплате (фото)."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    file_id = message.photo[-1].file_id
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        # Сохраняем квитанцию
        order.payment_receipt_file_id = file_id
        await service.update_order_status(order, OrderStatus.PAID)
        
        # Отправляем уведомление менеджерам
        notification_service = NotificationService(bot)
        await notification_service.notify_receipt_uploaded(order, file_id)
    
    manager = SettingsService.get(SettingKeys.MANAGER_USERNAME, "manager")
    await message.answer(
        f"✅ <b>Спасибо! Ваш заказ #{order.order_number} принят в работу!</b>\n\n"
        "Мы сообщим вам, когда фотографии будут распечатаны и готовы к отправке.\n\n"
        f"Для связи с менеджером: @{manager}",
        reply_markup=get_final_keyboard(),
        parse_mode="HTML",
    )
    
    await state.clear()


@router.message(OrderStates.waiting_payment_receipt, F.document)
async def process_payment_receipt_document(message: Message, state: FSMContext, bot: Bot):
    """Обработка квитанции об оплате (документ)."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    file_id = message.document.file_id
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        order.payment_receipt_file_id = file_id
        await service.update_order_status(order, OrderStatus.PAID)
        
        # Отправляем уведомление менеджерам
        notification_service = NotificationService(bot)
        await notification_service.notify_receipt_uploaded(order, file_id)
    
    manager = SettingsService.get(SettingKeys.MANAGER_USERNAME, "manager")
    await message.answer(
        f"✅ <b>Спасибо! Ваш заказ #{order.order_number} принят в работу!</b>\n\n"
        "Мы сообщим вам, когда фотографии будут распечатаны и готовы к отправке.\n\n"
        f"Для связи с менеджером: @{manager}",
        reply_markup=get_final_keyboard(),
        parse_mode="HTML",
    )
    
    await state.clear()

