"""Обработчики доставки с пошаговым вводом и валидацией."""
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from src.bot.states import OrderStates
from src.bot.keyboards import (
    get_delivery_keyboard,
    get_delivery_confirm_keyboard,
    get_back_keyboard,
)
from src.services.settings_service import SettingKeys
from src.models.order import DeliveryType
from src.services.delivery_options import delivery_display_name, delivery_cost, delivery_is_enabled

def validate_phone(phone: str) -> tuple[bool, str]:
    """Валидация телефона. Возвращает (is_valid, normalized_phone)."""
    # Убираем всё кроме цифр и +
    cleaned = re.sub(r'[^\d+]', '', phone)

    # Проверяем формат
    if cleaned.startswith('+7'):
        digits = cleaned[2:]
    elif cleaned.startswith('8') and len(cleaned) == 11:
        digits = cleaned[1:]
        cleaned = '+7' + digits
    elif cleaned.startswith('7') and len(cleaned) == 11:
        digits = cleaned[1:]
        cleaned = '+7' + digits
    else:
        digits = cleaned.lstrip('+')

    if len(digits) != 10:
        return False, ""

    if not digits.isdigit():
        return False, ""

    return True, f"+7{digits}"

def get_delivery_message(ctx) -> str:
    """Формирует сообщение с доступными способами доставки из настроек студии."""
    lines = ["🚚 <b>Выберите способ доставки:</b>\n"]

    methods = [
        (DeliveryType.OZON, "📦", SettingKeys.DELIVERY_OZON_DESCRIPTION),
        (DeliveryType.COURIER, "🚗", SettingKeys.DELIVERY_COURIER_DESCRIPTION),
        (DeliveryType.PICKUP, "🏠", SettingKeys.DELIVERY_PICKUP_DESCRIPTION),
    ]

    for dt, emoji, desc_key in methods:
        if not delivery_is_enabled(ctx.settings, dt):
            continue

        name = delivery_display_name(ctx.settings, dt)
        price = delivery_cost(ctx.settings, dt)
        desc = ctx.settings.get(desc_key, "")

        price_text = f" — {price}₽" if price > 0 else " — бесплатно" if dt == DeliveryType.PICKUP else ""
        lines.append(f"<b>{emoji} {name}{price_text}</b>")

        if dt == DeliveryType.PICKUP:
            pickup_addr = ctx.settings.get(SettingKeys.DELIVERY_PICKUP_ADDRESS, "")
            if pickup_addr:
                for addr_line in pickup_addr.split("\n"):
                    lines.append(f"• {addr_line.strip()}")

        if desc:
            for desc_line in desc.split("\n"):
                lines.append(f"• {desc_line.strip()}")

        lines.append("")

    return "\n".join(lines)

# ================== ВЫБОР ДОСТАВКИ ==================

async def select_delivery(callback: CallbackQuery, state: FSMContext, ctx):
    """Переход к выбору доставки."""
    await callback.message.edit_text(
        get_delivery_message(ctx),
        reply_markup=get_delivery_keyboard(ctx),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_delivery)
    await callback.answer()

# ================== ОЗОН ДОСТАВКА ==================

async def delivery_ozon_start(callback: CallbackQuery, state: FSMContext, ctx):
    """Начало ввода данных ОЗОН — запрос телефона."""
    await state.update_data(delivery_type="ozon")

    await callback.message.edit_text(
        "📦 <b>Доставка ОЗОН</b>\n\n"
        "Шаг 1 из 2: Введите номер телефона\n\n"
        "📱 Формат: +7XXXXXXXXXX или 8XXXXXXXXXX",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_ozon_phone)
    await callback.answer()

