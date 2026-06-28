"""Основные клавиатуры бота."""
from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.models.order import Order


def get_format_keyboard() -> InlineKeyboardMarkup:
    """Динамическая клавиатура выбора формата из БД."""
    from src.services.product_service import ProductService
    
    builder = InlineKeyboardBuilder()
    products = ProductService.get_top_level_products()
    
    for product in products:
        children = ProductService.get_active_children(product.id)
        if children:
            # Категория — покажем подменю
            callback = f"format_cat:{product.id}"
        else:
            # Самостоятельный товар — выбираем сразу
            callback = f"format:{product.id}"
        
        # Формируем текст кнопки
        price_hint = ""
        if product.price_per_unit > 0:
            price_hint = f" — {product.display_price}"
        elif children:
            # Для категории показываем цену первого ребёнка
            first = children[0]
            price_hint = f" — {first.display_price}"
        
        builder.row(
            InlineKeyboardButton(
                text=f"{product.emoji} {product.name}{price_hint}",
                callback_data=callback,
            )
        )
    
    return builder.as_markup()


def get_subcategory_keyboard(parent_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора варианта внутри категории."""
    from src.services.product_service import ProductService
    
    builder = InlineKeyboardBuilder()
    children = ProductService.get_active_children(parent_id)
    
    for product in children:
        builder.row(
            InlineKeyboardButton(
                text=f"{product.emoji} {product.name}",
                callback_data=f"format:{product.id}",
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к форматам",
            callback_data="back_to_formats",
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


def get_delivery_keyboard(ctx=None) -> InlineKeyboardMarkup:
    """Динамическая клавиатура выбора доставки из настроек."""
    from src.models.order import DeliveryType
    from src.services.delivery_options import delivery_display_name, delivery_cost, delivery_is_enabled

    builder = InlineKeyboardBuilder()

    delivery_methods = [
        (DeliveryType.OZON, "📦"),
        (DeliveryType.COURIER, "🚗"),
        (DeliveryType.PICKUP, "🏠"),
    ]

    for dt, emoji in delivery_methods:
        if ctx is not None and not delivery_is_enabled(ctx.settings, dt):
            continue

        if ctx is not None:
            name = delivery_display_name(ctx.settings, dt)
            price = delivery_cost(ctx.settings, dt)
        else:
            name = dt.value
            price = 0

        if price > 0:
            label = f"{emoji} {name} ({price}₽)"
        elif dt == DeliveryType.PICKUP:
            label = f"{emoji} {name} (бесплатно)"
        else:
            label = f"{emoji} {name}"

        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"delivery:{dt.value}"
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


def get_back_keyboard(callback_data: str = "back") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой Назад."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=callback_data
        )
    )
    return builder.as_markup()


def get_crop_option_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с опцией кадрирования."""
    from aiogram.types import WebAppInfo
    from src.config import settings
    import hashlib
    
    builder = InlineKeyboardBuilder()
    
    base_url = settings.admin_url or "https://print28.ru"
    token = hashlib.sha256(f"{order_id}:{settings.admin_secret_key}".encode()).hexdigest()[:32]
    webapp_url = f"{base_url}/webapp?order_id={order_id}&token={token}"
    
    builder.row(
        InlineKeyboardButton(
            text="✂️ Настроить кадрирование",
            web_app=WebAppInfo(url=webapp_url)
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⏭ Авто-кадр (пропустить)",
            callback_data="skip_crop"
        )
    )
    
    return builder.as_markup()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Основное меню после операций."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="🚚 Выбрать доставку",
            callback_data="select_delivery"
        )
    )
    
    return builder.as_markup()
