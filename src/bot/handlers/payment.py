"""Обработчики оплаты."""
from aiogram import Router, F
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
from src.models.order import OrderStatus
from src.config import settings

router = Router()


def format_payment_summary(order, show_promocode_info: bool = True) -> str:
    """Форматирует сводку для оплаты."""
    lines = [
        "💰 **Стоимость заказа:**\n",
        f"📷 Фотографии: {order.photos_cost}₽",
        f"🚚 Доставка: {order.delivery_cost}₽",
    ]
    
    if order.discount > 0:
        lines.append(f"🎟 Скидка: -{order.discount}₽")
    
    lines.append(f"\n**Итого к оплате: {order.total_cost}₽**")
    
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
        parse_mode="Markdown",
    )
    
    await callback.answer()


@router.callback_query(F.data == "enter_promocode")
async def enter_promocode(callback: CallbackQuery, state: FSMContext):
    """Ввод промокода."""
    await callback.message.edit_text(
        "🎟 **Введите промокод:**\n\n"
        "Отправьте промокод в сообщении.",
        parse_mode="Markdown",
    )
    
    await state.set_state(OrderStates.entering_promocode)
    await callback.answer()


@router.message(OrderStates.entering_promocode)
async def process_promocode(message: Message, state: FSMContext):
    """Обработка промокода."""
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
        
        # Проверяем валидность
        is_valid, error_msg = promocode.is_valid(order.photos_cost)
        
        if not is_valid:
            await message.answer(
                f"❌ Промокод не применён: {error_msg}\n\n"
                "Попробуйте другой промокод или перейдите к оплате.",
                reply_markup=get_promocode_keyboard(),
            )
            return
        
        # Применяем промокод
        order = await service.apply_promocode(order, promocode)
    
    await message.answer(
        f"✅ Промокод **{code}** применён!\n"
        f"Скидка: {order.discount}₽\n\n"
        + format_payment_summary(order, show_promocode_info=False),
        reply_markup=get_promocode_keyboard(),
        parse_mode="Markdown",
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
    
    payment_text = f"""
💳 **Оплата заказа #{order.order_number}**

📷 Стоимость фотографий: {order.photos_cost}₽
🚚 Стоимость доставки: {order.delivery_cost}₽
"""
    
    if order.discount > 0:
        payment_text += f"🎟 Скидка: -{order.discount}₽\n"
    
    payment_text += f"""
**💰 Итого: {order.total_cost}₽**

━━━━━━━━━━━━━━━

**Оплата переводом на Т-банк:**

📱 По номеру телефона: `{settings.payment_phone}`
💳 На карту: `{settings.payment_card}`
👤 Получатель: {settings.payment_receiver}

━━━━━━━━━━━━━━━

**Пришлите, пожалуйста, скриншот квитанции об оплате** 📎
"""
    
    await callback.message.edit_text(
        payment_text,
        reply_markup=get_payment_keyboard(),
        parse_mode="Markdown",
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
                parse_mode="Markdown",
            )
    
    await state.set_state(OrderStates.selecting_delivery)
    await callback.answer()


@router.message(OrderStates.waiting_payment_receipt, F.photo)
async def process_payment_receipt_photo(message: Message, state: FSMContext):
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
    
    await message.answer(
        f"✅ **Спасибо! Ваш заказ #{order.order_number} принят в работу!**\n\n"
        "Мы сообщим вам, когда фотографии будут распечатаны и готовы к отправке.\n\n"
        f"Для связи с менеджером: @{settings.manager_username}",
        reply_markup=get_final_keyboard(),
        parse_mode="Markdown",
    )
    
    await state.clear()


@router.message(OrderStates.waiting_payment_receipt, F.document)
async def process_payment_receipt_document(message: Message, state: FSMContext):
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
    
    await message.answer(
        f"✅ **Спасибо! Ваш заказ #{order.order_number} принят в работу!**\n\n"
        "Мы сообщим вам, когда фотографии будут распечатаны и готовы к отправке.\n\n"
        f"Для связи с менеджером: @{settings.manager_username}",
        reply_markup=get_final_keyboard(),
        parse_mode="Markdown",
    )
    
    await state.clear()