async def process_ozon_phone(message: Message, state: FSMContext, ctx):
    """Обработка телефона для ОЗОН."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите номер телефона текстом.")
        return

    is_valid, phone = validate_phone(message.text)

    if not is_valid:
        await message.answer(
            "❌ Неверный формат телефона.\n\n"
            "Введите номер в формате:\n"
            "• +79991234567\n"
            "• 89991234567\n"
            "• 9991234567",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    await state.update_data(delivery_phone=phone)

    await message.answer(
        "📦 <b>Доставка ОЗОН</b>\n\n"
        f"✅ Телефон: {phone}\n\n"
        "Шаг 2 из 2: Введите город доставки",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_ozon_city)

async def process_ozon_city(message: Message, state: FSMContext, ctx):
    """Обработка города для ОЗОН."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите город текстом.")
        return

    city = message.text.strip()

    if len(city) < 2:
        await message.answer(
            "❌ Введите название города (минимум 2 символа).",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    phone = data.get("delivery_phone")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order:
        await message.answer("Заказ не найден. Начните заново: /start")
        return

    await ctx.orders.set_delivery_info(
        order,
        delivery_type=DeliveryType.OZON,
        city=city,
        phone=phone,
    )

    order = await ctx.orders.get_order_by_id(order_id)

    ozon_name = delivery_display_name(ctx.settings, DeliveryType.OZON)

    await message.answer(
        f"✅ <b>Данные доставки сохранены</b>\n\n"
        f"📦 Способ: {ozon_name}\n"
        f"📱 Телефон: {phone}\n"
        f"🏙 Город: {city}\n"
        f"💰 Стоимость доставки: {order.delivery_cost}₽\n\n"
        "После оформления заказа мы попросим вас выбрать пункт выдачи в приложении ОЗОН.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_delivery)

# ================== КУРЬЕРСКАЯ ДОСТАВКА ==================

async def delivery_courier_start(callback: CallbackQuery, state: FSMContext, ctx):
    """Начало ввода данных курьера — запрос телефона."""
    await state.update_data(delivery_type="courier")

    await callback.message.edit_text(
        "🚗 <b>Доставка курьером</b>\n\n"
        "Шаг 1 из 4: Введите номер телефона\n\n"
        "📱 Формат: +7XXXXXXXXXX или 8XXXXXXXXXX",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_courier_phone)
    await callback.answer()

async def process_courier_phone(message: Message, state: FSMContext, ctx):
    """Обработка телефона для курьера."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите номер телефона текстом.")
        return

    is_valid, phone = validate_phone(message.text)

    if not is_valid:
        await message.answer(
            "❌ Неверный формат телефона.\n\n"
            "Введите номер в формате:\n"
            "• +79991234567\n"
            "• 89991234567",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    await state.update_data(delivery_phone=phone)

    await message.answer(
        "🚗 <b>Доставка курьером</b>\n\n"
        f"✅ Телефон: {phone}\n\n"
        "Шаг 2 из 4: Введите адрес доставки\n\n"
        "Например: ул. Ленина, д. 10, кв. 5",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_courier_address)

async def process_courier_address(message: Message, state: FSMContext, ctx):
    """Обработка адреса для курьера."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите адрес текстом.")
        return

    address = message.text.strip()

    if len(address) < 10:
        await message.answer(
            "❌ Адрес слишком короткий. Укажите полный адрес.",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    await state.update_data(delivery_address=address)

    await message.answer(
        "🚗 <b>Доставка курьером</b>\n\n"
        f"✅ Адрес: {address}\n\n"
        "Шаг 3 из 4: Введите ФИО получателя",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_courier_name)

async def process_courier_name(message: Message, state: FSMContext, ctx):
    """Обработка ФИО для курьера."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите ФИО текстом.")
        return

    name = message.text.strip()

    if len(name) < 3 or len(name.split()) < 2:
        await message.answer(
            "❌ Введите ФИО полностью (минимум имя и фамилия).",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    await state.update_data(delivery_name=name)

    await message.answer(
        "🚗 <b>Доставка курьером</b>\n\n"
        f"✅ ФИО: {name}\n\n"
        "Шаг 4 из 4: Укажите желаемую дату и время\n\n"
        "Например: 15 января, с 14:00 до 18:00\n"
        "⚠️ Не ранее чем через 2 дня",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_courier_datetime)

async def process_courier_datetime(message: Message, state: FSMContext, ctx):
    """Обработка даты/времени для курьера."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите дату и время текстом.")
        return

    datetime_str = message.text.strip()

    if len(datetime_str) < 5:
        await message.answer(
            "❌ Укажите дату и время доставки.",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    phone = data.get("delivery_phone")
    address = data.get("delivery_address")
    name = data.get("delivery_name")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order:
        await message.answer("Заказ не найден. Начните заново: /start")
        return

    # Собираем полный адрес
    full_address = f"{address}\nПолучатель: {name}\nВремя: {datetime_str}"

    await ctx.orders.set_delivery_info(
        order,
        delivery_type=DeliveryType.COURIER,
        address=full_address,
        phone=phone,
    )

    order = await ctx.orders.get_order_by_id(order_id)

    courier_name = delivery_display_name(ctx.settings, DeliveryType.COURIER)

    await message.answer(
        f"✅ <b>Данные доставки сохранены</b>\n\n"
        f"🚗 Способ: {courier_name}\n"
        f"📱 Телефон: {phone}\n"
        f"📍 Адрес: {address}\n"
        f"👤 Получатель: {name}\n"
        f"🕐 Время: {datetime_str}\n\n"
        f"После оформления заказа с вами свяжется менеджер для подтверждения.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_delivery)

# ================== САМОВЫВОЗ ==================

async def delivery_pickup_start(callback: CallbackQuery, state: FSMContext, ctx):
    """Начало ввода данных самовывоза — запрос телефона."""
    await state.update_data(delivery_type="pickup")

    pickup_name = delivery_display_name(ctx.settings, DeliveryType.PICKUP)
    pickup_addr = ctx.settings.get(SettingKeys.DELIVERY_PICKUP_ADDRESS, "")
    addr_text = f"\n📍 Адрес: {pickup_addr}\n" if pickup_addr else "\n"

    await callback.message.edit_text(
        f"🏠 <b>{pickup_name}</b>\n{addr_text}\n"
        "Шаг 1 из 2: Введите номер телефона для связи\n\n"
        "📱 Формат: +7XXXXXXXXXX",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_pickup_phone)
    await callback.answer()

async def process_pickup_phone(message: Message, state: FSMContext, ctx):
    """Обработка телефона для самовывоза."""
    if not message.text:
        await message.answer(
            "📝 Пожалуйста, введите номер телефона текстом.",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    is_valid, phone = validate_phone(message.text)

    if not is_valid:
        await message.answer(
            "❌ Неверный формат телефона.\n\n"
            "Введите номер в формате:\n"
            "• +79991234567\n"
            "• 89991234567",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    await state.update_data(delivery_phone=phone)

    await message.answer(
        "🏠 <b>Самовывоз</b>\n\n"
        f"✅ Телефон: {phone}\n\n"
        "Шаг 2 из 2: Введите ваше имя",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.entering_pickup_name)

async def process_pickup_name(message: Message, state: FSMContext, ctx):
    """Обработка имени для самовывоза."""
    if not message.text:
        await message.answer("📝 Пожалуйста, введите имя текстом.")
        return

    name = message.text.strip()

    if len(name) < 2:
        await message.answer(
            "❌ Введите ваше имя.",
            reply_markup=get_back_keyboard("back_to_delivery"),
        )
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    phone = data.get("delivery_phone")

    order = await ctx.orders.get_order_by_id(order_id)

    if not order:
        await message.answer("Заказ не найден. Начните заново: /start")
        return

    await ctx.orders.set_delivery_info(
        order,
        delivery_type=DeliveryType.PICKUP,
        phone=phone,
        address=f"Получатель: {name}",
    )

    pickup_addr = ctx.settings.get(SettingKeys.DELIVERY_PICKUP_ADDRESS, "")
    pickup_name_str = delivery_display_name(ctx.settings, DeliveryType.PICKUP)

    await message.answer(
        f"✅ <b>Данные сохранены</b>\n\n"
        f"🏠 Способ: {pickup_name_str}\n"
        + (f"📍 Адрес: {pickup_addr}\n" if pickup_addr else "")
        + f"📱 Телефон: {phone}\n"
        f"👤 Имя: {name}\n\n"
        f"После оформления заказа с вами свяжется менеджер для согласования времени.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_delivery)

# ================== СВЯЗЬ С МЕНЕДЖЕРОМ ==================

async def delivery_manager(callback: CallbackQuery, state: FSMContext, ctx):
    """Связь с менеджером."""
    manager = ctx.studio.manager_username or "manager"
    await callback.message.edit_text(
        f"💬 Пожалуйста, напишите менеджеру: @{manager}\n\n"
        "Он поможет подобрать удобный способ доставки.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()

# ================== КНОПКА НАЗАД ==================

async def back_to_delivery(callback: CallbackQuery, state: FSMContext, ctx):
    """Возврат к выбору доставки."""
    await callback.message.edit_text(
        get_delivery_message(ctx),
        reply_markup=get_delivery_keyboard(ctx),
        parse_mode="HTML",
    )

    await state.set_state(OrderStates.selecting_delivery)
    await callback.answer()

def build_delivery_router() -> Router:
    r = Router(name="delivery")
    r.callback_query.register(select_delivery, F.data == "select_delivery")
    r.callback_query.register(delivery_ozon_start, F.data == "delivery:ozon")
    r.message.register(process_ozon_phone, OrderStates.entering_ozon_phone)
    r.message.register(process_ozon_city, OrderStates.entering_ozon_city)
    r.callback_query.register(delivery_courier_start, F.data == "delivery:courier")
    r.message.register(process_courier_phone, OrderStates.entering_courier_phone)
    r.message.register(process_courier_address, OrderStates.entering_courier_address)
    r.message.register(process_courier_name, OrderStates.entering_courier_name)
    r.message.register(process_courier_datetime, OrderStates.entering_courier_datetime)
    r.callback_query.register(delivery_pickup_start, F.data == "delivery:pickup")
    r.message.register(process_pickup_phone, OrderStates.entering_pickup_phone)
    r.message.register(process_pickup_name, OrderStates.entering_pickup_name)
    r.callback_query.register(delivery_manager, F.data == "delivery:manager")
    r.callback_query.register(back_to_delivery, F.data == "back_to_delivery")
    return r
