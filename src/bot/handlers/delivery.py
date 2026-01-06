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
from src.database import async_session
from src.services.order_service import OrderService
from src.services.settings_service import SettingsService, SettingKeys
from src.models.order import DeliveryType

router = Router()


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


# ================== ВЫБОР ДОСТАВКИ ==================

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


# ================== ОЗОН ДОСТАВКА ==================

@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:ozon")
async def delivery_ozon_start(callback: CallbackQuery, state: FSMContext):
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


@router.message(OrderStates.entering_ozon_phone)
async def process_ozon_phone(message: Message, state: FSMContext):
    """Обработка телефона для ОЗОН."""
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


@router.message(OrderStates.entering_ozon_city)
async def process_ozon_city(message: Message, state: FSMContext):
    """Обработка города для ОЗОН."""
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
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        await service.set_delivery_info(
            order,
            delivery_type=DeliveryType.OZON,
            city=city,
            phone=phone,
        )
        
        order = await service.get_order_by_id(order_id)
    
    await message.answer(
        f"✅ <b>Данные доставки сохранены</b>\n\n"
        f"📦 Способ: ОЗОН доставка\n"
        f"📱 Телефон: {phone}\n"
        f"🏙 Город: {city}\n"
        f"💰 Стоимость доставки: {order.delivery_cost}₽\n\n"
        "После оформления заказа мы попросим вас выбрать пункт выдачи в приложении ОЗОН.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)


# ================== КУРЬЕРСКАЯ ДОСТАВКА ==================

@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:courier")
async def delivery_courier_start(callback: CallbackQuery, state: FSMContext):
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


@router.message(OrderStates.entering_courier_phone)
async def process_courier_phone(message: Message, state: FSMContext):
    """Обработка телефона для курьера."""
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


@router.message(OrderStates.entering_courier_address)
async def process_courier_address(message: Message, state: FSMContext):
    """Обработка адреса для курьера."""
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


@router.message(OrderStates.entering_courier_name)
async def process_courier_name(message: Message, state: FSMContext):
    """Обработка ФИО для курьера."""
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


@router.message(OrderStates.entering_courier_datetime)
async def process_courier_datetime(message: Message, state: FSMContext):
    """Обработка даты/времени для курьера."""
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
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        # Собираем полный адрес
        full_address = f"{address}\nПолучатель: {name}\nВремя: {datetime_str}"
        
        await service.set_delivery_info(
            order,
            delivery_type=DeliveryType.COURIER,
            address=full_address,
            phone=phone,
        )
        
        order = await service.get_order_by_id(order_id)
    
    await message.answer(
        f"✅ <b>Данные доставки сохранены</b>\n\n"
        f"🚗 Способ: Курьер по Москве\n"
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

@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:pickup")
async def delivery_pickup_start(callback: CallbackQuery, state: FSMContext):
    """Начало ввода данных самовывоза — запрос телефона."""
    await state.update_data(delivery_type="pickup")
    
    await callback.message.edit_text(
        "🏠 <b>Самовывоз</b>\n\n"
        "📍 Адрес: г. Москва, м. Чертановская\n"
        "Балаклавский пр-т 12к3, подъезд 1\n\n"
        "Шаг 1 из 2: Введите номер телефона для связи\n\n"
        "📱 Формат: +7XXXXXXXXXX",
        reply_markup=get_back_keyboard("back_to_delivery"),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.entering_pickup_phone)
    await callback.answer()


@router.message(OrderStates.entering_pickup_phone)
async def process_pickup_phone(message: Message, state: FSMContext):
    """Обработка телефона для самовывоза."""
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


@router.message(OrderStates.entering_pickup_name)
async def process_pickup_name(message: Message, state: FSMContext):
    """Обработка имени для самовывоза."""
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
    
    async with async_session() as session:
        service = OrderService(session)
        order = await service.get_order_by_id(order_id)
        
        if not order:
            await message.answer("Заказ не найден. Начните заново: /start")
            return
        
        await service.set_delivery_info(
            order,
            delivery_type=DeliveryType.PICKUP,
            phone=phone,
            address=f"Получатель: {name}",
        )
    
    await message.answer(
        f"✅ <b>Данные сохранены</b>\n\n"
        f"🏠 Способ: Самовывоз\n"
        f"📍 Адрес: г. Москва, м. Чертановская\n"
        f"Балаклавский пр-т 12к3, подъезд 1\n"
        f"📱 Телефон: {phone}\n"
        f"👤 Имя: {name}\n\n"
        f"После оформления заказа с вами свяжется менеджер для согласования времени.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)


# ================== СВЯЗЬ С МЕНЕДЖЕРОМ ==================

@router.callback_query(OrderStates.selecting_delivery, F.data == "delivery:manager")
async def delivery_manager(callback: CallbackQuery, state: FSMContext):
    """Связь с менеджером."""
    manager = SettingsService.get(SettingKeys.MANAGER_USERNAME, "manager")
    await callback.message.edit_text(
        f"💬 Пожалуйста, напишите менеджеру: @{manager}\n\n"
        "Он поможет подобрать удобный способ доставки.",
        reply_markup=get_delivery_confirm_keyboard(),
        parse_mode="HTML",
    )
    
    await callback.answer()


# ================== КНОПКА НАЗАД ==================

@router.callback_query(F.data == "back_to_delivery")
async def back_to_delivery(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору доставки."""
    await callback.message.edit_text(
        DELIVERY_MESSAGE,
        reply_markup=get_delivery_keyboard(),
        parse_mode="HTML",
    )
    
    await state.set_state(OrderStates.selecting_delivery)
    await callback.answer()
