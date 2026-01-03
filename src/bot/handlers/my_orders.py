"""Обработчики просмотра заказов."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.bot.states import MyOrdersStates
from src.bot.keyboards import get_my_orders_keyboard, get_order_detail_keyboard
from src.database import async_session
from src.services.order_service import OrderService

router = Router()


@router.callback_query(F.data == "my_orders")
async def show_my_orders(callback: CallbackQuery, state: FSMContext):
    """Показать мои заказы."""
    async with async_session() as session:
        service = OrderService(session)
        user = await service.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        
        orders = await service.get_user_orders(user, limit=10)
    
    if not orders:
        await callback.message.edit_text(
            "📋 У вас пока нет заказов.\n\n"
            "Нажмите кнопку ниже, чтобы сделать первый заказ!",
            reply_markup=get_my_orders_keyboard([]),
        )
    else:
        await callback.message.edit_text(
            "📋 <b>Ваши заказы:</b>\n\n"
            "Нажмите на заказ для просмотра деталей.",
            reply_markup=get_my_orders_keyboard(orders),
            parse_mode="HTML",
        )
    
    await state.set_state(MyOrdersStates.viewing_orders)
    await callback.answer()


@router.message(Command("orders"))
@router.message(Command("myorders"))
async def cmd_orders(message: Message, state: FSMContext):
    """Команда /orders или /myorders для просмотра заказов."""
    async with async_session() as session:
        service = OrderService(session)
        user = await service.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        
        orders = await service.get_user_orders(user, limit=10)
    
    if not orders:
        await message.answer(
            "📋 У вас пока нет заказов.\n\n"
            "Нажмите кнопку ниже, чтобы сделать первый заказ!",
            reply_markup=get_my_orders_keyboard([]),
        )
    else:
        await message.answer(
            "📋 <b>Ваши заказы:</b>\n\n"
            "Нажмите на заказ для просмотра деталей.",
            reply_markup=get_my_orders_keyboard(orders),
            parse_mode="HTML",
        )
    
    await state.set_state(MyOrdersStates.viewing_orders)


@router.callback_query(F.data.startswith("order_details:"))
async def show_order_details(callback: CallbackQuery, state: FSMContext):
    """Показать детали заказа."""
    order_id = int(callback.data.split(":")[1])
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
        
        photos_by_format = order.photos_by_format()
        
        # Формируем текст деталей
        lines = [
            f"📋 <b>Заказ #{order.order_number}</b>\n",
            f"📊 Статус: <b>{order.status.display_name}</b>",
            f"📅 Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}",
            "",
            "<b>Фотографии:</b>",
        ]
        
        for fmt, count in photos_by_format.items():
            lines.append(f"• {fmt.short_name}: {count} шт.")
        
        lines.extend([
            "",
            "<b>Стоимость:</b>",
            f"• Фотографии: {order.photos_cost}₽",
            f"• Доставка: {order.delivery_cost}₽",
        ])
        
        if order.discount > 0:
            lines.append(f"• Скидка: -{order.discount}₽")
        
        lines.append(f"• <b>Итого: {order.total_cost}₽</b>")
        
        if order.delivery_type:
            lines.extend([
                "",
                f"🚚 Доставка: {order.delivery_type.display_name}",
            ])
            if order.delivery_address:
                lines.append(f"📍 Адрес: {order.delivery_address}")
        
        text = "\n".join(lines)
    
    await callback.message.edit_text(
        text,
        reply_markup=get_order_detail_keyboard(order),
        parse_mode="HTML",
    )
    
    await state.set_state(MyOrdersStates.viewing_order_details)
    await callback.answer()

