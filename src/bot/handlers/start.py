"""Обработчик команды /start и /cancel."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.states import OrderStates
from src.bot.context import StudioContext
from src.bot.keyboards import get_format_keyboard
from src.services.settings_service import SettingKeys
from src.models.order import OrderStatus

router = Router()


def get_welcome_message(ctx: StudioContext) -> str:
    """Возвращает приветственное сообщение с актуальными данными."""
    manager = ctx.studio.manager_username or "manager"

    # Формируем список форматов динамически из БД
    products = ctx.products.top_level()
    format_lines = []
    for p in products:
        children = ctx.products.children(p.id)
        if children:
            variants = ", ".join(c.name.lower() for c in children)
            format_lines.append(f"• {p.emoji} {p.name} ({variants})")
        else:
            format_lines.append(f"• {p.emoji} {p.name}")

    formats_text = "\n".join(format_lines) if format_lines else "• Форматы загружаются..."

    # Берём шаблон из настроек или используем дефолтный
    template = ctx.settings.get(SettingKeys.WELCOME_MESSAGE, "")
    if template:
        try:
            return template.replace("{formats}", formats_text).replace("{manager}", manager).replace("{studio_name}", ctx.studio.name)
        except Exception:
            pass

    # Фоллбэк если шаблон пустой или ошибка
    return (
        f"Здравствуйте! 👋\n\n"
        f"Я бот приёма заказов <b>{ctx.studio.name}</b>!\n\n"
        f"Какой формат фотографий вы хотите напечатать?\n\n"
        f"📷 <b>Форматы:</b>\n{formats_text}\n\n"
        f"Для связи с менеджером: @{manager}"
    )


CONTINUE_ORDER_MESSAGE = """👋 С возвращением!

У вас есть незавершённый заказ:
📷 Загружено фото: <b>{photos_count}</b> шт.

Что хотите сделать?"""


def get_continue_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура продолжения заказа."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="▶️ Продолжить заказ",
            callback_data=f"continue_order:{order_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🆕 Начать новый заказ",
            callback_data="new_order"
        )
    )
    return builder.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, ctx: StudioContext):
    """Обработчик команды /start."""
    await state.clear()

    user = await ctx.orders.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    draft_order = await ctx.orders.get_user_draft_order(user)

    if draft_order and draft_order.photos_count > 0:
        await message.answer(
            CONTINUE_ORDER_MESSAGE.format(photos_count=draft_order.photos_count),
            reply_markup=get_continue_keyboard(draft_order.id),
            parse_mode="HTML",
        )
        return

    order = await ctx.orders.create_order(user)
    await state.update_data(order_id=order.id, user_id=user.id)

    await message.answer(
        get_welcome_message(ctx),
        reply_markup=get_format_keyboard(ctx),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_format)


@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    """Показывает Chat ID текущего чата."""
    chat_id = message.chat.id
    chat_type = message.chat.type
    chat_title = message.chat.title or "Личный чат"

    await message.answer(
        f"📍 <b>Информация о чате:</b>\n\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Тип: {chat_type}\n"
        f"Название: {chat_title}\n\n"
        f"Скопируйте Chat ID и вставьте в настройках админки.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("continue_order:"))
async def continue_order(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Продолжение существующего заказа."""
    order_id = int(callback.data.split(":")[1])

    order = await ctx.orders.get_order_by_id(order_id)

    if not order or order.status != OrderStatus.DRAFT:
        await callback.answer("Заказ не найден или уже оформлен")
        return

    await state.update_data(order_id=order.id, user_id=order.user_id)

    from src.bot.handlers.order import show_order_summary
    await show_order_summary(callback.message, order, ctx, edit=True)

    await state.set_state(OrderStates.reviewing_order)
    await callback.answer()


@router.callback_query(F.data == "new_order")
async def new_order(callback: CallbackQuery, state: FSMContext, ctx: StudioContext):
    """Создание нового заказа."""
    await state.clear()

    user = await ctx.orders.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
    )

    order = await ctx.orders.create_order(user)
    await state.update_data(order_id=order.id, user_id=user.id)

    await callback.message.edit_text(
        get_welcome_message(ctx),
        reply_markup=get_format_keyboard(ctx),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_format)
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, ctx: StudioContext):
    """Команда /cancel — отмена текущего действия."""
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "Нет активного действия для отмены.\n"
            "Используйте /start для начала нового заказа."
        )
        return

    await state.clear()

    user = await ctx.orders.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    draft_order = await ctx.orders.get_user_draft_order(user)

    if draft_order and draft_order.photos_count > 0:
        await message.answer(
            f"✅ Действие отменено.\n\n"
            f"У вас есть незавершённый заказ ({draft_order.photos_count} фото).\n"
            f"Используйте /start чтобы продолжить или начать заново.",
        )
    else:
        await message.answer(
            "✅ Действие отменено.\n"
            "Используйте /start для начала нового заказа.",
        )


@router.message(Command("help"))
async def cmd_help(message: Message, ctx: StudioContext):
    """Команда /help — справка."""
    manager = ctx.studio.manager_username or "manager"
    await message.answer(
        "<b>📖 Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — Начать заказ или продолжить незавершённый\n"
        "/cancel — Отменить текущее действие\n"
        "/myorders — Посмотреть свои заказы\n"
        "/help — Эта справка\n\n"
        "<b>Как сделать заказ:</b>\n"
        "1. Выберите формат фото\n"
        "2. Отправьте фотографии (минимум 10)\n"
        "3. Выберите способ доставки\n"
        "4. Оплатите и отправьте чек\n\n"
        f"<b>Связь с менеджером:</b> @{manager}",
        parse_mode="HTML",
    )
