"""Основные клавиатуры бота."""
from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.models.photo import PhotoFormat
from src.models.order import Order


def get_format_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора формата фотографий."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="📷 Полароид 7.6х10 стандарт",
            callback_data=f"format:{PhotoFormat.POLAROID_STANDARD.value}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📷 Полароид 7.6х10 широкий",
            callback_data=f"format:{PhotoFormat.POLAROID_WIDE.value}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📷 Инстакс 5.4х8.6",
            callback_data=f"format:{PhotoFormat.INSTAX.value}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📷 Классика 10х15 без рамки",
            callback_data=f"format:{PhotoFormat.CLASSIC.value}"
        )
    )
    
    return builder.as_markup()


def get_photo_actions_keyboard(has_photos: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура действий при загрузке фото."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить фото другого формата",
            callback_data="add_another_format"
        )
    )
    
    if has_photos:
        builder.row(
            InlineKeyboardButton(
                text="✅ Закончить отбор фото",
                callback_data="finish_photos"
            )
        )
    
    return builder.as_markup()


def get_order_summary_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура сводки заказа."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить фото другого формата",
            callback_data="add_another_format"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить лишние фото",
            callback_data="delete_photos"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🚚 Перейти к выбору доставки",
            callback_data="select_delivery"
        )
    )
    
    return builder.as_markup()


def get_delivery_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора доставки."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="📦 ОЗОН доставка (100₽)",
            callback_data="delivery:ozon"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🚗 Курьером по Москве",
            callback_data="delivery:courier"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏠 Самовывоз (бесплатно)",
            callback_data="delivery:pickup"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Связаться с менеджером",
            callback_data="delivery:manager"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Вернуться к выбору фото",
            callback_data="back_to_photos"
        )
    )
    
    return builder.as_markup()


def get_delivery_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения доставки."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Вернуться к выбору заказа",
            callback_data="back_to_summary"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💳 К оплате заказа",
            callback_data="go_to_payment"
        )
    )
    
    return builder.as_markup()


def get_promocode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура ввода промокода."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Вернуться к выбору фото",
            callback_data="back_to_summary"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🎟 Ввести промокод",
            callback_data="enter_promocode"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💳 Перейти к оплате",
            callback_data="skip_promocode"
        )
    )
    
    return builder.as_markup()


def get_payment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура оплаты."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Вернуться назад",
            callback_data="back_to_promocode"
        )
    )
    
    return builder.as_markup()


def get_final_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после оформления заказа."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="🆕 Сделать новый заказ",
            callback_data="new_order"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📋 Посмотреть мои заказы",
            callback_data="my_orders"
        )
    )
    
    return builder.as_markup()


def get_my_orders_keyboard(orders: List[Order]) -> InlineKeyboardMarkup:
    """Клавиатура списка заказов."""
    builder = InlineKeyboardBuilder()
    
    for order in orders:
        status_emoji = {
            "pending_payment": "⏳",
            "paid": "✅",
            "printing": "🖨",
            "ready": "📦",
            "shipped": "🚚",
            "delivered": "✓",
            "cancelled": "❌",
        }.get(order.status.value, "❓")
        
        builder.row(
            InlineKeyboardButton(
                text=f"{status_emoji} #{order.order_number} — {order.total_cost}₽",
                callback_data=f"order_details:{order.id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="🆕 Сделать новый заказ",
            callback_data="new_order"
        )
    )
    
    return builder.as_markup()


def get_order_detail_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Клавиатура деталей заказа."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к списку заказов",
            callback_data="my_orders"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🆕 Сделать новый заказ",
            callback_data="new_order"
        )
    )
    
    return builder.as_markup()


def get_photo_preview_keyboard(photo_id: int, current_idx: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура для превью фото при удалении."""
    builder = InlineKeyboardBuilder()
    
    # Кнопки ±10 (только если фото > 20)
    if total > 20:
        skip_buttons = []
        if current_idx >= 10:
            skip_buttons.append(
                InlineKeyboardButton(text="⏪ -10", callback_data=f"preview_photo:{current_idx - 10}")
            )
        else:
            skip_buttons.append(
                InlineKeyboardButton(text="⏪ -10", callback_data="nav_disabled")
            )
        if current_idx + 10 < total:
            skip_buttons.append(
                InlineKeyboardButton(text="+10 ⏩", callback_data=f"preview_photo:{current_idx + 10}")
            )
        else:
            skip_buttons.append(
                InlineKeyboardButton(text="+10 ⏩", callback_data="nav_disabled")
            )
        builder.row(*skip_buttons)
    
    # Кнопки ±1
    nav_buttons = []
    if current_idx > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Пред.", callback_data=f"preview_photo:{current_idx - 1}")
        )
    else:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Пред.", callback_data="nav_disabled")
        )
    if current_idx < total - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="След. ▶️", callback_data=f"preview_photo:{current_idx + 1}")
        )
    else:
        nav_buttons.append(
            InlineKeyboardButton(text="След. ▶️", callback_data="nav_disabled")
        )
    builder.row(*nav_buttons)
    
    # Кнопка удаления
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить это фото",
            callback_data=f"delete_photo:{photo_id}"
        )
    )
    
    # Завершение
    builder.row(
        InlineKeyboardButton(
            text="✅ К заказу",
            callback_data="finish_deleting"
        )
    )
    
    return builder.as_markup()
