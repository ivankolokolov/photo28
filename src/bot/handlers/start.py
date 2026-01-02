"""Обработчик команды /start."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from pathlib import Path

from src.bot.states import OrderStates
from src.bot.keyboards import get_format_keyboard
from src.config import settings
from src.database import async_session
from src.services.order_service import OrderService

router = Router()

WELCOME_MESSAGE = """Здравствуйте! 👋

Я бот приёма заказов <b>Photo28</b>!

Какой формат фотографий вы хотите напечатать?

📷 <b>Форматы:</b>
• Полароид 7.6х10 стандарт
• Полароид 7.6х10 широкий
• Инстакс 5.4х8.6
• Классика 10х15 без рамки

Для связи с менеджером: @{manager}"""


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    await state.clear()
    
    # Создаём или получаем пользователя
    async with async_session() as session:
        service = OrderService(session)
        user = await service.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        
        # Создаём новый заказ-черновик
        order = await service.create_order(user)
        await state.update_data(order_id=order.id, user_id=user.id)
    
    # Отправляем приветствие
    await message.answer(
        WELCOME_MESSAGE.format(manager=settings.manager_username),
        reply_markup=get_format_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_format)


@router.callback_query(F.data == "new_order")
async def new_order(callback: CallbackQuery, state: FSMContext):
    """Создание нового заказа."""
    await state.clear()
    
    async with async_session() as session:
        service = OrderService(session)
        user = await service.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        
        order = await service.create_order(user)
        await state.update_data(order_id=order.id, user_id=user.id)
    
    await callback.message.edit_text(
        WELCOME_MESSAGE.format(manager=settings.manager_username),
        reply_markup=get_format_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_format)
    await callback.answer()

