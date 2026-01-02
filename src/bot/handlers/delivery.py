"""Обработчики доставки."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.bot.states import OrderStates
from src.bot.keyboards import (
    get_delivery_keyboard,
    get_delivery_confirm_keyboard,
)
from src.database import async_session
from src.services.order_service import OrderService
from src.models.order import DeliveryType
from src.config import settings

router = Router()

DELIVERY_MESSAGE = """🚚 <b>Выберите способ доставки:</b>

<b>📦 ОЗОН доставка в пункт выдачи</b>
• Стоимость: 100₽
• Срок доставки: от 4 дней
• Необходимо наличие приложения ОЗОН

<b>🚗 Курьером по Москве</b>
• Служба Достависта
• Время и стоимость по согласованию

<b>🏠 Самовывоз</b>
• г. Москва, м. Чертановская
• Балаклавский пр-т 12к3, подъезд 1
• Время по согласованию"""

OZON_DELIVERY_MESSAGE = """📦 <b>Доставка ОЗОН</b>

Напишите в одном сообщении:
• Город доставки
• Ваш номер телефона

После оформления доставки мы попросим вас выбрать пункт выдачи в приложении."""

COURIER_DELIVERY_MESSAGE = """🚗 <b>Доставка курьером</b>

Напишите в одном сообщении:
• Адрес доставки
• Ваш номер телефона
• Дата и время (не ранее чем через 2 дня)

После оформления заказа с вами свяжется менеджер."""

PICKUP_MESSAGE = """🏠 <b>Самовывоз</b>

Адрес: г. Москва, м. Чертановская, Балаклавский пр-т 12к3, подъезд 1

После оформления заказа с вами свяжется менеджер для согласования времени."""


@router.callback_query(F.data == "select_delivery")
async def select_delivery(callback: CallbackQuery, state: FSMContext):
    """Переход к выбору доставки."""
    await callback.message.edit_text(
        DELIVERY_MESSAGE,
        reply_markup=get_delivery_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)
    await callback.answer()


@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:ozon")
async def delivery_ozon(callback: CallbackQuery, state: FSMContext):
    """Выбор доставки ОЗОН."""
    await state.update_data(delivery_type="ozon")
    
    await callback.message.edit_text(
        OZON_DELIVERY_MESSAGE,
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.entering_ozon_delivery)
    await callback.answer()


@router.message(OrderStates.entering_ozon_delivery)
async def process_ozon_delivery(message: Message, state: FSMContext):
    """Обработка данных доставки ОЗОН."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    # Парсим данные (город и телефон)
    text = message.text.strip()
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        # Сохраняем данные доставки
        await service.set_delivery_info(
            order,
            delivery_type=DeliveryType.OZON,
            city=text,  # Весь текст как город/телефон
            phone=text,
        )
        
        # Пересчитываем стоимость
        order = await service.get_order_by_id(order_id)
    
    await message.answer(
        f"✅ <b>Данные доставки сохранены</b>\n\n"
        f"📦 Способ: ОЗОН доставка\n"
        f"📍 Данные: {text}\n"
        f"💰 Стоимость доставки: {order.delivery_cost}₽",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)


@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:courier")
async def delivery_courier(callback: CallbackQuery, state: FSMContext):
    """Выбор курьерской доставки."""
    await state.update_data(delivery_type="courier")
    
    await callback.message.edit_text(
        COURIER_DELIVERY_MESSAGE,
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.entering_courier_delivery)
    await callback.answer()


@router.message(OrderStates.entering_courier_delivery)
async def process_courier_delivery(message: Message, state: FSMContext):
    """Обработка данных курьерской доставки."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    text = message.text.strip()
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        await service.set_delivery_info(
            order,
            delivery_type=DeliveryType.COURIER,
            address=text,
            phone=text,
        )
        
        order = await service.get_order_by_id(order_id)
    
    await message.answer(
        f"✅ <b>Данные доставки сохранены</b>\n\n"
        f"🚗 Способ: Курьер по Москве\n"
        f"📍 Данные: {text}\n\n"
        f"После оформления заказа с вами свяжется менеджер.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)


@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:pickup")
async def delivery_pickup(callback: CallbackQuery, state: FSMContext):
    """Выбор самовывоза."""
    data = await state.get_data()
    order_id = data.get("order_id")
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        await service.set_delivery_info(
            order,
            delivery_type=DeliveryType.PICKUP,
        )
    
    await callback.message.edit_text(
        PICKUP_MESSAGE,
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await callback.answer()


@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:manager")
async def delivery_manager(callback: CallbackQuery, state: FSMContext):
    """Связь с менеджером."""
    await callback.message.edit_text(
        f"💬 Пожалуйста, напишите менеджеру: @{settings.manager_username}\n\n"
        "Он поможет подобрать удобный способ доставки.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await callback.answer()
